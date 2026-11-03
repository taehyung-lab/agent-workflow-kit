"""승인 관문(wf-design/approval-gate.py)을 모델 없이 시험한다. selftest.sh 가 부른다."""
import json, subprocess, sys, tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / ".agents/skills/wf-design/approval-gate.py"
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "gate: " + name)


with tempfile.TemporaryDirectory() as t:
    repo = Path(t) / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    def call(mode, payload):
        p = {"cwd": str(repo), "session_id": "s", **payload}
        r = subprocess.run([sys.executable, "-I", str(GATE), mode], input=json.dumps(p), capture_output=True, text=True)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"

    say = lambda text: call("prompt", {"prompt": text})
    bash = lambda c: call("pre", {"tool_name": "Bash", "tool_input": {"command": c}})
    edit = lambda f: call("pre", {"tool_name": "Edit", "tool_input": {"file_path": f}})
    patch = lambda f: call("pre", {"tool_name": "apply_patch", "tool_input": {"command": f"*** Begin Patch\n*** Update File: {f}\n@@\n-a\n+b\n*** End Patch"}})

    check("승인 기록이 없으면 제품 파일 편집을 막는다", edit(str(repo / "app.py")))
    say("회원 탈퇴 기능을 만들어 주세요.")
    check("승인 없는 요청 턴: 제품 파일 편집을 막는다", edit("app.py"))
    check("승인 없는 요청 턴: apply_patch 를 막는다", patch(str(repo / "accounts.py")))
    check("승인 없는 요청 턴: work/ 아래 설계 기록은 쓸 수 있다", not edit(str(repo / "work/x/work.md")) and not patch("work/x/work.md"))
    check("work/ 를 벗어나는 경로(..)는 막는다", edit(str(repo / "work/../app.py")))
    check("읽기 도구는 막지 않는다", not call("pre", {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}))
    for c in ["ls -la; cat a.py | head -5", "rg -n 'a|b' src", "git status && git diff HEAD", "sed -n 1,20p a.py", "find . -name '*.py'",
              "cat a.py 2>/dev/null", "grep x a 2>&1 | wc -l", "rtk git log -3", "cd sub && ls"]:
        check(f"읽기 전용 셸은 둔다: {c}", not bash(c))
    for c in ["echo x > app.py", "sed -i '' s/a/b/ a.py", "python3 -c 'open(\"a\",\"w\")'", "cat a\npython3 x.py", "ls; rm -rf src",
              "find . -delete", "git checkout -- a.py", "cat $(echo a)", "tee a.py < b", "awk '{print > \"o\"}' a", "git branch new"]:
        check(f"쓰기·실행 셸은 막는다: {c!r}", bash(c))
    say("승인하지 말고 먼저 설명만 해 주세요.")
    check("부정 표현은 승인이 아니다", edit("app.py"))
    say("좋습니다. 승인합니다.")
    check("승인 턴: 편집과 셸을 연다", not edit("app.py") and not bash("python3 -m pytest"))
    say("그런데 재가입은 막아 주세요.")
    check("다음 사용자 메시지가 승인이 아니면 다시 닫힌다", edit("app.py") and bash("python3 x.py"))
    say("바로 구현해 주세요: scripts/calc.py 로 두 수의 합")
    check("요청 메시지 안의 '바로 구현' 은 승인이다", not edit("scripts/calc.py"))

    bad = subprocess.run([sys.executable, "-I", str(GATE), "pre"], input="{깨진", capture_output=True, text=True)
    check("입력을 읽지 못하면 막는다", '"deny"' in bad.stdout)
    nogit = subprocess.run([sys.executable, "-I", str(GATE), "pre"], capture_output=True, text=True,
                           input=json.dumps({"cwd": t, "tool_name": "Read", "tool_input": {}}))
    check("관문 오류여도 읽기 도구는 막지 않는다", '"deny"' not in nogit.stdout)

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
