"""표준 쓰기 경계 시험(모델 없음). selftest.sh 가 부른다.

Codex 의 표준 쓰기 경계(workspace-write, 권한 프로필 :workspace)는 에이전트 셸에서 `.git`·`.agents`·`.codex` 를 읽기 전용으로 둔다.
에이전트가 셸로 부르는 독립 검토 실행기(wf-verify/verify.py --map)가 그 경계 안에서 동작하고 원래 저장소의 .git 을 쓰지 않는지를
실제 `codex sandbox -P :workspace` 로 확인한다. 검토자 하네스는 가짜다.

codex 가 없거나 `codex sandbox` 를 쓸 수 없는 환경은 이 확인을 "미실행"으로 출력하고 종료 코드 3 으로 끝난다(통과로 세지 않는다).
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "sandbox: " + name)


def sh(*cmd, cwd=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, capture_output=True, text=True)


def tree_print(d):
    """폴더 안 모든 파일의 경로·내용 지문(.git 이 바뀌었는지 보려고)."""
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*")) if Path(d).is_dir() else []:
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


G = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "-c", "commit.gpgsign=false"]
OK = {"verdict": "OK", "conditions": [{"id": "B1", "result": "충족", "evidence": "python3 price.py 1000 3 10 → 2700"}], "out_of_scope": []}
RET = {"verdict": "RETURN", "conditions": [{"id": "B1", "result": "미충족", "evidence": "아직 3000"}], "return_reason": "B1 미충족."}
PLAN = "계획입니다.\n\n## 기준\n\n- 요청 원문: 할인 계산이 틀린 것 같아요, 고쳐 주세요\n| B1 | 1000원 3개 10% 할인 → 2700 | price.py | python3 price.py 1000 3 10 |\n\n## 질문\n\n진행할까요?"

codex = shutil.which("codex")
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    kit = t / "kit"
    for rel in ["install.sh", "AGENTS.md", "CLAUDE.md"]:
        (kit / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(KIT / rel, kit / rel)
    shutil.copytree(KIT / ".agents" / "skills", kit / ".agents" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    sh(*G, "init", "-q", cwd=kit); sh(*G, "add", "-A", cwd=kit); sh(*G, "commit", "-qm", "kit", cwd=kit)
    proj = t / "proj"; proj.mkdir()
    (proj / "README.md").write_text("# 가격\n검사: python3 price.py 1000 3 10\n")
    (proj / "price.py").write_text("import sys\np, n, d = map(int, sys.argv[1:4])\nprint(p * n)\n")
    sh(*G, "init", "-q", cwd=proj); sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "app", cwd=proj)
    r = sh("bash", str(kit / "install.sh"), str(proj))
    if r.returncode != 0:
        check("install.sh 설치", False); print(r.stderr); print(f"{ok} passed, {failed} failed"); sys.exit(1)
    sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "kit", cwd=proj)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    box = [codex or "codex", "sandbox", "-P", ":workspace", "-C", str(proj)]  # 절대 경로: 시험의 PATH 에 가짜 codex 가 있다
    probe = sh(*box, "sh", "-c", "touch work-probe && rm work-probe && ! touch .git/probe 2>/dev/null", cwd=proj, env=env) if codex else None
    if not codex or probe.returncode != 0:
        why = "codex 가 없다" if not codex else f"codex sandbox -P :workspace 를 쓸 수 없거나 .git 이 읽기 전용이 아니다: {probe.stderr.strip()[:200]}"
        print(f"미실행 sandbox: {why}. 재개 조건: codex(0.166 이상) 가 설치된 macOS/Linux 에서 다시 실행한다")
        sys.exit(3)
    check("경계 실재: 같은 sandbox 에서 작업 폴더는 쓸 수 있고 .git 은 읽기 전용이다", True)

    verifier = proj / ".agents/skills/wf-verify/verify.py"

    def inbox(*cmd, **extra):  # 에이전트 셸: 표준 쓰기 경계 안
        return sh(*box, *cmd, cwd=proj, env={**env, **extra})

    mp = proj / "work/discount/work.md"
    mp.parent.mkdir(parents=True); mp.write_text(PLAN.replace("계획입니다.", "# 할인") + "\n## 증거\n")
    fake = t / "bin"; fake.mkdir()
    (fake / "codex").write_text("""#!/bin/sh
for a in "$@"; do case "$a" in *"당신은 별도 검증자다"*) p="$a";; esac; done
[ -n "$p" ] || exit 1
n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/n"
printf '%s' "$p" > "$FAKE_DIR/vprompt.$n"
[ -z "${FAKE_FAIL:-}" ] || { echo "network blocked" >&2; exit 9; }
line=$(sed -n "${n}p" "$FAKE_DIR/verdicts")
printf '{"type": "item.completed", "item": {"type": "agent_message", "text": %s}}\\n' "$line"
""")
    (fake / "codex").chmod(0o755)

    def verify(verdicts, *args, **extra):
        d = Path(tempfile.mkdtemp(dir=t))
        (d / "verdicts").write_text("".join(json.dumps(json.dumps(v, ensure_ascii=False), ensure_ascii=False) + "\n" for v in verdicts))
        r = inbox("python3", str(KIT / "evals/verdict.py"), "session", "--tool", str(verifier), "--harness", "codex", "--map", "work/discount/work.md", *args,
                  FAKE_DIR=str(d), PATH=f"{fake}:{env.get('PATH', '/usr/bin:/bin')}", **extra)
        o = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        return r.returncode, o, (d / "vprompt.1").read_text() if (d / "vprompt.1").is_file() else ""

    # 구현(셸, sandbox 안) → 검토(sandbox 안, 가짜 하네스)
    inbox("sh", "-c", "printf 'import sys\\np, n, d = map(int, sys.argv[1:4])\\nprint(p * n * (100 - d) // 100)\\n' > price.py")
    git_before = tree_print(proj / ".git")
    rc, o, p = verify([RET])
    kept = Path(o.get("kept", "/nonexistent"))
    check("verify 가 표준 쓰기 경계 안에서 돈다: 돌려보냄(3), 증거 폴더는 지도 옆 verify/",
          rc == 3 and o.get("state") == "returned" and kept.is_dir() and Path(os.path.realpath(proj / "work/discount/verify")) in Path(os.path.realpath(kept)).parents)
    check("verify 입력: 지도에 옮긴 요청 원문·지도 기준·이번 변경", "할인 계산이 틀린" in p and "| B1 |" in p and "(100 - d)" in p)
    check("고정 대상 커밋·diff·판정이 증거 폴더에 남는다",
          (kept / "target").is_dir() and sh("git", "cat-file", "-e", f"{o.get('target')}^{{commit}}", cwd=kept / "target").returncode == 0
          and (kept / "diff.txt").is_file() and (kept / "result.json").is_file())
    check("verify 는 원래 저장소의 .git 을 쓰지 않는다(기준 커밋은 읽기만)", tree_print(proj / ".git") == git_before)
    rc, o, p = verify([RET])
    check("재검토 한도(2)에 닿으면 미완료(4)", rc == 4 and o.get("state") == "incomplete")
    req = proj / "work/discount/req2.txt"; req.write_text("할인은 소수점 아래를 버려 주세요\n")
    rc, o, p = verify([OK], "--request", str(req))
    check("요청 원문이 다른 새 시도는 1회차부터 다시 판정해 ok(0)", rc == 0 and o.get("state") == "ok" and o.get("round") == 1 and p != "")
    req.write_text("세 번째 시도\n")
    rc, o, p = verify([OK], "--request", str(req), FAKE_FAIL="1")
    check("검토자 하네스가 실패하면 미확인(5)과 재개 조건, 완료가 아님", rc == 5 and "재개 조건" in o.get("reason", "") and o.get("completion") != "verified")


print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
