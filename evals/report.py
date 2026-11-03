"""evals 결과 폴더의 *.meta.json 을 모아 사례·키트 커밋·하네스별 통과 수를 표로 보여 준다.

같은 사례·하네스를 비교하는 실행끼리 전역 지침 지문이 다르면 경고한다(그 비교는 키트 문장만의 효과가 아니다).
상시 읽는 AGENTS.md 바이트도 커밋별로 보여 줘, 교체가 문서를 무겁게 했는지 함께 본다.
"검토 필요"는 판정 검사가 자동으로 가르지 못해 원시 기록을 사람이 판정해야 하는 실행 수다.
"검증주장 미확인"은 마지막 답이 독립·별도 검증 통과를 주장했지만 기록에 검증자 생성 흔적이 없는 실행 수다(기록이 부족해 볼 수 없으면 세지 않는다).
"외부 장애"는 모델 용량·요청 한도 같은 하네스 밖 원인으로 판정하지 못한 실행 수다. 통과 수의 분모에서 뺀다.
"입력"은 사례의 원래 턴만 보냈는지(original), 사용자 승인 턴(approve.txt)을 더했는지(with-approval)다. 둘은 따로 센다.
"사용자 턴"은 실제로 보낸 사용자 턴 수, "승인 대기"는 그중 승인이 아니어서 쓰기가 막혀 있던 턴 수다(관문 훅 기록 기준).
"관문"은 그 커밋의 설치가 승인 관문 훅을 등록했는지다(같은 사례의 전후 비교에서 실행 조건이 다른지 보인다).
"언어"는 사례를 만든 제품 언어(EVALS_LANG, 없으면 -)다. 같은 실패 종류를 언어별로 나눠 센다.
"통과"는 사례 판정(그 단계의 기대 행동)이고, "검증 완료"는 독립 검증이 정해진 형식으로 모든 조건 충족을 낸 실행 수다(EVALS_VERIFY=1 일 때만).
"답 대기"는 끝난 때 승인 관문이 사용자 답을 기다리던 실행(completion=waiting-user: 승인 전이거나 사용자 철회·기준 변경으로 닫힘)이다.
구현 실패·검증 실패와 다른 미완료이며 완료로 세지 않는다.
"미완료"는 재검증 한도에 닿았거나 교정 턴이 실패했거나, 검증자는 OK 였지만 사례의 결정적 행동 검사가 실패한 실행(completion=check-failed), "검증 미확인"은 빈 답·형식 오류·조건 누락·검증자 오류·검증자의 수정으로 판정이 무효인 실행이다.
승인 대기 단계의 통과는 구현 완료가 아니므로 검증 완료와 합치지 않는다.

사용: python3 -I evals/report.py evals/results [evals/results/20261102 ...]
"""
import json, sys
from collections import defaultdict
from pathlib import Path

rows = defaultdict(list)
for root in sys.argv[1:] or ["evals/results"]:
    for meta in Path(root).rglob("*.meta.json"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        rows[(m["case"], m.get("lang") or "-", m["harness"], m["kit_commit"][:7], m.get("input", "original"))].append(m)

print(f"{'사례':<22} {'언어':<6} {'하네스':<7} {'키트':<8} {'입력':<13} {'사용자 턴':>5} {'승인 대기':>5} {'통과':>5} {'검토 필요':>6} {'검증주장 미확인':>9} {'하네스 실패':>8} {'외부 장애':>6} {'관문':>4} {'검증 완료':>6} {'답 대기':>5} {'미완료':>4} {'검증 미확인':>6} {'평균 초':>7} {'AGENTS.md 바이트':>16}")
fingerprints = defaultdict(set)
for (case, lang, harness, commit, inp), ms in sorted(rows.items()):
    skipped = sum(m.get("check_unverified", False) for m in ms)
    judged = len(ms) - skipped
    passed = sum(m["check_passed"] for m in ms)
    crashed = sum(m["exit_code"] != 0 and not m.get("check_unverified", False) for m in ms)
    gate = "/".join(sorted({"on" if m.get("approval_gate") else "off" for m in ms}))
    review = sum(m.get("check_needs_review", False) for m in ms)
    unverified = sum(m.get("observed", {}).get("independent_claim_unverified", False) for m in ms)
    seconds = sum(m["seconds"] for m in ms) // len(ms)
    verified = sum(m.get("completion") == "verified" for m in ms)
    incomplete = sum(m.get("completion") in ("incomplete", "check-failed") for m in ms)
    vunverified = sum(m.get("completion") == "unverified" for m in ms)
    waiting = sum(m.get("completion") == "waiting-user" for m in ms)
    turns = "/".join(sorted({str(m.get("user_turns", "?")) for m in ms}))
    waits = "/".join(sorted({str(m.get("unapproved_turns", "?")) for m in ms}))
    print(f"{case:<22} {lang:<6} {harness:<7} {commit:<8} {inp:<13} {turns:>5} {waits:>5} {passed:>2}/{judged:<2} {review:>6} {unverified:>9} {crashed:>8} {skipped:>6} {gate:>4} {verified:>6} {waiting:>5} {incomplete:>4} {vunverified:>6} {seconds:>7} {ms[0]['agents_md_bytes']:>16}")
    for m in ms:
        fingerprints[(case, harness)].add(json.dumps(m["global_instructions"], sort_keys=True))

for (case, harness), prints in sorted(fingerprints.items()):
    if len(prints) > 1:
        print(f"경고: {case}/{harness} 실행들의 전역 지침이 서로 다르다. 이 비교는 키트 문장만의 효과로 볼 수 없다.")
