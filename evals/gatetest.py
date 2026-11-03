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
    # 셸은 내용을 해석하지 않는다: 어느 언어의 검사 명령도, 셸 쓰기도 미리 막지 않는다(쓰기는 턴 끝 사후 감지).
    for c in ["ls -la; cat a.py | head -5", "python3 -m pytest -q", "pnpm test", "go test ./...", "composer test", "vendor/bin/phpunit",
              "php artisan test", "./gradlew test", "mvn -q test", "cargo test", "bundle exec rspec", "dotnet test", "npx tsc --noEmit",
              "rm -rf __pycache__", "echo x > app.py", "sed -i '' s/a/b/ a.py", ""]:
        check(f"셸은 미리 막지 않는다: {c!r}", not bash(c))
    check("cmd 필드로 온 셸·열린 셸 입력도 미리 막지 않는다", not call("pre", {"tool_name": "exec_command", "tool_input": {"cmd": "touch app.py"}})
          and not call("pre", {"tool_name": "write_stdin", "tool_input": {"chars": "x"}}))
    import re as _re
    src = GATE.read_text(encoding="utf-8")
    check("관문 코드에 셸 명령 목록·언어별 검사식·캐시 예외가 없다",
          not _re.search(r"READ_ONLY|TEST_RUN|JS_CHECK|__pycache__|pytest_cache|\\.pyc|pnpm|unittest", src))
    check("command 가 없는 apply_patch 입력도 대상을 찾아 막는다",
          call("pre", {"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch\n*** Add File: app.py\n+x\n*** End Patch"}}))
    check("이름으로 쓰기임이 드러나는 도구는 막는다", call("pre", {"tool_name": "mcp__files__write_file", "tool_input": {"path": "a"}}))
    check("계획 도구(TodoWrite·update_plan)는 막지 않는다", not call("pre", {"tool_name": "TodoWrite", "tool_input": {"todos": []}})
          and not call("pre", {"tool_name": "update_plan", "tool_input": {"plan": []}}))
    # 승인 판별 고정 표본(work/approval-retro 합의). 표본 밖의 드문 말은 문서의 한계로 두고 에이전트가 다시 확인한다.
    for text in ["진행해주세요라고 답하세요.", "승인합니다라는 표현", "진행해 주세요?", "진행해 주실 수 있을지 알려 주세요.", "진행하지 마세요.",
                 "승인하지 않습니다.", "승인합니다. 취소합니다.", "승인합니다. 멈춰 주세요.", "승인합니다. 아직 시작하지 마세요.",
                 "수정안을 설명해 주세요.", "진행해도 될까요?", "진행해 주세요는 예시일 뿐입니다", "do not approve", "승인 여부를 검토해 주세요",
                 "진행해 달라는 요청은 아직 아닙니다.", "진행해 주세요. 지금은 하지 마세요.", "승인하지 말고 먼저 설명만 해 주세요.", "승인합니다. 다만 지금은 시작하지 마세요."]:
        say(text)
        check(f"승인이 아니다: {text}", edit("app.py"))
    for text in ["영어 문구 빼고 진행해주세요", "진행해주세요 영어 문구 빼고", "승인합니다. 다만 영어 문구는 빼고요.",
                 "승인합니다. 다만 취소 버튼은 바꾸지 마세요.", "결제는 바꾸지 말고 진행해 주세요", "진행해 주세요.", "바로 구현해 주세요.",
                 "go ahead.", "네, 진행해 주세요", "추천안대로 승인합니다. 진행해 주세요.", "이 문구 바꾸는 거 진행해 주세요",
                 "로그인 버튼 글자를 '로그인하기'로 바로 바꿔 주세요.", "바로 고쳐 주세요: 로그인 버튼", "진행해 주세요. 테스트는 꼭 돌려 주세요.", "취소 버튼은 바꾸지 말고 진행해 주세요.", "진행해 주세요。"]:
        say(text)
        check(f"승인이다: {text}", not edit("app.py"))
    say("좋습니다. 승인합니다.")
    check("승인 턴: 편집과 셸을 연다", not edit("app.py") and not bash("python3 -m pytest"))
    check("다른 세션의 승인은 쓰지 않는다", call("pre", {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}, "session_id": "s2"}))
    check("session_id 가 없으면 승인이 없는 것으로 본다", call("pre", {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}, "session_id": None}))
    # 승인 수명: 승인은 턴이 아니라 이 작업의 승인 대상에 묶인다. 상태 질문은 유지, 철회·승인 아님이 분명한 승인 말은 닫는다.
    say("어디까지 됐어요?")
    check("승인 뒤 상태 질문(승인 말 없음)은 승인을 유지한다", not edit("app.py"))
    say("테스트는 몇 개 돌렸나요")
    check("승인 뒤 물음표 없는 상태 질문도 승인을 유지한다", not edit("app.py"))
    say("취소합니다.")
    check("철회 메시지는 승인을 닫는다", edit("app.py") and not bash("python3 x.py"))
    say("어디까지 됐어요?")
    check("철회 뒤 상태 질문은 다시 열지 않는다", edit("app.py"))
    say("승인합니다.")
    say("승인하지 않습니다.")
    check("승인 말이 들어 있지만 승인이 아닌 메시지(부정)는 닫는다", edit("app.py"))
    say("승인합니다.")
    say("진행해 주세요?")
    check("승인 말이 든 질문은 닫는다(다시 확인하는 쪽)", edit("app.py"))
    say("승인합니다.")
    say("그런데 재가입은 막아 주세요.")
    check("한계: 지도에 올리지 않은 말뿐인 범위 변경은 관문이 닫지 않는다(검증자가 원문과 대조)", not edit("app.py"))
    say("바로 구현해 주세요: scripts/calc.py 로 두 수의 합")
    check("요청 메시지 안의 '바로 구현' 은 승인이다", not edit("scripts/calc.py"))
    rec_file = lambda sid="s": repo / ".git" / "awk-gate" / (__import__("hashlib").sha256(sid.encode()).hexdigest()[:24] + ".approval")
    rec = lambda sid="s": json.loads(rec_file(sid).read_text())
    check("지도 없는 승인은 대화 안의 계획에 대한 승인으로 기록하고 승인 원문을 남긴다",
          rec()["conversation_only"] and rec()["prompt"].startswith("바로 구현해 주세요") and rec()["targets"] == {})

    # 승인과 작업 지도: 이 세션이 쓴 지도만 연결, 기준 변경(추가·삭제·수정)·지도 삭제·승인 뒤 새 지도는 닫고, 증거 갱신·다른 작업 지도는 영향 없음
    def write_map(path, crit, evidence="", via_tool=True, sid="s"):
        f = repo / path
        if via_tool:
            call("pre", {"tool_name": "Write", "tool_input": {"file_path": str(f)}, "session_id": sid})
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"# 작업\n\n## 기준\n\n{crit}\n\n## 증거\n\n{evidence}\n")
    s2 = lambda text: call("prompt", {"prompt": text, "session_id": "m"})
    edit2 = lambda f: call("pre", {"tool_name": "Edit", "tool_input": {"file_path": f}, "session_id": "m"})
    write_map("work/other/work.md", "| O1 | 다른 작업 |", via_tool=False)  # 다른 세션·사용자가 쓴 다른 작업 지도
    s2("회원 탈퇴를 만들어 주세요.")
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |", sid="m")
    check("승인 전: 지도는 쓸 수 있고 제품 편집은 막힌다", edit2("app.py"))
    s2("추천안대로 승인합니다. 진행해 주세요.")
    check("승인 대상은 이 세션이 쓴 지도만이다(다른 작업 지도는 연결하지 않음)", sorted(rec("m")["targets"]) == ["work/withdraw/work.md"]
          and not rec("m")["conversation_only"])
    check("승인 뒤 제품 편집이 열린다", not edit2("app.py"))
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |", "| W1 | pytest 통과 | 충족 |", sid="m")
    check("승인 뒤 `## 증거` 만 갱신하면 승인이 유지된다", not edit2("app.py"))
    write_map("work/other/work.md", "| O1 | 다른 작업 | 바뀜 |", via_tool=False)
    s2("어디까지 됐어요?")
    check("다른 작업의 지도가 (이 세션의 턴 밖에서) 바뀌어도 이 승인은 그대로다", not edit2("app.py"))
    s2("승인합니다.")
    check("다시 승인하면 그때의 기준으로 다시 묶인다", not edit2("app.py"))
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |\n| W2 | 재가입도 막는다 |", sid="m")
    check("승인 뒤 이 작업 지도의 기준에 조건을 더하면 닫힌다", edit2("app.py"))
    s2("어디까지 됐어요?")
    check("기준이 바뀐 채로는 상태 질문으로 다시 열리지 않는다", edit2("app.py"))
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |\n| W2 | 재가입도 막는다 |", "approved: true\n사용자 승인됨", sid="m")
    check("에이전트가 지도 증거에 approved: true·승인됨을 써도 열리지 않는다(사용자 메시지만 연다)", edit2("app.py"))
    s2("승인합니다.")
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |", sid="m")
    check("승인 뒤 기준에서 조건을 지우면 닫힌다", edit2("app.py"))
    s2("승인합니다.")
    (repo / "work/withdraw/work.md").unlink()
    check("승인 뒤 승인 대상 지도를 (셸로) 지우면 닫힌다", edit2("app.py"))
    s2("진행해 주세요: work/withdraw 다시 만들고 진행")
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인 불가 |", sid="m")
    check("기준이 있는 지도를 승인 뒤 다시 만들면 닫힌다", edit2("app.py"))
    s2("work/withdraw/work.md 기준대로 승인합니다.")
    check("승인 메시지가 지도 경로를 가리키면 그 근거와 함께 대상으로 묶는다",
          rec("m")["targets"].get("work/withdraw/work.md") in ("승인 메시지가 경로로 가리킴", "승인 전에 이 세션이 쓴 지도") and not edit2("app.py"))
    write_map("work/extra/work.md", "| X1 | 승인 뒤 새로 정한 범위 |", via_tool=False)
    check("승인 뒤 이 세션의 턴 동안 (셸로) 새 지도를 쓰면 보호 없이 넘어가지 않고 닫힌다", edit2("app.py"))
    stop_m = subprocess.run([sys.executable, "-I", str(GATE), "stop"], capture_output=True, text=True,
                            input=json.dumps({"cwd": str(repo), "session_id": "m"}))
    check("기준 변경으로 닫힌 턴 끝에는 (제품 변경이 없으면) 막지 않는다", '"block"' not in stop_m.stdout)
    import shutil
    shutil.rmtree(repo / "work")
    say("취소합니다.")  # 아래 턴 끝 검사들은 승인이 닫힌 세션 s 에서 본다

    def stop_reason():
        r = subprocess.run([sys.executable, "-I", str(GATE), "stop"], capture_output=True, text=True,
                           input=json.dumps({"cwd": str(repo), "session_id": "s"}))
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return out.get("reason", "") if out.get("decision") == "block" else ""
    stop = lambda: bool(stop_reason())
    say("검색만 해 주세요.")
    check("승인 없는 턴에 제품 파일이 그대로면 턴을 끝낼 수 있다", not stop())
    (repo / "app.py").write_text("hidden write\n")
    reason = stop_reason()
    check("승인 없는 턴에 셸 쓰기로 제품 파일이 바뀌면 턴 끝에 그 파일 이름을 알린다", "app.py" in reason)
    check("관문은 바뀐 파일을 되돌리지 않고, 일괄 되돌리기를 시키지 않는다",
          (repo / "app.py").read_text() == "hidden write\n" and "일괄 되돌리기 금지" in reason and "확실한 파일만" in reason)
    import hashlib
    blocks_file = repo / ".git" / "awk-gate" / (hashlib.sha256(b"s").hexdigest()[:24] + ".blocks")
    check("같은 턴 끝에 두 번 불려도(전역·프로젝트 훅) 같은 판단을 내고 알림 횟수는 한 번만 센다",
          stop() and blocks_file.read_text().strip() == "1")
    (repo / "work").mkdir(exist_ok=True); (repo / "app.py").unlink(); (repo / "work" / "w.md").write_text("x")
    say("검색만 해 주세요.")
    (repo / "work" / "w.md").write_text("y")
    check("work/ 기록만 바뀌면 막지 않는다", not stop())
    # 사용자가 턴 시작 전에 만든 미커밋 변경은 알림 대상이 아니고 내용도 그대로 남는다
    (repo / "user.txt").write_text("사용자 작업 중\n")
    say("검색만 해 주세요.")
    (repo / "agent.txt").write_text("에이전트가 셸로 씀\n")
    reason = stop_reason()
    check("턴 시작 전부터 있던 사용자 변경은 알림에 넣지 않고 그대로 둔다",
          "agent.txt" in reason and "user.txt" not in reason and (repo / "user.txt").read_text() == "사용자 작업 중\n")
    (repo / "agent.txt").unlink(); (repo / "user.txt").unlink()
    # 생성물은 프로젝트 .gitignore 가 정한다(언어별 예외 없음): 무시되지 않은 캐시는 제품 파일 변화로 보고, 무시된 것은 보지 않는다
    say("검사만 해 주세요.")
    (repo / "build").mkdir(); (repo / "build" / "out.o").write_bytes(b"\0")
    check("프로젝트가 무시하지 않은 생성물은 변경으로 알린다", "build/out.o" in stop_reason())
    (repo / ".gitignore").write_text("build/\n")
    say("검사만 해 주세요.")
    (repo / "build" / "out2.o").write_bytes(b"\0")
    check("프로젝트 .gitignore 가 무시하는 생성물은 보지 않는다", not stop())
    (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x=1\n")
    check("생성물과 함께 제품 파일이 생기면 알린다", "src/a.py" in stop_reason())
    (repo / "src" / "a.py").unlink()
    (repo / "keep.txt").write_text("k\n"); subprocess.run(["git", "add", "keep.txt"], cwd=repo)
    say("검사만 해 주세요.")
    (repo / "keep.txt").unlink()
    check("승인 없는 턴에 셸이 지운 제품 파일도 알린다", "keep.txt" in stop_reason())
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
