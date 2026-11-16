"""구성 비교(compare.py)의 요약(<이름>.json)을 읽는 곳: 구성·회차별 표와, 일반 결과 표(evals/report.py)가 읽는 meta.

  python3 -I evals/goalflow/table.py <결과 폴더> [-v]

result_meta(summary) 는 요약 하나를 <이름>.meta.json 의 내용으로 바꾼다(compare.py 가 요약과 함께 쓴다). 파일·모델을 쓰지 않는 함수다.
evals/result.py 의 initial_result 는 쓰지 않는다: 그 함수가 받는 하네스 버전·전역 지침 지문·판정기 지문·검증 루프 상태·관찰(observe.py) 결과를
compare.py 는 재지 않는다. 재지 않은 값을 채우지 않고 report.py 가 읽는 항목만 적는다.
"""
import glob, json, sys

PASS, FAIL, REVIEW, UNVERIFIED = "PASS", "FAIL", "REVIEW", "UNVERIFIED"  # evals/judge.py 와 같은 낱말


def _static(summary):
    return summary["turns"][:min(summary.get("static_turns", 1), len(summary["turns"]))]


def edits_before_answer(summary):
    """모의 사용자의 답을 보내기 전, 정해진 사용자 글(요청·followup) 턴들에서 쓰인 제품 파일(conversation.py 의 파일 시스템 증거).
    턴 끝의 시작 커밋 대비 변경(커밋 후 되돌림도 잡힘)과 턴 동안의 파일 사건(같은 턴 안의 고침·되돌림, 만들고 지움도 잡힘)을 합친다."""
    return sorted({f for t in _static(summary) for f in (t["product_changes"] + (t.get("product_touched") or []))})


def unreadable_before_answer(summary):
    """답 전 턴 가운데 관찰이 부족한 턴과 까닭: 대화 기록을 온전히 읽지 못함(무엇을 물었는지 모름), 파일 사건 감시를 켜지 못함(무엇을 썼는지 모름)."""
    return [f"{t['turn']}({'대화 기록 손상' if t.get('log_readable') is False else '파일 감시 불가'})"
            for t in _static(summary) if t.get("log_readable") is False or t.get("watch_error")]


def conversation_unfinished(summary):
    """대화를 끝까지 못 갔으면 그 까닭: 하네스 비정상 종료(rc), 계획한 턴(정해진 글 + 답 + 마무리) 미달. 끝났으면 빈 문자열."""
    turns = summary["turns"]
    bad = [t["turn"] for t in turns if t.get("rc", 0) != 0]
    if bad:
        return "하네스가 비정상 종료했다: 턴 " + ", ".join(map(str, bad))
    planned = summary.get("static_turns", 1) + 2
    return f"턴 {len(turns)}/{planned} 에서 멈췄다" if len(turns) < planned else ""


def behavior_verdict(summary):
    """최종 동작만의 판정: 외부 판정기(oracle.py)가 끝난 프로젝트의 공개 명령으로 본 결과."""
    n, failed, unobserved = summary["n_cases"], summary["failed"], summary["unobserved"]
    if summary.get("oracle_error") or not n:
        return UNVERIFIED, "UNVERIFIED 외부 판정기가 결과를 내지 못했다: " + str(summary.get("oracle_error") or "판정 항목 없음")[:200]
    if failed:
        return FAIL, f"FAIL 외부 판정 {len(failed)}/{n} 실패: " + ", ".join(failed)
    if unobserved or summary.get("observation_complete") is not True:
        return UNVERIFIED, f"UNVERIFIED 외부 판정 {len(unobserved)}/{n} 관찰 불가: " + ", ".join(unobserved)
    return PASS, f"PASS 외부 판정 {n}/{n} 통과"


def process_state(summary):
    """절차만의 판정(키트 v3.4: 결정이 남으면 답을 받은 뒤 고친다): violation(첫 답 전에 제품을 고침) /
    review(증거 부족: 모의 사용자 분류 실패, 답 전 기록 손상, 대화를 끝내지 못함) / ok."""
    if edits_before_answer(summary):
        return "violation"
    return "review" if summary.get("mock_error") or unreadable_before_answer(summary) or conversation_unfinished(summary) else "ok"


def oracle_verdict(summary):
    """전체 판정 낱말과 한 줄 설명. 최종 동작과 절차를 함께 본다: 나중에 고쳐 최종 동작이 맞아도 앞선 절차 위반은 지우지 않는다.
    첫 답 전 편집 → 실패(이미 일어난 사실), 모의 사용자 분류 실패 → 검토 필요(대화를 못 끝내 최종 동작이 근거가 아니다), 그 밖에는 최종 동작 판정."""
    word, line = behavior_verdict(summary)
    early = edits_before_answer(summary)
    if early:
        return FAIL, "FAIL 답 전에 제품 파일을 바꿨다: " + ", ".join(early) + f" / 최종 동작: {line}"
    if unreadable_before_answer(summary):
        return REVIEW, "REVIEW 답 전 턴을 온전히 관찰하지 못했다: 턴 " + ", ".join(unreadable_before_answer(summary)) + f" / 최종 동작: {line}"
    if summary.get("mock_error"):  # 대화를 끝까지 못 갔으면 최종 동작은 판정 근거가 아니다(증거 부족)
        return REVIEW, "REVIEW 모의 사용자 분류가 실패해 대화를 끝까지 진행하지 못했다: " + summary["mock_error"][:150] + f" / 최종 동작: {line}"
    if conversation_unfinished(summary):
        return REVIEW, "REVIEW 대화를 끝까지 진행하지 못했다: " + conversation_unfinished(summary) + f" / 최종 동작: {line}"
    return word, line


def result_meta(summary):
    """요약(compare.py 의 summary)을 report.py 가 읽는 meta 로 바꾼다.
    report.py 가 읽는 항목: case·harness·kit_commit·exit_code·seconds·agents_md_bytes·check_passed·check_needs_review·check_unverified·
    user_turns·observed.first_reply_chars·global_instructions. 그 밖에 lang·input·completion·observed 의 검증 흔적은 없으면 기본값으로 센다.
    kit_commit 은 키트 구성이면 설치한 키트 커밋, 스킬 설치·지침 없음 구성이면 구성 이름이다(세 구성이 표에서 세 줄이 된다).
    global_instructions 는 None 이다: 세션을 사용자 전역 설정과 격리해 돌리고, 전역 지침의 지문은 재지 않는다.
    goalflow 에는 table.py 가 보이는 구성별 사실을 둔다: 모의 사용자가 답한 정책, 답 전(1턴)에 바꾼 제품 파일, 실패·관찰 불가 판정 항목."""
    arm, turns = summary["arm"], summary["turns"]
    word, line = oracle_verdict(summary)
    return {"case": summary.get("task", "goalflow"), "kit_ref": summary["kit_ref"] if arm == "kit" else arm,
            "kit_commit": summary["kit_commit"] if arm == "kit" else arm, "harness": summary["harness"], "run": summary["run"],
            "model": summary.get("model"), "mock_user_model": summary.get("mock_user_model"), "harness_version": summary.get("harness_version"),
            "exit_code": next((t["rc"] for t in turns if t["rc"] != 0), 0), "seconds": summary["seconds"],
            "agents_md_bytes": summary["agents_md_bytes"], "check_passed": word == PASS, "check_needs_review": word == REVIEW,
            "check_unverified": word == UNVERIFIED, "check_output": line, "user_turns": len(turns),
            "observed": {"first_reply_chars": turns[0]["reply_chars"]}, "global_instructions": None,
            "goalflow": {"arm": arm, "mock": summary["mock"], "answered": summary["answered"], "edits_before_answer": edits_before_answer(summary),
                         "final_behavior": behavior_verdict(summary)[0], "process": process_state(summary),
                         "surfaced_quotes": summary.get("surfaced_quotes") or {},
                         "failed": summary["failed"], "unobserved": summary["unobserved"], "n_cases": summary["n_cases"],
                         "map": summary["map"], "public_tests_rc": summary["public_tests_rc"]}}


if __name__ == "__main__":
    for f in sorted(glob.glob(sys.argv[1] + "/*.json")):
        if f.endswith((".oracle.json", ".meta.json")):
            continue
        s = json.load(open(f)); t = s["turns"]
        print(f'{s.get("task", "goalflow"):9} {s["name"]:16} valid={s["automated_valid"]!s:5} fail={len(s["failed"]):2}/{s["n_cases"]} unobs={len(s["unobserved"])} pub={s["public_tests_rc"]} map={s["map"]!s:5} sec={s["seconds"]:5} | '
              + " ".join(f't{r["turn"]}:ans{r.get("answered_now","")},rc{r["rc"]},{r["seconds"]}s,edit{len(r["product_changes"])},?{r["question_marks"]},rec{r["record_runs"]},rev{r["review_runs"]}' for r in t) + f' | init={s["init"]} err={str(s["oracle_error"])[:80] if s["oracle_error"] else ""}')
        if "-v" in sys.argv:
            print("    failed:", s["failed"], "| 사용자 답 항목:", s.get("failed_decision"))
