"""evals 결과 폴더의 *.meta.json 을 모아 사례·키트 커밋·하네스별 통과 수를 표로 보여 준다.

같은 사례·하네스를 비교하는 실행끼리 전역 지침 지문이 다르면 경고한다(그 비교는 키트 문장만의 효과가 아니다).
상시 읽는 AGENTS.md 바이트도 커밋별로 보여 줘, 교체가 문서를 무겁게 했는지 함께 본다.
"검토 필요"는 판정 검사가 자동으로 가르지 못해 원시 기록을 사람이 판정해야 하는 실행 수다.
"검증주장 미확인"은 마지막 답이 독립·별도 검증 통과를 주장했지만 기록에 검증자 흔적이 없거나, 검증 실행기만 돌렸고 그 결과가 ok 가 아닌 실행 수다(기록이 부족하거나 결과를 모르면 세지 않는다).
"실행기 OK(완료)/실행"은 마지막 턴에 구현자가 검증 실행기를 실행한 흔적이 있는 실행 수(결과를 모르는 것 포함)와, 그중 실행기 판정이 ok 인 수,
괄호 안은 실행기가 전체 완료(verified)까지 낸 수다(ok 여도 사용자 답 대기면 waiting-user). 실행 흔적은 성공이 아니며, 이 열은 완료 판정에 쓰지 않는다.
"외부 장애"는 모델 용량·요청 한도 같은 하네스 밖 원인으로 판정하지 못한 실행 수다. 통과 수의 분모에서 뺀다.
"입력"은 사례의 원래 턴만 보냈는지(original), 사용자 승인 턴(approve.txt)을 더했는지(with-approval)다. 둘은 따로 센다.
"첫 답"은 첫 턴 마지막 답 글자 수의 중앙값이다(긴 첫 답변을 변경 전후로 비교하는 측정값, 판정이 아니다. 기록이 없으면 -).
"사용자 턴"은 실제로 보낸 사용자 턴 수다.
"키트"는 설치한 키트 커밋이다. goalflow 구성 비교(goalflow/compare.py)의 스킬 설치·지침 없음 구성은 커밋 대신 구성 이름(skills·none)이 온다.
"언어"는 사례를 만든 제품 언어(EVALS_LANG, 없으면 -)다. 같은 실패 종류를 언어별로 나눠 센다.
"통과"는 사례 판정(그 단계의 기대 행동)이고, "검증 완료"는 독립 검증이 정해진 형식으로 모든 조건 충족을 낸 실행 수다(EVALS_VERIFY=1 일 때만).
"답 대기"는 끝난 때 사용자 답을 기다리던 실행(completion=waiting-user: 요구 기록에 미정이 남음)이다.
구현 실패·검증 실패와 다른 미완료이며 완료로 세지 않는다.
"미완료"는 재검증 한도에 닿았거나 교정 턴이 실패했거나, 검증자는 OK 였지만 사례의 결정적 행동 검사가 실패한 실행(completion=check-failed), "검증 미확인"은 빈 답·형식 오류·조건 누락·검증자 오류·검증자의 수정으로 판정이 무효인 실행이다.
승인 대기 단계의 통과는 구현 완료가 아니므로 검증 완료와 합치지 않는다.

사용: python3 -I evals/report.py evals/results [evals/results/20261102 ...]
     python3 -I evals/report.py --compare <기준 커밋> <대상 커밋> <결과 폴더 ...>   (run.sh <사례> 기준..대상 이 끝에 부른다)

--compare 는 같은 사례·언어·하네스·입력의 두 커밋 실행을 한 줄로 나란히 보인다(통과/판정, 검토 필요, 외부 장애, 답 대기, 첫 답 중앙값).
비교 조건(하네스 버전·전역 지침 지문·판정기 버전)이 다르면 "비교 불가"와 그 항목을 적는다.
표시의 맨 앞은 이 줄로 무엇을 말할 수 있는가다(decide). 통과 수는 그 과제를 그 횟수만큼 돌려 본 관찰이고, 두 커밋의 차이는 따로 확인해야 하는 주장이다.
  "차이: 개선"·"차이: 퇴보"  양쪽을 2회 이상 돌렸고 한쪽은 전부 실패, 다른 쪽은 전부 통과다(전부 뒤집힌 경우만 차이로 적는다).
  "회귀 확인용"              양쪽 모두 전부 통과다. 기준이 이미 통과하는 사례라 두 커밋의 우열을 가르지 못한다.
  "재발"                     양쪽 모두 전부 실패다(검토 필요는 실패로 세지 않는다).
  "말할 수 없음"             섞인 결과이거나 한쪽이 1회뿐이다. 1/3 대 0/3 같은 차이는 같은 커밋을 다시 돌려도 나온다. 횟수를 늘리거나 원시 기록을 본다.
  "사람 판독 대기 N"         검토 필요로 남은 실행이 있다. 읽기 전에는 통과도 실패도 아니다.
같은 원인인지·무엇을 고칠지·채택·되돌리기는 원시 기록을 본 사람이 정한다(자동 수정·자동 되돌리기 없음).
"""
import json, subprocess, sys
from collections import defaultdict
from pathlib import Path


def median_first(ms):
    chars = sorted(m["observed"]["first_reply_chars"] for m in ms if isinstance(m.get("observed", {}).get("first_reply_chars"), int))
    return chars[len(chars) // 2] if chars else None


def decide(base_passed, base_n, target_passed, target_n, pending=0):
    """두 커밋의 통과 수로 무엇을 말할 수 있는가. 판정된 실행(외부 장애 제외) 가운데 검토 필요는 통과도 실패도 아니므로 n 에서 빼고 넘긴다.
    전부 뒤집힌 경우(양쪽 2회 이상, 0/n ↔ n/n)만 차이다. 관찰을 차이로 읽지 않게 하려는 표시이며 통계 검정이 아니다."""
    wait = f", 사람 판독 대기 {pending}" if pending else ""
    if not base_n or not target_n:
        return "말할 수 없음: 한쪽에 판정된 실행이 없다" + wait
    all_b, none_b = base_passed == base_n, base_passed == 0
    all_t, none_t = target_passed == target_n, target_passed == 0
    if all_b and all_t:
        return "회귀 확인용: 양쪽 모두 통과(우열을 가르지 못한다)" + wait
    if none_b and none_t:
        return "재발: 양쪽 모두 실패" + wait
    if (none_b and all_t) or (all_b and none_t):
        if min(base_n, target_n) < 2:
            return "말할 수 없음: 뒤집혔지만 한쪽이 1회뿐이다" + wait
        return ("차이: 개선" if all_t else "차이: 퇴보") + f"(전부 뒤집힘, {base_n}회·{target_n}회)" + wait
    return f"말할 수 없음: 섞인 결과({base_passed}/{base_n}→{target_passed}/{target_n})" + wait


def compare(base, target, roots):
    kit = Path(__file__).resolve().parents[1]
    full = lambda r: subprocess.run(["git", "-C", str(kit), "rev-parse", "--verify", "-q", f"{r}^{{commit}}"], capture_output=True, text=True).stdout.strip() or r
    sides = {"base": full(base), "target": full(target)}
    groups = defaultdict(lambda: {"base": [], "target": []})
    for root in roots:
        for meta in Path(root).rglob("*.meta.json"):
            m = json.loads(meta.read_text(encoding="utf-8"))
            for side, sha in sides.items():
                if m["kit_commit"].startswith(sha[:7]) or sha.startswith(m["kit_commit"][:7]):
                    groups[(m["case"], m.get("lang") or "-", m["harness"], m.get("input", "original"))][side].append(m)
    print(f"기준 {sides['base'][:7]} → 대상 {sides['target'][:7]}")
    print(f"{'사례':<26} {'언어':<4} {'하네스':<7} {'입력':<13} {'통과(기준→대상)':>16} {'검토 필요':>9} {'답 대기':>7} {'첫 답':>11}  표시")
    cell = lambda ms, f: str(sum(f(m) for m in ms))
    for (case, lang, harness, inp), g in sorted(groups.items()):
        b, t = g["base"], g["target"]
        judged = lambda ms: [m for m in ms if not m.get("check_unverified", False)]
        rate = lambda ms: (sum(m["check_passed"] for m in judged(ms)) / len(judged(ms))) if judged(ms) else None
        passed = f"{sum(m['check_passed'] for m in judged(b))}/{len(judged(b))}→{sum(m['check_passed'] for m in judged(t))}/{len(judged(t))}"
        review = f"{cell(b, lambda m: m.get('check_needs_review', False))}→{cell(t, lambda m: m.get('check_needs_review', False))}"
        waiting = f"{cell(b, lambda m: m.get('completion') == 'waiting-user')}→{cell(t, lambda m: m.get('completion') == 'waiting-user')}"
        first = f"{median_first(b) or '-'}→{median_first(t) or '-'}"
        marks = []
        if not b or not t:
            marks.append("한쪽 실행 없음")
        else:
            diff = [k for k, f in (("하네스 버전", lambda m: m.get("harness_version")),
                                   ("전역 지침", lambda m: json.dumps(m.get("global_instructions"), sort_keys=True)), ("판정기", lambda m: m.get("judge_version")))
                    if {f(m) for m in b} != {f(m) for m in t}]
            if diff:
                marks.append("비교 불가: " + "·".join(diff))
            # 검토 필요는 통과도 실패도 아니다: 판단의 횟수에서 빼고 '사람 판독 대기'로 따로 센다.
            settled = lambda ms: [m for m in judged(ms) if not m.get("check_needs_review")]
            pending = sum(bool(m.get("check_needs_review")) for m in judged(b) + judged(t))
            marks.insert(0, decide(sum(m["check_passed"] for m in settled(b)), len(settled(b)),
                                   sum(m["check_passed"] for m in settled(t)), len(settled(t)), pending))
        if any(m.get("check_unverified") for m in b + t):
            marks.append(f"외부 장애 {sum(m.get('check_unverified', False) for m in b + t)}")
        print(f"{case:<26} {lang:<4} {harness:<7} {inp:<13} {passed:>16} {review:>9} {waiting:>7} {first:>11}  {', '.join(marks)}")


def main(argv):
    if len(argv) > 2 and argv[0] == "--compare":
        compare(argv[1], argv[2], argv[3:] or ["evals/results"])
        return 0

    rows = defaultdict(list)
    for root in argv or ["evals/results"]:
        for meta in Path(root).rglob("*.meta.json"):
            m = json.loads(meta.read_text(encoding="utf-8"))
            rows[(m["case"], m.get("lang") or "-", m["harness"], m["kit_commit"][:7], m.get("input", "original"))].append(m)

    print(f"{'사례':<22} {'언어':<6} {'하네스':<7} {'키트':<8} {'입력':<13} {'사용자 턴':>5} {'첫 답':>5} {'통과':>5} {'검토 필요':>6} {'검증주장 미확인':>9} {'실행기 OK(완료)/실행':>14} {'하네스 실패':>8} {'외부 장애':>6} {'검증 완료':>6} {'답 대기':>5} {'미완료':>4} {'검증 미확인':>6} {'평균 초':>7} {'AGENTS.md 바이트':>16}")
    fingerprints = defaultdict(set)
    for (case, lang, harness, commit, inp), ms in sorted(rows.items()):
        skipped = sum(m.get("check_unverified", False) for m in ms)
        judged = len(ms) - skipped
        passed = sum(m["check_passed"] for m in ms)
        crashed = sum(m["exit_code"] != 0 and not m.get("check_unverified", False) for m in ms)
        review = sum(m.get("check_needs_review", False) for m in ms)
        unverified = sum(m.get("observed", {}).get("independent_claim_unverified", False) for m in ms)
        runs = [m.get("observed", {}) for m in ms]
        executor = (f"{sum(o.get('verify_run') == 'ok' for o in runs)}({sum(o.get('verify_run_completion') == 'verified' for o in runs)})"
                    f"/{sum(o.get('verify_run', 'none') != 'none' for o in runs)}")
        seconds = sum(m["seconds"] for m in ms) // len(ms)
        verified = sum(m.get("completion") == "verified" for m in ms)
        incomplete = sum(m.get("completion") in ("incomplete", "check-failed") for m in ms)
        vunverified = sum(m.get("completion") == "unverified" for m in ms)
        waiting = sum(m.get("completion") == "waiting-user" for m in ms)
        turns = "/".join(sorted({str(m.get("user_turns", "?")) for m in ms}))
        chars = sorted(m["observed"]["first_reply_chars"] for m in ms if isinstance(m.get("observed", {}).get("first_reply_chars"), int))
        first = str(chars[len(chars) // 2]) if chars else "-"
        print(f"{case:<22} {lang:<6} {harness:<7} {commit:<8} {inp:<13} {turns:>5} {first:>5} {passed:>2}/{judged:<2} {review:>6} {unverified:>9} {executor:>14} {crashed:>8} {skipped:>6} {verified:>6} {waiting:>5} {incomplete:>4} {vunverified:>6} {seconds:>7} {ms[0]['agents_md_bytes']:>16}")
        for m in ms:
            fingerprints[(case, harness)].add(json.dumps(m["global_instructions"], sort_keys=True))

    for (case, harness), prints in sorted(fingerprints.items()):
        if len(prints) > 1:
            print(f"경고: {case}/{harness} 실행들의 전역 지침이 서로 다르다. 이 비교는 키트 문장만의 효과로 볼 수 없다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
