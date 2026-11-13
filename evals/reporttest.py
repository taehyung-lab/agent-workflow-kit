"""비교 보고의 판단 규칙(report.decide) 시험. 모델을 부르지 않는다.

  python3 -I evals/reporttest.py

통과 수는 관찰이고 두 커밋의 차이는 따로 확인해야 하는 주장이다: 전부 뒤집힌 경우만 차이로 적는지 본다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import decide  # noqa: E402

checks = [
    ("1/3 대 0/3 은 차이가 아니다(말할 수 없음)", decide(1, 3, 0, 3).startswith("말할 수 없음")),
    ("2/3 대 3/3 도 차이가 아니다", decide(2, 3, 3, 3).startswith("말할 수 없음")),
    ("0/3 대 3/3 은 차이: 개선", decide(0, 3, 3, 3).startswith("차이: 개선")),
    ("3/3 대 0/3 은 차이: 퇴보", decide(3, 3, 0, 3).startswith("차이: 퇴보")),
    ("전부 뒤집혀도 한쪽이 1회뿐이면 말할 수 없음", decide(0, 1, 1, 1).startswith("말할 수 없음") and decide(0, 3, 1, 1).startswith("말할 수 없음")),
    ("양쪽 모두 통과는 회귀 확인용(우열을 가르지 못한다)", decide(3, 3, 2, 2).startswith("회귀 확인용")),
    ("양쪽 모두 실패는 재발", decide(0, 2, 0, 3).startswith("재발")),
    ("한쪽에 판정된 실행이 없으면 말할 수 없음", decide(0, 0, 3, 3).startswith("말할 수 없음") and decide(2, 2, 0, 0).startswith("말할 수 없음")),
    ("검토 필요는 사람 판독 대기로 따로 적는다", "사람 판독 대기 2" in decide(3, 3, 3, 3, pending=2) and "사람 판독 대기" not in decide(3, 3, 3, 3)),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
