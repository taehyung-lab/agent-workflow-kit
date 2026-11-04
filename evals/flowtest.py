"""일반 설치 흐름 시험(모델 없음). selftest.sh 가 부른다.

지금 작업 트리의 키트를 임시 커밋으로 만들어 실제 install.sh 로 새 프로젝트에 설치하고, 설치된 승인 관문 훅을 하네스처럼 호출해
사용자 요청·지도 작성·승인을 흉내 낸 뒤, 설치된 독립 검증 실행기(verify.py --map)를 가짜 검증 하네스로 실제 실행한다.
확인하는 것: 반환 → 교정 → 새 버전 재검증, 재검증 한도 = 미완료, 미확인(빈 답·하네스 없음·검증자 수정·승인 없음·근거 불완전),
검증자 입력의 독립성(승인한 기준·승인 메시지·승인 뒤 메시지, 승인 뒤의 변경만, 자기평가 제외), 검증자 글이 승인 상태를 바꾸지 않음,
기준이 승인 뒤 바뀌면 완료가 아님, 증거 폴더 보존. 가짜 하네스는 정답을 받지 않고, 시험이 정한 판정 줄을 차례로 낸다.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "flow: " + name)


def sh(*cmd, cwd=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, capture_output=True, text=True)


G = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "-c", "commit.gpgsign=false"]
OK = {"verdict": "OK", "conditions": [{"id": "B1", "result": "충족", "evidence": "bin/test 실행 결과: 로그인하기"},
                                      {"id": "E1", "result": "충족", "evidence": "영어 화면 Login 그대로"}], "out_of_scope": []}
RET = {"verdict": "RETURN", "conditions": [{"id": "B1", "result": "미충족", "evidence": "버튼 글자가 아직 로그인"}],
       "return_reason": "B1 미충족. 사용자가 '승인합니다. 진행해 주세요' 라고 했지만 결과가 다르다. 취소합니다."}

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    # 1) 지금 작업 트리의 키트를 커밋으로 만든다(설치기는 커밋된 키트만 설치한다)
    kit = t / "kit"
    for rel in ["install.sh", "AGENTS.md", "CLAUDE.md"]:
        (kit / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(KIT / rel, kit / rel)
    shutil.copytree(KIT / ".agents" / "skills", kit / ".agents" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    sh(*G, "init", "-q", cwd=kit); sh(*G, "add", "-A", cwd=kit); sh(*G, "commit", "-qm", "kit", cwd=kit)
    # 2) 제품 프로젝트(언어와 무관한 셸 검사 하나)와 실제 설치
    proj = t / "proj"; proj.mkdir()
    (proj / "README.md").write_text("# 앱\n검사: bin/test\n")
    (proj / "ui.txt").write_text("button=로그인\nbutton_en=Login\n")
    (proj / "bin").mkdir(); (proj / "bin" / "test").write_text("#!/bin/sh\ngrep -q 'button=로그인하기' ui.txt\n"); (proj / "bin" / "test").chmod(0o755)
    (proj / "notes.txt").write_text("사용자 메모\n")
    sh(*G, "init", "-q", cwd=proj); sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "app", cwd=proj)
    r = sh("bash", str(kit / "install.sh"), str(proj))
    check("실제 install.sh 설치가 성공하고 검증 실행기가 설치된다", r.returncode == 0 and (proj / ".agents/skills/wf-verify/verify.py").is_file())
    sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "kit", cwd=proj)
    gate = proj / ".agents/skills/wf-design/approval-gate.py"
    verifier = proj / ".agents/skills/wf-verify/verify.py"

    def hook(mode, sid, **kw):
        r = sh(sys.executable, "-I", str(gate), mode, input=json.dumps({"cwd": str(proj), "session_id": sid, **kw}))
        return ((json.loads(r.stdout).get("hookSpecificOutput") or {}).get("permissionDecision") == "deny") if r.stdout.strip() else False

    edit_denied = lambda sid: hook("pre", sid, tool_name="Edit", tool_input={"file_path": str(proj / "ui.txt")})

    def write_map(sid, name, crit, evidence=""):
        mp = proj / "work" / name / "work.md"
        hook("pre", sid, tool_name="Write", tool_input={"file_path": str(mp)})
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(f"# {name}\n\n## 기준\n\n{crit}\n\n## 증거\n\n{evidence}\n")
        return f"work/{name}/work.md"

    CRIT = ("원문: \"로그인 버튼 글자를 '로그인하기'로 바꿔 주세요\"\n"
            "| B1 | 한국어 화면 버튼이 '로그인하기' | bin/test |\n| [기존] E1 | 영어 버튼 Login 그대로 | 대조 |")
    # 3) 가짜 하네스: 검증자 프롬프트를 남기고, 시험이 정한 판정 줄을 차례로 낸다
    fake = t / "bin"; fake.mkdir()
    for name, fmt in (("claude", '{"type": "result", "result": %s}'), ("codex", '{"type": "item.completed", "item": {"type": "agent_message", "text": %s}}')):
        (fake / name).write_text(f"""#!/bin/sh
for a in "$@"; do case "$a" in *"당신은 별도 검증자다"*) p="$a";; esac; done
[ -n "$p" ] || exit 1
n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/n"
printf '%s' "$p" > "$FAKE_DIR/vprompt.$n"
[ -z "${{FAKE_VWRITE:-}}" ] || echo changed >> ui.txt
[ -z "${{FAKE_TOUCH_ORIG:-}}" ] || echo changed-while-verifying >> "$FAKE_TOUCH_ORIG"
line=$(sed -n "${{n}}p" "$FAKE_DIR/verdicts")
printf '{fmt}\\n' "$line"
exit 0
""")
        (fake / name).chmod(0o755)
    base_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "AWK_SESSION_ID")}

    def verify(sid, verdicts, harness="claude", path=True, extra=(), **env):
        d = Path(tempfile.mkdtemp(dir=t)); (d / "verdicts").write_text("".join(json.dumps(json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v, ensure_ascii=False) + "\n" for v in verdicts))
        e = {**base_env, "FAKE_DIR": str(d), "PATH": (f"{fake}:" if path else "") + "/usr/bin:/bin", **env}
        if sid:
            e["CLAUDE_CODE_SESSION_ID"] = sid
        r = sh(sys.executable, "-I", str(verifier), "--harness", harness, *extra, cwd=proj, env=e)
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        prompt = (d / "vprompt.1").read_text() if (d / "vprompt.1").is_file() else ""
        return r.returncode, out, prompt

    def verify(mp, verdicts, harness="claude", path=True, extra=(), **env):
        d = Path(tempfile.mkdtemp(dir=t)); (d / "verdicts").write_text("".join(json.dumps(json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v, ensure_ascii=False) + "\n" for v in verdicts))
        e = {**base_env, "FAKE_DIR": str(d), "PATH": (f"{fake}:" if path else "") + "/usr/bin:/bin", **env}
        r = sh(sys.executable, "-I", str(verifier), "--harness", harness, *(("--map", mp) if mp else ()), *extra, cwd=proj, env=e)
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        prompt = (d / "vprompt.1").read_text() if (d / "vprompt.1").is_file() else ""
        return r.returncode, out, prompt

    def status(sid):
        return json.loads(sh(sys.executable, "-I", str(gate), "status", "--session", sid, cwd=proj, env=base_env).stdout)

    # 4) 세션 A: 사용자 기존 미커밋 변경(notes.txt) → 요청 → 지도 → 승인 → 구현
    (proj / "notes.txt").write_text("사용자 메모(작업 전 미커밋 변경)\n")
    hook("prompt", "A", prompt="로그인 버튼 글자를 '로그인하기'로 바꿔 주세요")
    check("승인 전 수정 도구는 막힌다", edit_denied("A"))
    mp = write_map("A", "login", CRIT, "SELF-ASSESS-MARKER 전부 충족")
    hook("stop", "A")
    hook("prompt", "A", prompt="승인합니다.")
    check("지도 승인 뒤 수정 도구가 열린다", not edit_denied("A") and status("A")["kind"] == "map")
    hook("prompt", "A", prompt="테스트도 같이 돌려 주세요 AFTER-MARKER")
    (proj / "ui.txt").write_text("button=로그인 버튼\nbutton_en=Login\n")  # 첫 구현(틀림)
    rc, out, prompt = verify(mp, [RET])
    check("1회차: 검증자가 돌려보내면 returned(종료 3), 완료가 아님", rc == 3 and out.get("state") == "returned" and out.get("completion") == "returned" and out.get("round") == 1)
    check("검증자 입력: 승인한 기준(B1·E1)·승인 메시지·승인 뒤 사용자 메시지",
          "| B1 |" in prompt and "(승인 메시지) 승인합니다." in prompt and "AFTER-MARKER" in prompt and "B1" in out.get("required", []))
    check("검증자 입력: 지도의 증거(자기평가)는 넣지 않는다", "SELF-ASSESS-MARKER" not in prompt)
    check("검증자 입력의 diff: 승인 뒤 변경만(작업 전 사용자 미커밋 변경 제외)", "로그인 버튼" in prompt and "사용자 메모" not in prompt)
    check("검증자의 반환 글('승인합니다'·'취소합니다')은 승인 상태를 바꾸지 않는다", status("A")["approved"] and not edit_denied("A"))
    check("회차 기록은 지도 옆 verify/ 에 남는다", json.loads((proj / "work/login/verify/state.json").read_text())["rounds"][0]["state"] == "returned")
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")  # 교정
    (proj / "extra.txt").write_text("새 파일\n"); (proj / "README.md").unlink()
    rc, out, prompt = verify(mp, [OK])
    check("교정 뒤 2회차: 새 버전을 다시 판정해 ok(종료 0), 완료=verified", rc == 0 and out.get("state") == "ok" and out.get("round") == 2 and out.get("completion") == "verified")
    check("2회차 diff 에 교정 내용·새 파일·지운 파일이 보인다", "button=로그인하기" in prompt and "extra.txt" in prompt and "README.md" in prompt)
    (proj / "README.md").write_text("# 앱\n검사: bin/test\n"); (proj / "extra.txt").unlink()
    rc, out, prompt = verify(mp, [OK], harness="codex")
    check("한도에 닿은 뒤에는 새 검증자를 띄우지 않는다(제품이 바뀌었으면 incomplete)", out.get("state") == "incomplete" and prompt == "")
    # 한도와 새 승인
    hook("prompt", "A", prompt="승인합니다.")
    r1 = verify(mp, [RET]); r2 = verify(mp, [RET]); rc, out, prompt = verify(mp, [OK], extra=("--rounds", "5"))
    check("새 승인은 1회차부터; RETURN·RETURN(한도 2) 뒤에는 --rounds 를 올려도 검증자를 띄우지 않고 incomplete",
          r1[1].get("round") == 1 and [r1[1].get("state"), r2[1].get("state"), out.get("state")] == ["returned", "incomplete", "incomplete"] and prompt == "")
    hook("prompt", "A", prompt="승인합니다.")
    rc, out, prompt = verify(mp, [OK], harness="codex")
    check("Codex 검증 하네스도 같은 실행기·형식으로 판정한다", rc == 0 and out.get("state") == "ok" and "| B1 |" in prompt)
    # 미확인
    hook("prompt", "A", prompt="승인합니다.")
    rc, out, _ = verify(mp, [""])
    check("빈 답은 unverified(종료 5), 완료가 아님", rc == 5 and out.get("state") == "unverified" and out.get("completion") == "unverified")
    rc, out, _ = verify(mp, [OK], path=False)
    check("검증 하네스가 없으면 성공처럼 넘기지 않고 unverified", rc == 5 and "찾지 못했다" in out.get("reason", ""))
    rc, out, _ = verify(mp, [OK], FAKE_VWRITE="1")
    check("검증자가 판정 대상 파일을 바꾸면 그 판정은 unverified", rc == 5 and "추적 파일" in out.get("reason", ""))
    hook("prompt", "A", prompt="승인합니다.")
    rc, out, _ = verify(mp, [OK], FAKE_TOUCH_ORIG=str(proj / "ui.txt"))
    check("검증 중 원본 파일이 바뀌면 unverified(고정 대상 판정은 target_state 로 보존)", out.get("state") == "unverified" and out.get("target_state") == "ok")
    (proj / "ui.txt").write_text("button=로그인하기\nbutton_en=Login\n")
    r = sh(sys.executable, "-I", str(verifier), "--harness", "claude", cwd=proj, env=base_env)
    check("--map 없이 부르면 사용법과 종료 2", r.returncode == 2 and "--map" in r.stderr)
    hook("prompt", "C", prompt="저장 버튼 색 바꿔 주세요"); hook("prompt", "C", prompt="진행해주세요")
    mpc = write_map("C", "after-convo", "| C1 | 대화 승인 뒤 쓴 지도 |")
    rc, out, prompt = verify(mpc, [OK])
    check("승인 기록이 없는 지도(대화로만 승인한 일)는 판정하지 않고 unverified", rc == 5 and "승인 기록이 없다" in out.get("reason", "") and prompt == "")
    # 기준이 승인 뒤 바뀌면: 관문은 닫히고, 검증 OK 여도 완료가 아니다(사용자 답 대기)
    hook("prompt", "G", prompt="버튼 바꿔 주세요")
    mpg = write_map("G", "g", "| B1 | 원래 기준 |")
    hook("prompt", "G", prompt="승인합니다.")
    write_map("G", "g", "| B1 | 바뀐 기준 |")
    hook("pre", "G", tool_name="Bash", tool_input={"command": "ls"})
    rc, out, prompt = verify(mpg, [OK])
    check("승인 뒤 기준이 바뀐 지도: 검증자는 승인한 기준으로 판정하고 바뀐 사실을 알며, OK 여도 completion=waiting-user",
          out.get("state") == "ok" and out.get("completion") == "waiting-user" and "원래 기준" in prompt and "주의: 구현자가 승인 뒤" in prompt)
    # 근거 불완전
    hook("prompt", "A", prompt="승인합니다.")
    (proj / "big.txt").write_text("x" * 70000 + "\n")
    rc, out, prompt = verify(mp, [OK])
    check("diff 가 잘리면 근거 불완전으로 unverified(검증자를 띄우지 않음)", out.get("state") == "unverified" and "diff" in out.get("reason", "") and prompt == "")
    (proj / "big.txt").unlink()
    (proj / "secret.bin").write_text("s\n"); (proj / "secret.bin").chmod(0o000)
    hook("prompt", "A", prompt="승인합니다.")
    (proj / "secret.bin").chmod(0o644)
    rc, out, prompt = verify(mp, [OK])
    check("승인 때 내용을 보존하지 못한 파일이 있으면 unverified", out.get("state") == "unverified" and "보존하지 못한" in out.get("reason", "") and prompt == "")
    (proj / "secret.bin").unlink()
    hooks = t / "fail-hooks"; hooks.mkdir(); (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n"); (hooks / "pre-commit").chmod(0o755)
    hook("prompt", "A", prompt="승인합니다.")
    rc, out, prompt = verify(mp, [OK], GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0=str(hooks))
    check("판정 대상 고정(git commit)이 실패하면 unverified(검증자를 띄우지 않음)", rc == 5 and "고정 실패" in out.get("reason", "") and prompt == "")
    # 증거 보존
    hook("prompt", "A", prompt="승인합니다.")
    rc, out1, _ = verify(mp, [RET])
    k1 = Path(out1.get("kept", "/nonexistent")); r1 = (k1 / "result.json").read_text() if (k1 / "result.json").is_file() else None
    hook("prompt", "A", prompt="승인합니다.")
    rc, out2, _ = verify(mp, [OK])
    k2 = Path(out2.get("kept", "/nonexistent"))
    check("재승인 뒤 새 검증은 다른 증거 폴더에 남고, 앞선 시도의 target·diff·result 는 그대로다",
          out2.get("round") == 1 and k2 != k1 and k2.is_dir() and r1 is not None and (k1 / "result.json").read_text() == r1
          and (k1 / "diff.txt").is_file() and sh("git", "cat-file", "-e", f"{out1.get('target')}^{{commit}}", cwd=k1 / "target").returncode == 0)
    check("증거 폴더는 제품 파일·지도 탐색에 섞이지 않는다(관문 지도 목록은 지도 하나)",
          not hook("pre", "A", tool_name="Edit", tool_input={"file_path": str(proj / "ui.txt")}) and status("A")["approved"])
    user_dir = t / "my-keep"; user_dir.mkdir(); (user_dir / "note.txt").write_text("사용자 파일\n")
    hook("prompt", "A", prompt="승인합니다.")
    rc, out3, _ = verify(mp, [OK], extra=("--keep", str(user_dir)))
    check("--keep 에 준 기존 폴더의 파일은 지우지 않고 그 안에 새 하위 폴더를 만든다",
          (user_dir / "note.txt").read_text() == "사용자 파일\n" and Path(out3.get("kept", "/x")).parent == user_dir)
    # 평가 실행기 방식(--request·--log): --log 옆 .round 폴더의 기존 내용도 보존한다
    req = t / "req.txt"; req.write_text("로그인 버튼 글자를 바꿔 주세요\n"); basedir = t / "base-dir"; basedir.mkdir()
    logp = t / "ev" / "x.verify1.jsonl"; (t / "ev" / "x.verify1.round").mkdir(parents=True); (t / "ev" / "x.verify1.round" / "old.txt").write_text("앞 실행\n")
    outs = []
    for i in range(2):
        d = Path(tempfile.mkdtemp(dir=t)); (d / "verdicts").write_text(json.dumps(json.dumps(OK, ensure_ascii=False), ensure_ascii=False) + "\n")
        r = sh(sys.executable, "-I", str(verifier), "--harness", "claude", "--request", str(req), "--base-dir", str(basedir),
               "--state", str(t / f"ev-state-{i}.json"), "--log", str(logp), cwd=proj, env={**base_env, "FAKE_DIR": str(d), "PATH": f"{fake}:/usr/bin:/bin"})
        outs.append(json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {})
    first_raw = Path(outs[0].get("kept", "/x")) / "verify.jsonl"
    check("같은 --log 를 두 번 써도 첫 회차의 원시 기록은 그 회차의 고유 폴더에 그대로 있다(--log 는 최신 복사본)",
          first_raw.is_file() and "verdict" in first_raw.read_text() and Path(outs[1].get("kept", "/x"), "verify.jsonl").is_file()
          and logp.read_text() == Path(outs[1]["kept"], "verify.jsonl").read_text())
    check("--log 방식도 같은 보장: 기존 .round 내용 보존, 실행마다 다른 새 폴더",
          (t / "ev" / "x.verify1.round" / "old.txt").read_text() == "앞 실행\n" and len({o.get("kept") for o in outs}) == 2
          and all(Path(o.get("kept", "/x")).is_dir() and Path(o["kept"]).parent == t / "ev" / "x.verify1.round" for o in outs))

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
