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
              "cat a.py 2>/dev/null", "grep x a 2>&1 | wc -l", "rtk git log -3", "cd sub && ls", "rtk read AGENTS.md",
              "git -C . status", "git --no-pager -C . diff", "rg \">\" src", "echo '>'", "sed -n '/w/p' a.py",
              "rtk proxy sh -c 'if [ -f v ]; then cat v; else cat AGENTS.md; fi'", "rtk --raw-output=true rg --files -g '!node_modules'",
              "rtk python3 -m unittest discover -s tests", "python3 -m pytest -q tests/test_a.py",
              "rtk rm tests/__pycache__/t.cpython-314.pyc", "rm -rf .pytest_cache tests/__pycache__",
              "rtk pnpm --dir apps/starter test", "pnpm --dir apps/starter typecheck", "npm run lint", "pnpm --filter web-kit check",
              "pnpm test src/a.test.ts", "node --version", "pnpm -v",
              "command -v node", "rtk proxy sh -c 'command -v node; node --version; pnpm --version'",
              'export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"; unset NODE_OPTIONS; pnpm typecheck',
              "rtk proxy env -u NODE_OPTIONS PATH=/x/bin:$PATH pnpm test", "env ls", "rg 'foo$' src", "grep -n '^x$' a"]:
        check(f"읽기 전용 셸은 둔다: {c}", not bash(c))
    for c in ["echo x > app.py", "sed -i '' s/a/b/ a.py", "python3 -c 'open(\"a\",\"w\")'", "cat a\npython3 x.py", "ls; rm -rf src",
              "find . -delete", "git checkout -- a.py", "cat $(echo a)", "tee a.py < b", "awk '{print > \"o\"}' a", "git branch new",
              "sed -n 'w out' src", "sed 's/a/b/w out' src", "sort -o out src", "git diff --no-index --output=o /dev/null src",
              "git remote add x /tmp/n", "cat <> new", "awk -f work/r.awk src", "/tmp/cat src", "", "sh -c 'echo x > a.py'", "python3 -m unittest; rm a",
              "python3 -m pytest $(rm -rf x)", "python3 -m http.server", "rm app.py", "rm -rf __pycache__/../src",
              "pnpm lint --fix", "npx eslint . --fix", "pnpm install", "pnpm add left-pad", "npx tsc -p tsconfig.app.json",
              "pnpm test -u", "env -u X python3 x.py", "export X=1; rm a.py", "node version", "npm run lint:fix", "pnpm test-update", "npx tsc --noEmit false",
              "npx eslint . --output-file report.json", "npx tsc --noEmit --generateTrace trace", "pnpm test --outputFile=r.json",
              "pnpm lint -- --fix", "npx tsc -p tsconfig.app.json --noEmit", "pnpm --dir -x test", "npm test $TEST_ARGS", 'pnpm test "$X"', "cat $F", 'X=--outputFile=r pnpm test $X', "node -e 'require(\"fs\").writeFileSync(\"a\",\"x\")'", "node script.js", "pnpm test > out.txt"]:
        check(f"쓰기·실행 셸은 막는다: {c!r}", bash(c))
    check("cmd 필드로 온 셸도 검사한다", call("pre", {"tool_name": "exec_command", "tool_input": {"cmd": "touch app.py"}}))
    check("command 가 없는 apply_patch 입력도 대상을 찾아 막는다",
          call("pre", {"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch\n*** Add File: app.py\n+x\n*** End Patch"}}))
    check("이름으로 쓰기임이 드러나는 도구는 막는다", call("pre", {"tool_name": "mcp__files__write_file", "tool_input": {"path": "a"}})
          and call("pre", {"tool_name": "write_stdin", "tool_input": {"chars": "x"}}))
    check("계획 도구(TodoWrite·update_plan)는 막지 않는다", not call("pre", {"tool_name": "TodoWrite", "tool_input": {"todos": []}})
          and not call("pre", {"tool_name": "update_plan", "tool_input": {"plan": []}}))
    for text in ["승인하지 말고 먼저 설명만 해 주세요.", "승인 여부를 검토해 주세요", "진행해 주세요는 예시일 뿐입니다", "do not approve",
                 "보류합니다. 바로 구현하지 마세요", "승인합니다. 다만 결제 모듈은 바꾸지 마세요", "진행해도 될까요?"]:
        say(text)
        check(f"승인이 아니다: {text}", edit("app.py"))
    say("좋습니다. 승인합니다.")
    check("승인 턴: 편집과 셸을 연다", not edit("app.py") and not bash("python3 -m pytest"))
    check("다른 세션의 승인은 쓰지 않는다", call("pre", {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}, "session_id": "s2"}))
    check("session_id 가 없으면 승인이 없는 것으로 본다", call("pre", {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}, "session_id": None}))
    say("그런데 재가입은 막아 주세요.")
    check("다음 사용자 메시지가 승인이 아니면 다시 닫힌다", edit("app.py") and bash("python3 x.py"))
    say("바로 구현해 주세요: scripts/calc.py 로 두 수의 합")
    check("요청 메시지 안의 '바로 구현' 은 승인이다", not edit("scripts/calc.py"))

    stop = lambda: call("stop", {}) or json.loads(subprocess.run([sys.executable, "-I", str(GATE), "stop"], capture_output=True, text=True,
                input=json.dumps({"cwd": str(repo), "session_id": "s"})).stdout or "{}").get("decision") == "block"
    say("검색만 해 주세요.")
    check("승인 없는 턴에 제품 파일이 그대로면 턴을 끝낼 수 있다", not stop())
    (repo / "app.py").write_text("hidden write\n")
    check("승인 없는 턴에 숨은 쓰기로 제품 파일이 바뀌면 되돌리게 막는다", stop())
    (repo / "work").mkdir(exist_ok=True); (repo / "app.py").unlink(); (repo / "work" / "w.md").write_text("x")
    check("work/ 기록만 바뀌면 막지 않는다", not stop())
    (repo / "tests" / "__pycache__").mkdir(parents=True); (repo / "tests" / "__pycache__" / "t.cpython-314.pyc").write_bytes(b"\0")
    (repo / ".pytest_cache").mkdir(); (repo / ".pytest_cache" / "v").write_text("x")
    check("테스트 캐시(__pycache__ 안 .pyc, .pytest_cache)만 생기면 막지 않는다", not stop())
    bad = subprocess.run([sys.executable, "-I", str(GATE), "pre"], input="{깨진", capture_output=True, text=True)
    check("입력을 읽지 못하면 막는다", '"deny"' in bad.stdout)
    nogit = subprocess.run([sys.executable, "-I", str(GATE), "pre"], capture_output=True, text=True,
                           input=json.dumps({"cwd": t, "tool_name": "Read", "tool_input": {}}))
    check("관문 오류여도 읽기 도구는 막지 않는다", '"deny"' not in nogit.stdout)

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
