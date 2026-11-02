"""결정 표 관문(wf-design/decision-gate.py)을 모델 없이 시험한다. selftest.sh 가 부른다."""
import json, subprocess, sys, tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / ".agents/skills/wf-design/decision-gate.py"
ok = failed = 0


def check(name, cond):
    global ok, failed
    ok, failed = (ok + 1, failed) if cond else (ok, failed + 1)
    print(("ok   " if cond else "FAIL ") + "gate: " + name)


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    repo = t / "repo"; repo.mkdir()
    run = lambda *c: subprocess.run(c, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q"); (repo / "app.py").write_text("x = 1\n"); (repo / "README.md").write_text("계약: 모든 할 일을 CSV 로\n")
    run("git", "add", "-A"); run("git", "-c", "user.name=t", "-c", "user.email=t@i", "commit", "-qm", "i")
    tr = t / "t.jsonl"
    msgs = ["완료한 할 일은 목록에서 안 보이게 해 주세요.", "사실 보관함으로 옮기라는 뜻이었어요.", "[decision-gate] 훅 지시: 보관함 조회는 archive"]
    tr.write_text("".join(json.dumps({"type": "user", "message": {"content": m}}, ensure_ascii=False) + "\n" for m in msgs))

    def gate(mode, answer="", session="s"):
        p = {"cwd": str(repo), "transcript_path": str(tr), "session_id": session, "last_assistant_message": answer}
        r = subprocess.run([sys.executable, "-I", str(GATE), mode], input=json.dumps(p), capture_output=True, text=True)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return out.get("decision") == "block", out.get("reason", "")

    gate("prompt")
    blocked, _ = gate("stop", "물어볼 게 있습니다. 어떻게 할까요?")
    check("제품 파일을 바꾸지 않은 턴은 표 없이 통과", not blocked)

    (repo / "app.py").write_text("x = 2\n")
    blocked, reason = gate("stop", "구현했습니다.")
    check("바꿨는데 결정 표가 없으면 막는다", blocked and "결정 표가 없" in reason)

    ans = '구현했습니다.\n\n결정 표\n- 완료 항목을 보관함으로 옮김 | 원문 "보관함으로 옮기라는 뜻"\n- CSV 에 모든 할 일 | 계약 README.md\n'
    blocked, _ = gate("stop", ans)
    check("원문 인용이 사용자 말에 있고 계약 경로가 있으면 통과", not blocked)

    blocked, reason = gate("stop", '결정 표\n- 보관함은 archive 명령으로 조회 | 원문 "보관함 조회는 archive"\n')
    check("훅 지시문에만 있는 말을 원문으로 인용하면 막는다", blocked and "그대로 없" in reason)

    blocked, reason = gate("stop", '결정 표\n- CSV 유지 | 계약 docs/없는파일.md\n')
    check("없는 계약 경로는 막는다", blocked and "저장소에 없" in reason)

    blocked, reason = gate("stop", '보관함 조회 방식을 정해 주세요?\n\n결정 표\n- 보관함 조회 방식 | 미확인\n', session="u")
    check("미확인이 있는데 이번 턴에 바꿨으면 되돌리게 막는다", blocked and "되돌리고" in reason)

    blocked, reason = gate("stop", '구현했습니다.\n\n결정 표\n- 보관함 조회 방식 | 미확인\n', session="u2")
    check("미확인이 있는데 질문으로 끝나지 않으면 막는다", blocked and "질문으로 끝나지" in reason)

    gate("prompt", session="v")  # 변경된 상태에서 턴 시작
    blocked, _ = gate("stop", '보관함 조회는 어떻게 할까요?\n\n결정 표\n- 보관함 조회 방식 | 미확인\n', session="v")
    check("이번 턴에 바꾸지 않고 미확인을 물으면 통과", not blocked)

    blocked, reason = gate("stop", '결정 표\n- 보관함 조회 | 추천안\n', session="w")
    check("출처 종류가 원문·계약·미확인이 아니면 막는다", blocked and "중 하나가 아닙니다" in reason)

    for _ in range(3):
        gate("stop", "구현했습니다.", session="x")
    blocked, _ = gate("stop", "구현했습니다.", session="x")
    check("한 턴에 막는 횟수는 한도까지만", not blocked)

print(f"gate {ok} passed, {failed} failed")
sys.exit(1 if failed else 0)
