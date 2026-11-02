"""evals 결과 폴더의 *.meta.json 을 모아 사례·키트 커밋·하네스별 통과 수를 표로 보여 준다.

같은 사례·하네스를 비교하는 실행끼리 전역 지침 지문이 다르면 경고한다(그 비교는 키트 문장만의 효과가 아니다).
상시 읽는 AGENTS.md 바이트도 커밋별로 보여 줘, 교체가 문서를 무겁게 했는지 함께 본다.
"검토 필요"는 판정 검사가 자동으로 가르지 못해 원시 기록을 사람이 판정해야 하는 실행 수다.
"검증주장 미확인"은 마지막 답이 독립·별도 검증 통과를 주장했지만 기록에 검증자 생성 흔적이 없는 실행 수다.

사용: python3 -I evals/report.py evals/results [evals/results/20261102 ...]
"""
import json, sys
from collections import defaultdict
from pathlib import Path

rows = defaultdict(list)
for root in sys.argv[1:] or ["evals/results"]:
    for meta in Path(root).rglob("*.meta.json"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        rows[(m["case"], m["harness"], m["kit_commit"][:7])].append(m)

print(f"{'사례':<22} {'하네스':<7} {'키트':<8} {'통과':>5} {'검토 필요':>6} {'검증주장 미확인':>9} {'하네스 실패':>8} {'평균 초':>7} {'AGENTS.md 바이트':>16}")
fingerprints = defaultdict(set)
for (case, harness, commit), ms in sorted(rows.items()):
    passed = sum(m["check_passed"] for m in ms)
    crashed = sum(m["exit_code"] != 0 for m in ms)
    review = sum(m.get("check_needs_review", False) for m in ms)
    unverified = sum(m.get("observed", {}).get("independent_claim_unverified", False) for m in ms)
    seconds = sum(m["seconds"] for m in ms) // len(ms)
    print(f"{case:<22} {harness:<7} {commit:<8} {passed:>2}/{len(ms):<2} {review:>6} {unverified:>9} {crashed:>8} {seconds:>7} {ms[0]['agents_md_bytes']:>16}")
    for m in ms:
        fingerprints[(case, harness)].add(json.dumps(m["global_instructions"], sort_keys=True))

for (case, harness), prints in sorted(fingerprints.items()):
    if len(prints) > 1:
        print(f"경고: {case}/{harness} 실행들의 전역 지침이 서로 다르다. 이 비교는 키트 문장만의 효과로 볼 수 없다.")
