"""Stop 훅(wf-verify/stop-verify.py)을 모델 없이 시험한다. selftest.sh 가 부른다.

가짜 claude 가 받은 프롬프트를 파일로 남기고 정해 둔 답을 낸다. 훅의 출력(막음 여부)과 가짜 검증자 호출 횟수를 본다.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify/stop-verify.py"
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "hook: " + name)


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    repo, bindir = t / "repo", t / "bin"
    repo.mkdir(); bindir.mkdir()
    sh(repo, "git", "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    sh(repo, "git", "add", "-A"); sh(repo, "git", "-c", "user.name=t", "-c", "user.email=t@i", "commit", "-qm", "i")
    fake = bindir / "claude"
    fake.write_text('#!/bin/sh\nn=$(cat "$FAKE_DIR/calls" 2>/dev/null || echo 0); echo $((n+1)) > "$FAKE_DIR/calls"\n'
                    'while [ $# -gt 0 ]; do [ "$1" = -p ] && printf "%s" "$2" > "$FAKE_DIR/prompt"; shift; done\n'
                    'printf "%b\\n" "$FAKE_ANSWER"; exit "${FAKE_RC:-0}"\n')
    fake.chmod(0o755)
    transcript = t / "t.jsonl"

    def write_transcript(*msgs):
        transcript.write_text("".join(json.dumps({"type": "user", "message": {"content": m}}, ensure_ascii=False) + "\n" for m in msgs))

    def run(answer, continued=False, rc=0, turn="s1"):
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_DIR=str(t), FAKE_ANSWER=answer, FAKE_RC=str(rc), AWK_VERIFIER="claude")
        env.pop("AWK_VERIFYING", None)
        payload = {"cwd": str(repo), "transcript_path": str(transcript), "session_id": turn, "stop_hook_active": continued}
        r = subprocess.run([sys.executable, "-I", str(HOOK)], input=json.dumps(payload), env=env, capture_output=True, text=True)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return out.get("decision") == "block", out.get("reason", ""), r.stderr

    def calls():
        return int((t / "calls").read_text()) if (t / "calls").exists() else 0

    write_transcript("<요청>탈퇴를 비활성화로</요청>", "<system-reminder>주입</system-reminder>", "[stop-verify] 훅 지시")
    blocked, _, _ = run("OK")
    check("변경이 없으면 검증자를 부르지 않는다", not blocked and calls() == 0)

    (repo / "a.py").write_text("x = 2\n")
    (repo / "tests").mkdir(); (repo / "tests" / "b.bin").write_bytes(b"\x00\x01binary")
    blocked, _, err = run("RETURN\n명단 표시는 근거 없음")
    prompt = (t / "prompt").read_text() if (t / "prompt").exists() else ""
    check("이진 새 파일이 있어도 검증자를 부른다", calls() == 1 and "이진" in prompt and "\x00" not in prompt)
    check("'<'로 시작하는 실제 요청은 원문에 넣고 주입·훅 지시는 뺀다", "<요청>탈퇴를 비활성화로" in prompt and "주입" not in prompt and "훅 지시" not in prompt)
    check("RETURN 이면 막고 사유를 돌려준다", blocked)

    (repo / "a.py").write_text("x = 3\n")
    blocked, _, _ = run("OK", continued=True)
    check("돌려받은 뒤 다시 멈추면 바뀐 변경을 다시 검토한다", calls() == 2 and not blocked)
    blocked, _, _ = run("OK")
    check("같은 원문·변경에 OK 를 받았으면 다시 부르지 않는다", calls() == 2 and not blocked)
    write_transcript("<요청>탈퇴를 비활성화로</요청>", "명단에서는 숨겨 주세요")
    run("OK", turn="s2")
    check("원문이 바뀌면 같은 변경도 다시 검토한다", calls() == 3)

    (repo / "a.py").write_text("x = 4\n")
    blocked, reason, _ = run("", rc=1, turn="s3")
    check("검증 세션이 실패하면 막고 미확인으로 보고하게 한다", blocked and "미확인" in reason)
    blocked, _, _ = run("OKAY 좋아 보임", turn="s4")
    check("첫 줄이 정확히 OK·RETURN 이 아니면 통과로 보지 않는다", blocked)
    run("RETURN\nx", turn="s5"); run("RETURN\nx", turn="s5")
    blocked, _, err = run("RETURN\nx", turn="s5")
    check("한 턴에 막는 횟수는 한도까지만", not blocked and "한도" in err)

print(f"hook {ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
