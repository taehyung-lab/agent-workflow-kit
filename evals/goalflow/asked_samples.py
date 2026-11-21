"""모의 사용자 분류 확인(모델 호출, CI 밖): 실제 답(asked-samples/*.json)에서 모의 사용자가 사람이 읽은 것과 같은 주제를 고르는가.

  python3 -I evals/goalflow/asked_samples.py           평가기를 고치며 보는 표본(holdout 아님)
  python3 -I evals/goalflow/asked_samples.py --final   마지막 확인용 표본까지(평가기 수정에 쓰지 않은 표본)

표본: kind(갈래), task(과제 폴더 이름. goalflow 는 회차 신청), reply(에이전트의 실제 글), expect(꼭 골라야 할 주제), expect_none(골라서는 안 되는 주제), holdout.
갈래(2026-11-16): surfaced 질문·제안으로 드러냄 / implemented 묻지 않고 구현만 보고 / asked-then-implemented 물었지만 같은 턴에 구현(분류는 드러낸 것으로,
판정은 table.py 의 답 전 편집으로 실패) / proceed 근거·답을 받은 뒤 구현을 보고 / review 사람 판독도 모호해 정답으로 세지 않음(결과만 보인다).
holdout 표본은 평가기를 고치는 동안 돌리지 않고, 기대값은 분류기를 돌리기 전에 사람이 글을 읽고 정했다.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from asked import asked  # noqa: E402

final = "--final" in sys.argv
bad = counted = 0
for f in sorted((HERE / "asked-samples").glob("*.json")):
    s = json.loads(f.read_text(encoding="utf-8"))
    if s.get("holdout") and not final:
        continue
    task_dir = HERE if s["task"] == "goalflow" else HERE / "tasks" / s["task"]
    got = asked(s["reply"], (task_dir / "topics.txt").read_text(encoding="utf-8"))
    tag = ("[확인용] " if s.get("holdout") else "") + f"{s['kind']} {f.stem}: 고른 주제 {got}"
    if s["kind"] == "review":
        print("REVIEW " + tag + " (정답으로 세지 않음)")
        continue
    counted += 1
    ok = (bool(got) if s["expect"] == "nonempty" else set(s["expect"]) <= set(got)) and not set(s.get("expect_none", [])) & set(got)
    bad += not ok
    print(("ok   " if ok else "FAIL ") + tag + f", 기대 {s['expect']}, 고르면 안 됨 {s.get('expect_none', [])}")
print(f"{counted} 표본 중 {bad} failed" + (" (확인용 포함)" if final else ""))
sys.exit(1 if bad else 0)
