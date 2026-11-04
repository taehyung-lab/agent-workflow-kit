"""승인 관문(wf-design/approval-gate.py)을 모델 없이 시험한다. selftest.sh 가 부른다."""
import hashlib, json, subprocess, sys, tempfile
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

    import os

    def call(mode, payload, env=None):
        p = {"cwd": str(repo), "session_id": "s", **payload}
        r = subprocess.run([sys.executable, "-I", str(GATE), mode], input=json.dumps(p), capture_output=True, text=True,
                           env={**os.environ, **(env or {})})
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
    # 승인 말의 수명(지도 승인으로 본다): 상태 질문은 유지, 철회·승인 아님이 분명한 승인 말은 닫는다.
    call("pre", {"tool_name": "Write", "tool_input": {"file_path": str(repo / "work/head/work.md")}})
    (repo / "work/head").mkdir(parents=True, exist_ok=True); (repo / "work/head/work.md").write_text("## 기준\n| H1 | 결과 |\n")
    stopq = lambda: subprocess.run([sys.executable, "-I", str(GATE), "stop"], input=json.dumps({"cwd": str(repo), "session_id": "s"}), capture_output=True, text=True)
    say("승인합니다."); stopq()
    say("어디까지 됐어요?")
    check("지도 승인 뒤 상태 질문(승인 말 없음)은 승인을 유지한다", not edit("app.py"))
    say("테스트는 몇 개 돌렸나요")
    check("지도 승인 뒤 물음표 없는 상태 질문도 승인을 유지한다", not edit("app.py"))
    say("취소합니다.")
    check("철회 메시지는 승인을 닫는다", edit("app.py") and not bash("python3 x.py"))
    say("어디까지 됐어요?")
    check("철회 뒤 상태 질문은 다시 열지 않는다", edit("app.py"))
    say("승인합니다.")
    check("철회 뒤 다시 승인하면 지난 승인의 지도에 다시 묶인다", not edit("app.py"))
    say("승인하지 않습니다.")
    check("승인 말이 들어 있지만 승인이 아닌 메시지(부정)는 닫는다", edit("app.py"))
    say("승인합니다.")
    say("진행해 주세요?")
    check("승인 말이 든 질문은 닫는다(다시 확인하는 쪽)", edit("app.py"))
    say("승인합니다."); stopq()
    say("그런데 재가입은 막아 주세요.")
    check("한계: 지도에 올리지 않은 말뿐인 범위 변경은 관문이 닫지 않는다(검증자가 원문과 대조)", not edit("app.py"))
    import shutil as _sh; _sh.rmtree(repo / "work")
    say("취소합니다.")
    say("바로 구현해 주세요: scripts/calc.py 로 두 수의 합")
    check("요청 메시지 안의 '바로 구현' 은 승인이다", not edit("scripts/calc.py"))
    # ---- 승인 수명: 대화 승인은 그 턴만, 지도 승인은 그 지도의 `## 기준`이 그대로인 동안 ----
    import shutil
    shutil_rm = lambda p: shutil.rmtree(p, ignore_errors=True)
    hk = lambda sid: hashlib.sha256(sid.encode()).hexdigest()[:24]
    rec = lambda sid="s": json.loads((repo / ".git" / "awk-gate" / (hk(sid) + ".approval")).read_text())
    tp = lambda sid, text: call("prompt", {"prompt": text, "session_id": sid})
    ed = lambda sid, f="app.py": call("pre", {"tool_name": "Edit", "tool_input": {"file_path": f}, "session_id": sid})

    def stop_of(sid):
        r = subprocess.run([sys.executable, "-I", str(GATE), "stop"], capture_output=True, text=True,
                           input=json.dumps({"cwd": str(repo), "session_id": sid}))
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return out.get("reason", "") if out.get("decision") == "block" else ""

    def write_map(path, row, sid, extra=""):
        """에이전트가 수정 도구로 지도를 쓰는 것처럼: pre 훅을 거친 뒤 파일을 쓴다."""
        call("pre", {"tool_name": "Write", "tool_input": {"file_path": str(repo / path)}, "session_id": sid})
        p = repo / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# 지도\n\n## 기준\n\n원문: 요청\n\n| ID | 결과 |\n| --- | --- |\n{row}\n\n## 증거\n{extra}\n")

    def status(sid):
        r = subprocess.run([sys.executable, "-I", str(GATE), "status", "--session", sid], cwd=repo, capture_output=True, text=True)
        return json.loads(r.stdout or "{}")

    # 대화 승인(작은 일): 그 턴에만 유효하다
    tp("c1", "저장 버튼 색을 파란색으로 바꿔 주세요.")
    check("대화 승인 전: 편집을 막는다", ed("c1"))
    tp("c1", "진행해주세요")
    check("대화 승인: 지도 없이 승인하면 대화 승인으로 연다", rec("c1")["kind"] == "conversation" and not ed("c1"))
    (repo / "app.py").write_text("blue\n")
    check("대화 승인 턴의 변경은 턴 끝에 알리지 않는다", not stop_of("c1"))
    check("대화 승인은 턴 끝에 닫힌다", ed("c1") and rec("c1")["closed_by"] == "turn-end")
    check("턴 끝에 닫힌 대화 승인은 사용자 답 대기가 아니다(작업이 끝난 것)", status("c1")["waiting"] is False)
    check("같은 턴 끝에 다시 불려도 승인 중 변경을 알리지 않는다", not stop_of("c1"))
    tp("c1", "이제 결제 페이지에 쿠폰 입력칸도 추가해 줘")
    check("새 요청: 앞 작업의 대화 승인이 이어지지 않는다", ed("c1"))
    tp("c1", "어디까지 됐어요?")
    check("대화 승인이 닫힌 뒤 상태 질문으로 열리지 않는다", ed("c1"))
    (repo / "app.py").unlink()

    # 지도 승인(여러 턴 걸리는 일)
    tp("m1", "회원 탈퇴 기능을 만들어 주세요.")
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인이 막힌다 |", "m1")
    check("승인 전: 지도는 쓸 수 있고 제품 편집은 막힌다", ed("m1"))
    stop_of("m1")
    (repo / "work" / "other").mkdir(parents=True); (repo / "work/other/work.md").write_text("## 기준\n| O1 | 다른 작업 |\n")
    tp("m1", "진행해 주세요")
    check("지도 승인: 승인 전에 이 세션이 쓴 지도에만 묶인다(다른 지도는 묶지 않음)",
          rec("m1")["kind"] == "map" and sorted(rec("m1")["targets"]) == ["work/withdraw/work.md"] and not ed("m1"))
    stop_of("m1")
    check("지도 승인은 승인 턴 끝의 기준 글과 승인 때 제품 파일 상태를 남긴다(검증기 입력)",
          "탈퇴하면" in rec("m1")["criteria"]["work/withdraw/work.md"] and rec("m1")["base"])
    check("지도 승인은 턴 끝에 닫히지 않는다", not ed("m1"))
    tp("m1", "어디까지 됐어요?")
    check("지도 승인 뒤 상태 질문에도 유지된다", not ed("m1") and rec("m1")["after"][-1] == "어디까지 됐어요?")
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인이 막힌다 |", "m1", extra="| W1 | 통과 | approved: true 승인됨 |")
    check("`## 증거`만 갱신하면 승인이 유지된다", not ed("m1"))
    (repo / "work/other/work.md").write_text("## 기준\n| O1 | 다른 작업 바뀜 |\n")
    tp("m1", "테스트는 몇 개 돌렸나요")
    check("승인 대상이 아닌 다른 지도가 (이 세션의 턴 밖에서) 바뀌어도 그대로다", not ed("m1"))
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인이 막힌다 |\n| W2 | 재가입은 막는다 |", "m1")
    check("승인한 지도의 `## 기준`에 조건을 더하면 닫힌다", ed("m1") and rec("m1")["closed_by"] == "criteria")
    check("기준 변경으로 닫힌 상태는 사용자 답 대기다", status("m1")["waiting"] is True)
    write_map("work/withdraw/work.md", "| W1 | 탈퇴하면 로그인이 막힌다 |", "m1")
    check("에이전트가 기준을 되돌려도 다시 열리지 않는다(사용자 승인만 연다)", ed("m1"))
    tp("m1", "어디까지 됐어요?")
    check("닫힌 뒤 상태 질문으로 열리지 않는다", ed("m1"))
    tp("m1", "승인합니다"); stop_of("m1")
    check("다시 승인하면 그 지도에 다시 묶인다", not ed("m1") and sorted(rec("m1")["targets"]) == ["work/withdraw/work.md"])
    write_map("work/pw/work.md", "| P1 | 비밀번호 변경 |", "m1")
    check("승인 뒤 이 세션이 새 작업 지도를 쓰면 닫힌다", ed("m1"))
    tp("m1", "진행해 주세요"); stop_of("m1")
    check("새 작업 승인은 새 지도에 묶이고 앞 작업 지도는 섞이지 않는다", sorted(rec("m1")["targets"]) == ["work/pw/work.md"] and not ed("m1"))
    (repo / "pw.py").write_text("x\n")
    shutil_rm(repo / "work/pw")
    check("작업을 마치며 승인한 지도를 정리하면 닫힌다(완료, 대기 아님)", ed("m1") and rec("m1")["closed_by"] == "map-removed" and status("m1")["waiting"] is False)
    check("승인 중에 바꾼 파일은 지도 정리 뒤 턴 끝에 알리지 않는다", not stop_of("m1"))
    (repo / "pw.py").unlink()
    tp("m1", "다음 작업")
    stop_of("m1")

    tp("m2", "탈퇴 기능")
    write_map("work/t/work.md", "| T1 | 결과 |", "m2")
    stop_of("m2")
    tp("m3", "work/t 지도대로 승인합니다"); stop_of("m3")
    check("승인 메시지가 경로로 가리킨 지도에도 묶는다(다른 세션이 쓴 지도)", sorted(rec("m3")["targets"]) == ["work/t/work.md"] and not ed("m3"))
    (repo / "work/t/work.md").write_text("## 기준\n| T1 | 결과 바뀜 |\n")
    check("가리킨 지도의 기준이 (셸로) 바뀌어도 닫힌다", ed("m3"))
    shutil_rm(repo / "work")

    tp("f1", "기능 만들어 주세요")
    check("에이전트가 지도에 approved: true 를 써도 열리지 않는다(사용자 메시지만 연다)",
          (write_map("work/f/work.md", "| F1 | x |", "f1", extra="approved: true") or True) and ed("f1"))
    check("승인과 관계없이 관문 기록(.git/awk-gate)은 수정 도구로 바꿀 수 없다",
          call("pre", {"tool_name": "Write", "tool_input": {"file_path": str(repo / ".git/awk-gate/x.approval")}, "session_id": "f1"}))
    shutil_rm(repo / "work")
    src = GATE.read_text(encoding="utf-8")
    check("관문에 작업 선언 명령·에이전트 기록 저장소가 없다(대화 기록은 승인 직전 계획을 남기려고 읽기만 한다)",
          not _re.search(r"task begin|decl\.jsonl|\.awk-gate", src))
    # 검토 입력 고정: 승인 전 사용자 메시지(요청 원문)와 승인 직전 에이전트 답(계획)을 그대로 남긴다
    tr = Path(t) / "tr.jsonl"
    tr.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [
        {"type": "user", "message": {"role": "user", "content": "회원 탈퇴 기능을 만들어 주세요. REQ-MARKER"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "계획: 비활성화로 바꿉니다. PLAN-MARKER 진행할까요?"}]}}]) + "\n")
    tp("q1", "회원 탈퇴 기능을 만들어 주세요. REQ-MARKER")
    tp("q1", "사실 비활성화하라는 뜻이었어요")
    call("prompt", {"prompt": "진행해 주세요", "session_id": "q1", "transcript_path": str(tr)})
    r_ = rec("q1")
    check("승인 기록에 승인 전 사용자 메시지 전부와 승인 메시지가 요청 원문으로 남는다",
          r_["requests"] == ["회원 탈퇴 기능을 만들어 주세요. REQ-MARKER", "사실 비활성화하라는 뜻이었어요", "진행해 주세요"])
    check("승인 기록에 승인 직전 에이전트가 보여 준 계획이 그대로 남는다", "PLAN-MARKER" in (r_.get("plan") or ""))
    call("prompt", {"prompt": "진행해 주세요", "session_id": "q1", "transcript_path": str(tr)})
    check("릴리스 검토 P1: 같은 사건의 두 번째 훅 호출은 요청 원문을 지우지 않는다", rec("q1")["requests"][0] == "회원 탈퇴 기능을 만들어 주세요. REQ-MARKER")
    stop_of("q1")
    # 지도 승인이 열린 채 추가 요구 → 계속 진행 승인 / 기준 변경 뒤 재승인: 이번 작업의 첫 원문부터 모두 남는다
    tp("q4", "회원 탈퇴 ORIGINAL-REQ"); write_map("work/q4/work.md", "| Q1 | 탈퇴 |", "q4"); stop_of("q4")
    tp("q4", "진행해 주세요"); stop_of("q4")
    tp("q4", "고객 정보도 지워 주세요 AFTER-REQ"); tp("q4", "계속 진행해주세요")
    check("릴리스 검토 P1: 열린 지도에서 추가 요구 뒤 계속 진행 승인해도 첫 원문·추가 요구가 남는다",
          rec("q4")["requests"][0] == "회원 탈퇴 ORIGINAL-REQ" and "고객 정보도 지워 주세요 AFTER-REQ" in rec("q4")["requests"])
    stop_of("q4"); write_map("work/q4/work.md", "| Q1 | 탈퇴 |\n| Q2 | 고객 정보 삭제 |", "q4"); tp("q4", "승인합니다")
    check("릴리스 검토 P1: 기준 변경 뒤 재승인에도 첫 원문이 남는다", rec("q4")["requests"][0] == "회원 탈퇴 ORIGINAL-REQ")
    stop_of("q4"); shutil_rm(repo / "work")
    call("prompt", {"prompt": "DUP-REQ 요청", "session_id": "q5"}); call("prompt", {"prompt": "승인합니다", "session_id": "q5"})
    call("prompt", {"prompt": "승인합니다", "session_id": "q5"})
    check("릴리스 검토 P1: 대화 기록 없이 같은 승인이 바로 두 번 와도 원문이 남는다", rec("q5")["requests"] == ["DUP-REQ 요청", "승인합니다"])
    stop_of("q5")
    # 재확인2 C: Stop 없이 다음 요청 → 재승인해도 그 요청이 원문에 남는다
    tp("q6", "첫 요청"); tp("q6", "진행해 주세요"); tp("q6", "NEW-REQ 새 요청"); tp("q6", "승인합니다")
    check("재확인2 C: Stop 이 빠져도 다음 승인의 원문에 새 요청이 남는다", rec("q6")["requests"] == ["NEW-REQ 새 요청", "승인합니다"])
    stop_of("q6")
    # 재확인2 D: 기록 손상 → 철회가 무시되지 않고(닫힘) 원문 불완전 표시
    lg = lambda sid: repo / ".git" / "awk-gate" / (hk(sid) + ".prompts.jsonl")
    tp("q7", "탈퇴 기능"); write_map("work/q7/work.md", "| Q7 | 탈퇴 |", "q7"); stop_of("q7"); tp("q7", "승인합니다"); stop_of("q7")
    with open(lg("q7"), "a") as fh: fh.write("[]\n")
    tp("q7", "취소합니다")
    check("재확인2 D: 기록에 이상한 줄이 있어도 철회가 적용되고 수정 도구를 막는다", ed("q7") and rec("q7")["approved"] is False)
    shutil_rm(repo / "work")
    # 재확인3: 같은 승인 사건의 중복 훅은 대화 승인을 닫지 않는다
    tp("q9", "버튼 문구 바꿔 주세요"); tp("q9", "진행해 주세요"); tp("q9", "진행해 주세요")
    check("재확인3: 중복 훅 호출 뒤에도 대화 승인이 열려 있다", rec("q9")["approved"] is True and not ed("q9"))
    stop_of("q9")
    # 재확인3: 기록 입출력 오류(잘못된 UTF-8, 파일 자리에 폴더)에서도 철회가 적용된다
    for sid_, breaker in (("qa", lambda f: open(f, "ab").write(b"\xff\n")), ("qb", lambda f: (f.unlink(), f.mkdir()))):
        tp(sid_, "탈퇴 기능"); write_map(f"work/{sid_}/work.md", "| Q | 탈퇴 |", sid_); stop_of(sid_); tp(sid_, "승인합니다"); stop_of(sid_)
        breaker(lg(sid_))
        tp(sid_, "취소합니다")
        check(f"재확인3: 기록 입출력 오류({sid_})에서도 철회가 적용되어 수정 도구를 막는다", ed(sid_) and rec(sid_)["approved"] is False)
        shutil_rm(repo / "work")
    tp("q8", "ORIG 요청"); lg("q8").unlink(); tp("q8", "진행해 주세요")
    check("재확인2 D: 승인 전에 기록이 없어지면 원문 불완전으로 표시한다", rec("q8").get("requests_incomplete") is True)
    stop_of("q8")
    tp("q3", "FIRST-REQ 원래 요청"); tp("q3", "IMPORTANT-REQ 개인정보 영구 삭제")
    for i in range(45):
        tp("q3", f"질문 답변 {i}")
    tp("q3", "진행해 주세요")
    check("릴리스 검토 P1: 승인 전 메시지가 길어도 줄이지 않는다(첫 원문·가운데 중요한 요구 모두 남음)",
          rec("q3")["requests"][0] == "FIRST-REQ 원래 요청" and "IMPORTANT-REQ 개인정보 영구 삭제" in rec("q3")["requests"] and len(rec("q3")["requests"]) == 48)
    stop_of("q3")
    tp("q2", "버튼 바꿔 주세요"); tp("q2", "진행해 주세요")
    check("대화 기록이 없으면 계획은 비어 있다(검토기가 입력 부족으로 다룬다)", rec("q2").get("plan") is None and rec("q2")["requests"] == ["버튼 바꿔 주세요", "진행해 주세요"])

    # 승인 턴 안의 옮겨 적기: "추천안대로 진행"으로 정한 결정을 지도에 옮겨도 닫히지 않고, 턴 끝의 기준에 묶인다
    tp("b1", "할 일 숨기기")
    write_map("work/b/work.md", "| B1 | 숨기기 |", "b1"); stop_of("b1")
    tp("b1", "추천안대로 승인합니다. 진행해 주세요.")
    write_map("work/b/work.md", "| B1 | 보관함으로 옮김(추천안) |", "b1")
    check("승인 턴에 지도 기준을 고쳐도(결정 옮겨 적기) 닫히지 않는다", not ed("b1"))
    stop_of("b1")
    check("승인 턴 끝의 기준에 묶인다", "보관함" in rec("b1")["criteria"]["work/b/work.md"] and rec("b1")["kind"] == "map")
    write_map("work/b/work.md", "| B1 | 보관함으로 옮김(추천안) |\n| B2 | 추가 |", "b1")
    check("승인 턴 뒤의 기준 변경은 닫는다", ed("b1"))
    shutil_rm(repo / "work")
    tp("b2", "버튼 문구 바꿔 주세요"); tp("b2", "진행해주세요")
    write_map("work/b2/work.md", "| C1 | 문구 |", "b2")
    stop_of("b2")
    check("대화로 승인한 턴에 쓴 지도는 그 지도 승인이 된다(옮겨 적기, 다음 턴에도 유지)", rec("b2")["kind"] == "map" and not ed("b2"))
    shutil_rm(repo / "work")
    # Codex 반례 회귀 표본
    tp("x1", "기능"); write_map("work/x/work.md", "| X1 | A |", "x1"); stop_of("x1"); tp("x1", "승인합니다"); stop_of("x1")
    (repo / "work/x/work.md").write_text("## 기준\n| X1 | B |\n")
    tp("x1", "어디까지 됐어요?")
    (repo / "work/x/work.md").write_text("# 지도\n\n## 기준\n\n원문: 요청\n\n| ID | 결과 |\n| --- | --- |\n| X1 | A |\n\n## 증거\n\n")
    check("반례1: 턴 사이에 바뀐 기준은 다음 메시지에서 닫힘으로 남는다(되돌려도 열리지 않음)", ed("x1"))
    tp("x1", "승인합니다"); stop_of("x1")
    call("pre", {"tool_name": "Bash", "tool_input": {"command": "x"}, "session_id": "x1"})
    (repo / "work/x/work.md").write_text("## 기준\n| X1 | B |\n"); (repo / "late.txt").write_text("x\n")
    r = stop_of("x1")
    check("반례2: 기준 변경과 함께 셸로 쓴 제품 파일도 턴 끝에 알리고, 승인 중 변경은 그대로 두라고 한다", "late.txt" in r and "승인이 열려 있을 때 바꾼 것은 그대로" in r)
    (repo / "late.txt").unlink(); shutil_rm(repo / "work")
    check("반례3: 관문 기록이 없는 세션은 사용자 답 대기로 세지 않는다", status("none")["waiting"] is False)
    tp("x4", "기능"); write_map("work/y/work.md", "| Y1 | A |", "x4"); stop_of("x4"); tp("x4", "승인합니다"); stop_of("x4")
    call("pre", {"tool_name": "Write", "tool_input": {"file_path": str(repo / "work/n/work.md")}, "session_id": "x4"})
    (repo / "work/n").mkdir(parents=True); (repo / "work/n/work.md").write_text("# 메모\n기준 없음\n")
    check("반례4: `## 기준`이 없는 새 파일은 승인을 닫지 않는다", not ed("x4"))
    check("반례5: 검증 기록(work/<작업명>/verify/)은 승인 뒤에도 수정 도구로 바꿀 수 없다",
          ed("x4", str(repo / "work/y/verify/state.json")) and call("pre", {"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: work/y/verify/state.json\n@@\n-a\n+b\n*** End Patch"}, "session_id": "x4"}))
    shutil_rm(repo / "work")

    # 재검토 반례: 다른 세션이 쓴 지도·셸로 만든 지도는 내 승인 대상으로 묶지 않는다(대화 승인으로 닫힘, 다시 묻는 쪽)
    tp("c3", "기능"); tp("c3", "진행해주세요")
    write_map("work/other-session/work.md", "| O1 | 다른 세션 |", "b9")
    call("pre", {"tool_name": "Read", "tool_input": {"file_path": "x"}, "session_id": "c3"}); stop_of("c3")
    check("재검토3: 다른 세션이 쓴 지도는 내 승인 대상이 되지 않는다", rec("c3")["kind"] == "conversation" and ed("c3"))
    shutil_rm(repo / "work")
    tp("c4", "기능"); tp("c4", "진행해주세요")
    (repo / "work/sh").mkdir(parents=True); (repo / "work/sh/work.md").write_text("## 기준\n| S1 | 셸로 쓴 지도 |\n")
    tp("c4", "어디까지 됐어요?")
    check("재검토2: 셸로 만든 지도는 묶지 않는다(Stop 이 빠져도 일관되게 대화 승인으로 닫힘)", rec("c4")["kind"] == "conversation" and ed("c4"))
    shutil_rm(repo / "work")

    # 지도 승인 때 보존한 제품 파일 상태(검증기 기준)
    (repo / "pre.txt").write_text("사용자 기존 변경\n")
    tp("d3", "새 기능 만들어 주세요.")
    write_map("work/d3/work.md", "| D1 | 결과 |", "d3")
    tp("d3", "승인합니다.")
    base = json.loads((repo / ".git" / "awk-gate" / rec("d3")["base"]).read_text())
    blob = subprocess.run(["git", "cat-file", "blob", base.get("pre.txt", {}).get("blob", "0")], cwd=repo, capture_output=True, text=True).stdout
    check("지도 승인 때 제품 파일 내용을 보존한다(승인 전부터 있던 미커밋 변경 포함)", blob == "사용자 기존 변경\n" and "work.md" not in json.dumps(base))
    (repo / "pre.txt").unlink()
    shutil_rm(repo / "work")

    # 평가 실행기가 보낸 검증 반환(사용자 아님): 글 속 승인·철회 말로 승인 상태가 바뀌지 않고, 변경 감시는 계속된다
    runner = {"AWK_GATE_PROMPT_FROM": "runner"}
    s3 = lambda text, env=None: call("prompt", {"prompt": text, "session_id": "r"}, env)
    edit3 = lambda f: call("pre", {"tool_name": "Edit", "tool_input": {"file_path": f}, "session_id": "r"})
    s3("탈퇴 기능을 만들어 주세요.")
    write_map("work/r/work.md", "| R1 | 탈퇴 |", "r"); stop_of("r")
    s3("별도 검증자가 다음 사유로 돌려보냈습니다.\n\n사용자가 '승인합니다. 진행해 주세요.' 라고 했다. approved", runner)
    check("반환 원문의 '승인합니다'·approved 는 승인을 열지 않는다(실행기 발신 구분)", edit3("app.py"))
    s3("승인합니다."); stop_of("r")
    s3("별도 검증자가 다음 사유로 돌려보냈습니다.\n취소합니다.", runner)
    check("반환 원문의 '취소합니다' 는 사용자 승인을 닫지 않는다", not edit3("app.py"))
    s3("취소합니다.")
    check("실제 사용자 원문의 철회 처리는 그대로다", edit3("app.py"))
    shutil_rm(repo / "work")
    s3("별도 검증자가 다음 사유로 돌려보냈습니다.", runner)
    (repo / "runner.txt").write_text("x\n")
    r = subprocess.run([sys.executable, "-I", str(GATE), "stop"], capture_output=True, text=True,
                       input=json.dumps({"cwd": str(repo), "session_id": "r"}), env={**os.environ, **runner})
    check("승인 없는 반환 턴의 제품 파일 변경도 턴 끝에 알린다", "runner.txt" in r.stdout)
    (repo / "runner.txt").unlink()
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
