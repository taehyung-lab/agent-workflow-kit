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
    (repo / ".agents").mkdir(); (repo / ".agents" / "agent-workflow-kit.version").write_text("0" * 40 + "\n")  # 설치된 프로젝트처럼

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
              "cat a.py 2>/dev/null", "printenv NODE_OPTIONS", "grep x a 2>&1 | wc -l", "rtk git log -3", "cd sub && ls", "rtk read AGENTS.md",
              "git -C . status", "git --no-pager -C . diff", "rg \">\" src", "echo '>'", "sed -n '/w/p' a.py",
              "rtk proxy sh -c 'if [ -f v ]; then cat v; else cat AGENTS.md; fi'", "rtk --raw-output=true rg --files -g '!node_modules'",
              "rtk python3 -m unittest discover -s tests", "python3 -m pytest -q tests/test_a.py",
              "rtk rm tests/__pycache__/t.cpython-314.pyc", "rm -rf .pytest_cache tests/__pycache__",
              "rtk pnpm --dir apps/starter test", "pnpm --dir apps/starter typecheck", "npm run lint", "pnpm --filter web-kit check",
              "pnpm test src/a.test.ts", "node --version", "pnpm -v",
              "command -v node", "rtk proxy sh -c 'command -v node; node --version; pnpm --version'",
              'export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"; unset NODE_OPTIONS; pnpm typecheck',
              "rtk proxy env -u NODE_OPTIONS PATH=/x/bin:$PATH pnpm test", "env ls", "rg 'foo$' src", "grep -n '^x$' a", "ls *.md", "uniq -c a.txt", "date +%Y", "date -u", "tree -L 2", "sed -n '1,40p' a.py", "sed -n '/start/,/end/p' a", "sed 's/a/b/g' a", "sed -n -e '1p' -e '$p' a", "sort --reverse a", "sort --numeric-sort a", "rg --hidden x", "git log --oneline -3", "node -v", "python3 --version", 'echo "NODE_OPTIONS=[$NODE_OPTIONS]"', "ls ~/.nvm/versions/node", "cat $F", "/x/v24/bin/node --version",
              "env -u NODE_OPTIONS PATH=/x/bin:/usr/bin /x/bin/node --version", "python3 -m pytest -q tests/test_a.py -k login", "python3 -B -m unittest discover -s tests -p 'test_*.py'"]:
        check(f"읽기 전용 셸은 둔다: {c}", not bash(c))
    for c in ["echo x > app.py", "sed -i '' s/a/b/ a.py", "python3 -c 'open(\"a\",\"w\")'", "cat a\npython3 x.py", "ls; rm -rf src",
              "find . -delete", "git checkout -- a.py", "cat $(echo a)", "tee a.py < b", "awk '{print > \"o\"}' a", "git branch new",
              "sed -n 'w out' src", "sed 's/a/b/w out' src", "sort -o out src", "git diff --no-index --output=o /dev/null src",
              "git remote add x /tmp/n", "cat <> new", "awk -f work/r.awk src", "/tmp/cat src", "", "sh -c 'echo x > a.py'", "python3 -m unittest; rm a",
              "python3 -m pytest $(rm -rf x)", "python3 -m http.server", "rm app.py", "rm -rf __pycache__/../src",
              "pnpm lint --fix", "npx eslint . --fix", "pnpm install", "pnpm add left-pad", "npx tsc -p tsconfig.app.json",
              "pnpm test -u", "env -u X python3 x.py", "export X=1; rm a.py", "node version", "npm run lint:fix", "pnpm test-update", "npx tsc --noEmit false",
              "npx eslint . --output-file report.json", "npx tsc --noEmit --generateTrace trace", "pnpm test --outputFile=r.json",
              "pnpm lint -- --fix", "npx tsc -p tsconfig.app.json --noEmit", "pnpm --dir -x test", "npm test $TEST_ARGS", "npm test {--test-reporter-destination=r,x}", "pnpm test *", "python3 -m pytest --junitxml=o.xml", "pytest ~/x", "python3 pytest", "python3 -B pytest", "python3 unittest", "xxd -r payload.hex app.txt", "uniq a.txt app.txt", "tree -o app.txt", "file -C -m x", "date 010100002030", "date -s now",
              "sed -n -e p -e 'w app.txt' input.txt", "sed -n -ewapp.txt input.txt", "sed -n -e p -fscript.sed i", "sed -n '/x/w out' i",
              "awk -fscript.awk i", "awk 'BEGIN { print 1 | \"tee a\" }'", "sort -ro app.txt i", "sort -roapp.txt i",
              "sort -S 1b --compress-program=./c.sh i", "file --compile -m magic", "file -cC -m magic", "git -c core.fsmonitor=./w status",
              "git grep --open-files-in-pager='tee a' x", "rg --pre ./w.sh x a", "rtk grep x a --pre ./w.sh", "rtk proxy sed -n -ewa i",
              "bash -v", "python3 -v", "env NODE_OPTIONS=--require=./w.cjs npm test", "export NODE_OPTIONS=--require=./w.cjs; npm test",
              "NODE_OPTIONS=--require=./w.cjs npm test", "sort --o app.txt i", "rtk proxy sort --o app.txt i", "sort --out=app.txt i", "sort --outp app.txt i", "sort --compress=./c i", "file --com -m magic", "file --compi -m m",
              "git --no-pager diff --ext app.txt", "git diff --textc", "rg --pre=./w x", "rg --hostname=./w x", "awk --fi s.awk i", "/x/bin/node script.js", "./tool --version", "sort $X a", 'pnpm test "$X"', 'X=--outputFile=r pnpm test $X', "node -e 'require(\"fs\").writeFileSync(\"a\",\"x\")'", "node script.js", "pnpm test > out.txt"]:
        check(f"쓰기·실행 셸은 막는다: {c!r}", bash(c))
    check("cmd 필드로 온 셸도 검사한다", call("pre", {"tool_name": "exec_command", "tool_input": {"cmd": "touch app.py"}}))
    check("command 가 없는 apply_patch 입력도 대상을 찾아 막는다",
          call("pre", {"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch\n*** Add File: app.py\n+x\n*** End Patch"}}))
    check("이름으로 쓰기임이 드러나는 도구는 막는다", call("pre", {"tool_name": "mcp__files__write_file", "tool_input": {"path": "a"}})
          and call("pre", {"tool_name": "write_stdin", "tool_input": {"chars": "x"}}))
    check("계획 도구(TodoWrite·update_plan)는 막지 않는다", not call("pre", {"tool_name": "TodoWrite", "tool_input": {"todos": []}})
          and not call("pre", {"tool_name": "update_plan", "tool_input": {"plan": []}}))
    for text in ["승인하지 말고 먼저 설명만 해 주세요.", "승인 여부를 검토해 주세요", "진행해 주세요는 예시일 뿐입니다", "do not approve",
                 "보류합니다. 바로 구현하지 마세요", "진행해도 될까요?", "진행해 주실 수 있나요?", "승인할게요?",
                 '"승인합니다"라는 문구를 번역해 주세요.', "어제는 승인합니다라고 했지만 지금은 취소합니다.", "승인합니다라는 말은 아직 안 했어요.",
                 "진행해 주세요라고 말하면 되죠.", "승인합니다. 라고 답하면 되나요?", "진행해 주세요…라고 하면 안 됩니다.",
                 "다음 문장을 번역해 주세요: 승인합니다.", "승인합니다의 뜻을 설명해 주세요.", "승인합니다. 취소합니다.", "승인합니다. 아니요, 잠깐 멈춰 주세요.",
                 "진행해 주실 수 있을지 알려 주세요.", "진행해 주실 수 있는지 확인해 주세요.", "진행해 달라는 요청은 아직 아닙니다."]:
        say(text)
        check(f"승인이 아니다: {text}", edit("app.py"))
    for text in ["승인합니다. 다만 영어 문구는 빼고요.", "승인합니다. 다만 결제 모듈은 바꾸지 마세요", "진행해 주세요. 테스트는 꼭 돌려 주세요.", "네 진행해 주세요!", "좋아요, 바로 고쳐 주세요.", "진행해 주세요\n그리고 끝나면 알려 주세요", "네, 진행해 주세요", "추천안대로 승인합니다. 진행해 주세요.",
                 "이 문구 바꾸는 거 진행해 주세요", "apps/starter 로그인 버튼 글자를 '로그인하기'로 바로 바꿔 주세요.", "Go ahead.", "승인", "진행해 주세요~"]:
        say(text)
        check(f"범위를 좁히는 다른 문장이 있어도 승인이다: {text}", not edit("app.py"))
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
    import hashlib
    blocks_file = repo / ".git" / "awk-gate" / (hashlib.sha256(b"s").hexdigest()[:24] + ".blocks")
    check("같은 턴 끝에 두 번 불려도(전역·프로젝트 훅) 같은 판단을 내고 되돌리기 요청 횟수는 한 번만 센다",
          stop() and blocks_file.read_text().strip() == "1")
    (repo / "work").mkdir(exist_ok=True); (repo / "app.py").unlink(); (repo / "work" / "w.md").write_text("x")
    check("work/ 기록만 바뀌면 막지 않는다", not stop())
    (repo / "tests" / "__pycache__").mkdir(parents=True); (repo / "tests" / "__pycache__" / "t.cpython-314.pyc").write_bytes(b"\0")
    (repo / ".pytest_cache").mkdir(); (repo / ".pytest_cache" / "v").write_text("x")
    (repo / "src" / "deep" / "__pycache__").mkdir(parents=True); (repo / "src" / "deep" / "__pycache__" / "note").write_text("x")
    (repo / "src" / ".pytest_cache" / "v").mkdir(parents=True); (repo / "src" / ".pytest_cache" / "v" / "nodeids").write_text("[]")
    (repo / "__pycache__").mkdir(); (repo / "__pycache__" / "x.pyc").write_bytes(b"\0")
    check("테스트 캐시(__pycache__ 안 .pyc, .pytest_cache)만 생기면 막지 않는다", not stop())
    (repo / "src" / "a.py").write_text("x=1\n")
    check("캐시와 함께 하위 경로의 제품 파일이 생기면 막는다", stop())
    (repo / "src" / "a.py").unlink()
    say("검사만 해 주세요.")
    (repo / "app2.py").write_text("x\n")
    stop(); (repo / "app2.py").unlink()
    say("검사만 해 주세요.")
    (repo / "app2.py").write_text("x\n")
    check("다음 턴에서 같은 변경이 생겨도 앞 턴의 판단을 다시 쓰지 않고 새로 센다", stop() and blocks_file.read_text().strip() == "1")
    (repo / "app2.py").unlink()
    # 저장소 설정의 clean filter·fsmonitor 가 관문의 상태 기록 중에 실행되지 않는다
    (repo / "f.txt").write_text("before\n"); (repo / ".gitattributes").write_text("f.txt filter=demo\n")
    (repo / "w.sh").write_text("#!/bin/sh\nprintf 'after\\n' > f.txt\ncat\n"); (repo / "w.sh").chmod(0o755)
    subprocess.run(["git", "config", "filter.demo.clean", "./w.sh"], cwd=repo); subprocess.run(["git", "config", "core.fsmonitor", "./w.sh"], cwd=repo)
    say("검사만 해 주세요.")
    check("상태 기록이 저장소의 외부 프로그램(clean filter·fsmonitor)을 실행하지 않는다", (repo / "f.txt").read_text() == "before\n")
    (repo / "f.txt").chmod(0o755)
    check("승인 없는 턴에 실행 권한만 바뀌어도 되돌리게 막는다", stop())
    (repo / "f.txt").chmod(0o644)
    sub = repo / "sub"; sub.mkdir(); g = lambda *c, d=sub: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@i", *c], cwd=d, capture_output=True)
    g("init", "-q"); (sub / "s.txt").write_text("1\n"); g("add", "-A"); g("commit", "-qm", "1"); (sub / "s.txt").write_text("2\n"); g("commit", "-qam", "2")
    say("검사만 해 주세요.")
    g("checkout", "-q", "HEAD~1")
    check("승인 없는 턴에 하위 저장소의 체크아웃 버전이 바뀌면 막는다", stop())
    deep = sub
    for _ in range(4):
        deep = deep / "n"; deep.mkdir(); g("init", "-q", d=deep); (deep / "d.txt").write_text("1\n"); g("add", "-A", d=deep); g("commit", "-qm", "1", d=deep)
    say("검사만 해 주세요.")
    (deep / "d.txt").write_text("2\n")
    check("네 단계 아래 하위 저장소의 파일이 바뀌어도 막는다", stop())
    say("검사만 해 주세요.")
    (deep / "d.txt").write_text("3\n"); (deep / "d.txt").chmod(0o000)
    check("내용을 바꾼 뒤 읽기 권한을 없애도 막는다", stop())
    (deep / "d.txt").chmod(0o644)
    subprocess.run(["git", "config", "--unset", "filter.demo.clean"], cwd=repo); subprocess.run(["git", "config", "--unset", "core.fsmonitor"], cwd=repo)
    other = Path(t) / "kit-source"; other.mkdir(); subprocess.run(["git", "init", "-q"], cwd=other, check=True)
    r = subprocess.run([sys.executable, "-I", str(GATE), "pre"], capture_output=True, text=True,
                       input=json.dumps({"cwd": str(other), "session_id": "z", "tool_name": "Edit", "tool_input": {"file_path": "x.py"}}))
    check("키트 버전 기록이 없는 저장소(키트 원본 등)에서는 아무것도 막지 않는다", '"deny"' not in r.stdout)
    bad = subprocess.run([sys.executable, "-I", str(GATE), "pre"], input="{깨진", capture_output=True, text=True)
    check("입력을 읽지 못하면 막는다", '"deny"' in bad.stdout)
    nogit = subprocess.run([sys.executable, "-I", str(GATE), "pre"], capture_output=True, text=True,
                           input=json.dumps({"cwd": t, "tool_name": "Read", "tool_input": {}}))
    check("관문 오류여도 읽기 도구는 막지 않는다", '"deny"' not in nogit.stdout)

print(f"{ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
