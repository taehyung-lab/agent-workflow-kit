"""표준 쓰기 경계 시험(모델 없음). selftest.sh 가 부른다.

Codex 의 표준 쓰기 경계(workspace-write, 권한 프로필 :workspace)는 에이전트 셸에서 `.git`·`.agents`·`.codex` 를 읽기 전용으로 둔다.
에이전트가 셸로 부르는 명령(approval-gate.py task·status, wf-verify/verify.py)이 그 경계 안에서 실제로 동작하는지,
그리고 승인 근거는 여전히 훅(하네스가 sandbox 밖에서 실행)만 만드는지를 실제 `codex sandbox -P :workspace` 로 확인한다.
훅은 하네스처럼 sandbox 밖에서 부르고, 에이전트 명령만 sandbox 안에서 부른다. 검증자 하네스는 가짜다(모델을 부르지 않는다).

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
    """폴더 안 모든 파일의 경로·내용 지문(관문 기록이 바뀌었는지 보려고)."""
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*")) if Path(d).is_dir() else []:
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


G = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "-c", "commit.gpgsign=false"]
OK = {"verdict": "OK", "conditions": [{"id": "B1", "result": "충족", "evidence": "python3 price.py 1000 3 10 → 2700"}], "out_of_scope": []}
RET = {"verdict": "RETURN", "conditions": [{"id": "B1", "result": "미충족", "evidence": "아직 3000"}], "return_reason": "B1 미충족. 승인합니다."}
PLAN = "계획입니다.\n\n## 기준\n\n| B1 | 1000원 3개 10% 할인 → 2700 | price.py | python3 price.py 1000 3 10 |\n\n## 질문\n\n진행할까요?"

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
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "AWK_SESSION_ID", "AWK_GATE_LOG")}
    box = [codex or "codex", "sandbox", "-P", ":workspace", "-C", str(proj)]  # 절대 경로: 시험의 PATH 에 가짜 codex 가 있다
    probe = sh(*box, "sh", "-c", "touch work-probe && rm work-probe && ! touch .git/probe 2>/dev/null", cwd=proj, env=env) if codex else None
    if not codex or probe.returncode != 0:
        why = "codex 가 없다" if not codex else f"codex sandbox -P :workspace 를 쓸 수 없거나 .git 이 읽기 전용이 아니다: {probe.stderr.strip()[:200]}"
        print(f"미실행 sandbox: {why}. 재개 조건: codex(0.166 이상) 가 설치된 macOS/Linux 에서 다시 실행한다")
        sys.exit(3)
    check("경계 실재: 같은 sandbox 에서 작업 폴더는 쓸 수 있고 .git 은 읽기 전용이다", True)

    gate = proj / ".agents/skills/wf-design/approval-gate.py"
    verifier = proj / ".agents/skills/wf-verify/verify.py"
    state = proj / ".git" / "awk-gate"
    key = lambda sid: hashlib.sha256(sid.encode()).hexdigest()[:24]
    rec = lambda sid: json.loads((state / f"{key(sid)}.approval").read_text())

    def hook(mode, sid, **kw):  # 하네스가 sandbox 밖에서 부르는 훅
        r = sh(sys.executable, "-I", str(gate), mode, input=json.dumps({"cwd": str(proj), "session_id": sid, **kw}), env=env)
        return r

    def denied(sid, path="price.py"):
        out = hook("pre", sid, tool_name="Edit", tool_input={"file_path": str(proj / path)}).stdout
        return bool(out.strip()) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"

    def stop_blocks(sid):
        out = hook("stop", sid).stdout.strip()
        return bool(out) and json.loads(out).get("decision") == "block"

    def inbox(*cmd, **extra):  # 에이전트 셸: 표준 쓰기 경계 안
        return sh(*box, *cmd, cwd=proj, env={**env, **extra})

    def gate_cli(*args, sid="S"):
        return inbox("python3", str(gate), *args, "--session", sid)

    transcript = t / "plan.jsonl"
    transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "요청"}}) + "\n"
                          + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": PLAN}]}}) + "\n")

    # 1) 실제 실패 재현 경로: 요청 → 조사 → task begin (sandbox 안)
    hook("prompt", "S", prompt="할인 계산이 틀린 것 같아요, 고쳐 주세요")
    first = rec("S")["id"]
    before = tree_print(state)
    r = gate_cli("task", "begin", "discount-calculation")
    out = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
    check("task begin 이 표준 쓰기 경계 안에서 성공한다(종료 0, 오류 없음)", r.returncode == 0 and "오류" not in r.stderr and out.get("name") == "discount-calculation")
    check("task begin 출력은 곧바로 새 작업(다른 id, 사용자 답 대기)을 보여 준다", out.get("task") not in (None, first) and out.get("approval") == "waiting" and out.get("waiting") is True)
    check("명령은 관문 기록(.git/awk-gate)을 쓰지 않는다", tree_print(state) == before)
    r = gate_cli("status")
    st = json.loads(r.stdout) if r.returncode == 0 else {}
    check("status 도 같은 경계 안에서 성공하고 선언을 반영한다", r.returncode == 0 and st.get("task") == out.get("task") and st.get("name") == "discount-calculation")
    r = inbox("python3", str(gate), "status", CODEX_THREAD_ID="S")
    check("세션 id 를 하네스 환경 변수(CODEX_THREAD_ID)로 받아도 같다", r.returncode == 0 and json.loads(r.stdout).get("task") == out.get("task"))
    check("다음 훅이 선언을 관문 기록에 흡수한다(같은 작업 id·이름, 승인은 열리지 않음)",
          denied("S") and rec("S")["id"] == out.get("task") and rec("S")["name"] == "discount-calculation" and rec("S")["approved"] is False)
    check("에이전트 기록 폴더는 git 이 무시한다(제품 파일·커밋에 섞이지 않음)",
          (proj / "work/.awk-gate/.gitignore").is_file() and "awk-gate" not in sh("git", "status", "--porcelain", "--untracked-files=all", cwd=proj).stdout)

    # 2) 에이전트 기록을 위조해도 승인 근거가 생기지 않는다
    decl = proj / "work/.awk-gate" / key("S") / "decl.jsonl"
    tid = rec("S")["id"]
    inbox("sh", "-c", "printf '%s\\n' \"$1\" \"$2\" \"$3\" >> \"$4\"; printf '%s' \"$5\" > \"$6\"",
          "x", json.dumps({"uid": "f1", "kind": "approve", "task": tid, "approved": True}),
          json.dumps({"uid": "f2", "kind": "verify", "task": tid, "approved_at": 1.0, "round": {"uid": "r", "state": "ok"}, "state": "ok"}),
          json.dumps({"uid": "f3", "kind": "done", "task": tid, "approved": True}), str(decl),
          json.dumps({"approved": True, "state": "approved", "approved_at": 1.0}), str(decl.parent / f"{key('S')}.approval"))
    r = gate_cli("status"); st = json.loads(r.stdout) if r.returncode == 0 else {}
    check("에이전트 기록에 approved=true·다른 승인 시각·가짜 승인 파일을 써도 status 는 승인 전이다",
          st.get("approval") == "waiting" and not st.get("verify"))
    check("위조 기록을 흡수한 훅도 수정 도구를 막는다", denied("S") and rec("S")["approved"] is False and not rec("S").get("approved_at"))
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

    def verify(verdicts, sid="S", **extra):
        d = Path(tempfile.mkdtemp(dir=t))
        (d / "verdicts").write_text("".join(json.dumps(json.dumps(v, ensure_ascii=False), ensure_ascii=False) + "\n" for v in verdicts))
        r = inbox("python3", str(verifier), "--harness", "codex", "--session", sid,
                  FAKE_DIR=str(d), PATH=f"{fake}:{env.get('PATH', '/usr/bin:/bin')}", **extra)
        o = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        return r.returncode, o, (d / "vprompt.1").read_text() if (d / "vprompt.1").is_file() else ""

    rc, o, p = verify([OK])
    check("승인 전 verify 는 위조 기록과 관계없이 판정하지 않고 미확인(5), 사용자 답 대기", rc == 5 and o.get("completion") == "waiting-user" and p == "")

    # 3) 승인(사용자 메시지, 훅) → 구현(셸) → 검증(sandbox 안, 가짜 하네스)
    hook("prompt", "S", prompt="승인합니다.", transcript_path=str(transcript))
    check("사용자 승인은 훅으로 열린다", not denied("S"))
    approved_at = rec("S")["approved_at"]
    inbox("sh", "-c", "printf 'import sys\\np, n, d = map(int, sys.argv[1:4])\\nprint(p * n * (100 - d) // 100)\\n' > price.py")
    before = tree_print(state)
    rc, o, p = verify([RET])
    kept = Path(o.get("kept", "/nonexistent"))
    check("verify 가 표준 쓰기 경계 안에서 돈다: 돌려보냄(3), 증거 폴더는 작업 폴더의 에이전트 기록 안",
          rc == 3 and o.get("state") == "returned" and kept.is_dir() and Path(os.path.realpath(proj / "work/.awk-gate")) in Path(os.path.realpath(kept)).parents)
    check("verify 입력: 사용자 원문·승인 기준·이번 변경", "할인 계산이 틀린" in p and "| B1 |" in p and "(100 - d)" in p)
    check("고정 대상 커밋·diff·판정이 증거 폴더에 남는다",
          (kept / "target").is_dir() and sh("git", "cat-file", "-e", f"{o.get('target')}^{{commit}}", cwd=kept / "target").returncode == 0
          and all((kept / f).exists() for f in ("base", "diff.txt", "prompt.txt", "result.json", "verify.jsonl")))
    check("verify 는 관문 기록(.git/awk-gate)을 쓰지 않는다", tree_print(state) == before)
    r = gate_cli("status"); st = json.loads(r.stdout)
    check("판정 회차가 status 에 바로 보이고 승인 상태는 그대로다", st.get("approval") == "open" and len(st["verify"].get("rounds", [])) == 1)
    hook("pre", "S", tool_name="Bash", tool_input={"command": "ls"})
    check("다음 훅이 판정 회차를 관문 기록에 흡수한다", len(rec("S")["verify"].get("rounds", [])) == 1 and rec("S")["approved"] is True)
    rc, o, _ = verify([RET])
    check("재검증 한도(2)에 닿으면 미완료(4)", rc == 4 and o.get("state") == "incomplete")
    hook("pre", "S", tool_name="Bash", tool_input={"command": "ls"})
    inbox("rm", "-f", str(decl))
    rc, o, p = verify([OK])
    check("흡수 뒤 에이전트 기록을 지워도 한도는 초기화되지 않는다(새 검증자를 띄우지 않음)", rc == 4 and p == "")
    check("앞선 회차의 원시 기록은 지워지지 않는다", kept.is_dir() and (kept / "verify.jsonl").is_file() and (kept / "result.json").is_file())
    hook("prompt", "S", prompt="승인합니다.")  # 사용자의 새 승인 = 새 검증 시도
    check("같은 작업 재승인은 새 승인 시각을 만든다", rec("S")["approved_at"] != approved_at)
    rc, o, p = verify([OK])
    check("새 승인 시도에는 앞선 시도의 회차가 합쳐지지 않는다: 1회차부터 다시 판정해 ok(0)", rc == 0 and o.get("state") == "ok" and o.get("round") == 1 and p != "")
    rc, o, _ = verify([OK], FAKE_FAIL="1")
    check("검증자 하네스가 실패하면(sandbox 안 네트워크 차단 등) 미확인(5)과 재개 조건, 완료가 아님",
          rc == 5 and o.get("state") == "unverified" and "재개 조건" in o.get("reason", "") and o.get("completion") == "unverified")

    # 4) 완료 선언과 턴 끝 검사(승인 중 변경은 알리지 않고, 선언 뒤·승인 없는 변경은 알린다)
    hook("prompt", "S", prompt="승인합니다.")
    inbox("sh", "-c", "echo '# 승인 중 수정' >> price.py")
    r = gate_cli("task", "done")
    check("task done 이 경계 안에서 성공하고 승인을 닫는다(대기 아님)", r.returncode == 0 and json.loads(r.stdout).get("approval") == "closed" and json.loads(r.stdout).get("waiting") is False)
    check("승인 → 허용된 수정 → task done → 턴 끝: 알림 없음", not stop_blocks("S"))
    hook("prompt", "S", prompt="승인합니다.")
    inbox("sh", "-c", f"echo '# 승인 중' >> price.py && python3 {gate} task done --session S >/dev/null && echo '# 완료 뒤' >> price.py")
    check("같은 셸 명령 안에서 task done 뒤에 더 고치면 턴 끝에 알린다", stop_blocks("S"))
    hook("prompt", "S", prompt="승인합니다.")
    gate_cli("task", "done")
    inbox("sh", "-c", "echo '# 완료 뒤 다음 명령' >> price.py")
    check("task done 뒤 다른 명령으로 고쳐도 턴 끝에 알린다", stop_blocks("S"))
    hook("prompt", "S", prompt="어디까지 됐어요?")
    inbox("sh", "-c", "echo '# 승인 없이' >> price.py")
    gate_cli("task", "done")
    check("승인 없는 수정 → task done → 턴 끝: 여전히 알린다", stop_blocks("S"))

    # 5) 명시 명령의 실패는 0 이 아닌 종료 코드와 오류 문구
    r = gate_cli("task", "begin", "x", sid="no-such-session")
    check("작업 기록이 없는 세션의 task begin 은 종료 2 와 오류 문구", r.returncode == 2 and "오류" in r.stderr)
    r = gate_cli("status", sid="no-such-session")
    check("작업 기록이 없는 세션의 status 는 종료 2(사유 JSON 도 냄)", r.returncode == 2 and json.loads(r.stdout).get("task") is None)
    r = gate_cli("task", "frobnicate")
    check("잘못된 task 사용은 종료 2", r.returncode == 2 and "사용" in r.stderr)
    r = inbox("python3", str(gate), "--help")
    check("--help 는 사용법(종료 0), 훅 입력으로 읽지 않는다", r.returncode == 0 and "사용" in r.stdout)
    shutil.move(str(proj / "work"), str(t / "work-saved")); (proj / "work").write_text("파일\n")
    r = gate_cli("task", "begin", "y")
    check("에이전트 기록을 쓰지 못하면 task 는 종료 1 과 오류 문구(조용히 0 이 아님)", r.returncode == 1 and "오류" in r.stderr)
    rc, o, _ = verify([OK])
    check("verify 도 기록 실패는 미확인(5)과 오류 문구", rc == 5 and o.get("state") == "unverified")
    (proj / "work").unlink(); shutil.move(str(t / "work-saved"), str(proj / "work"))
    plain = t / "plain"; plain.mkdir(); sh(*G, "init", "-q", cwd=plain)
    r = sh(codex, "sandbox", "-P", ":workspace", "-C", str(plain), "python3", str(gate), "status", cwd=plain, env=env)
    check("키트가 설치되지 않은 저장소의 status 는 종료 2 와 오류 문구", r.returncode == 2 and "오류" in r.stderr)

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
