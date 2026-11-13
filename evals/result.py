"""평가 결과의 완료 근거와 재판정 이력을 한 곳에서 보존한다.

완료 규칙 자체는 설치 검토 도구의 completion을 쓴다. 이 module은 그 규칙에
필요한 입력을 실행과 재판정 사이에 잃지 않게 한다. 구기록의 없는 입력은
False로 복원하지 않는다.
"""
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import EXIT, FAIL, PASS, REVIEW, UNVERIFIED
from verdict import completion

REVIEW_STATES = {"off", "ok", "returned", "incomplete", "unverified"}


def _known_inputs(inputs):
    return (isinstance(inputs, dict) and inputs.get("version") == 1
            and isinstance(inputs.get("review_state"), str) and inputs["review_state"] in REVIEW_STATES
            and type(inputs.get("review_required")) is bool
            and all(isinstance(inputs.get(k), list)
                    and all(isinstance(v, str) for v in inputs[k]) for k in ("open_decisions", "unconfirmed")))


CHECK_EXIT = {code: word for word, code in EXIT.items()}  # 종료 코드 → 판정 낱말


def check_word(exit_code, output):
    """판정 검사(check.py)의 종료 코드와 출력으로 판정 낱말을 정한다. 실행기(run.py)와 재판정(rejudge.py)이 같이 쓴다.
    검사는 0=통과, 1=실패, 2=검토 필요로 끝나고 결과 줄을 PASS·FAIL·REVIEW 로 시작한다. 둘이 맞지 않으면(예외 등 검사 자체의 오류)
    실패가 아니라 미확인(UNVERIFIED)이다."""
    word = CHECK_EXIT.get(exit_code)
    return word if word and output.startswith(word) else UNVERIFIED


def check_verdict(record):
    if record.get("check_passed"):
        return PASS
    if record.get("check_needs_review"):
        return REVIEW
    return UNVERIFIED if record.get("check_unverified") else FAIL


def _completed(record, check):
    inputs = record.get("completion_inputs")
    if _known_inputs(inputs):
        # 관문이 있던 때(v3.0 이하)의 기록에 남은 gate_waiting 은 읽지 않는다(그 결과는 그 태그의 evals 로 다시 판정한다).
        return completion(inputs["review_state"], check, bool(inputs["open_decisions"]),
                          inputs["review_required"], unresolved=bool(inputs["unconfirmed"]))
    # 예전 저장 형식에는 미정·미확인 입력이 없다. 기존 대기와 실패는 보존하되
    # PASS만 다시 얻었다고 그 공백이 해소된 것으로 보지 않는다.
    previous = record.get("completion")
    state = record.get("review_state", record.get("verifier", "unverified"))
    waiting = previous == "waiting-user"
    return completion(state, check, waiting, required=True, unresolved=True)


def initial_result(run):
    """실행기가 관찰한 근거를 저장한 뒤 그 근거로 완료를 계산한다. run 은 한 번의 실행에서 관찰한 사실이다:
    case·kit_ref·kit_commit·harness·run·harness_version·exit_code·seconds·agents_md_bytes, check(판정 낱말)·check_output,
    input·user_turns·planned_turns, observed(observe.py 결과),
    verifier(실행기 검증 루프의 상태, 안 돌렸으면 off)·verify_reason·verify_rounds·verifier_exit_code·review(검토 도구의 마지막 결과 JSON)·
    baseline_changed·verifier_tool·review_required, lang·judge_version·codex_project_trusted·claude_project_settings·global_instructions."""
    observed, review = run["observed"], run["review"]
    state = run["verifier"]
    evidence = review
    if state == "off":
        state = observed.get("verify_run", "none")
        if state in REVIEW_STATES - {"off"}:
            evidence = observed.get("verify_run_inputs") or {}
        elif state in ("error", "unknown"):
            state, evidence = "unverified", {}
        else:
            state, evidence = "off", {"open_decisions": [], "unconfirmed": []}
    inputs = {"version": 1, "review_state": state, "review_required": run["review_required"],
              "open_decisions": evidence.get("open_decisions"), "unconfirmed": evidence.get("unconfirmed")}
    m = {"case": run["case"], "kit_ref": run["kit_ref"], "kit_commit": run["kit_commit"], "harness": run["harness"],
         "run": run["run"], "harness_version": run["harness_version"], "exit_code": run["exit_code"], "seconds": run["seconds"],
         "agents_md_bytes": run["agents_md_bytes"], "check_passed": run["check"] == PASS,
         "check_needs_review": run["check"] == REVIEW, "check_unverified": run["check"] == UNVERIFIED,
         "input": run["input"], "user_turns": run["user_turns"], "planned_turns": run["planned_turns"],
         "check_output": run["check_output"], "observed": observed, "verifier": run["verifier"],
         "verify_reason": run["verify_reason"], "verify_rounds": run["verify_rounds"],
         "verifier_exit_code": run["verifier_exit_code"],
         "out_of_scope": review.get("out_of_scope", []), "verifier_conditions": review.get("conditions", []),
         "lang": run["lang"] or None, "judge_version": run["judge_version"],
         "stage": "after-approval" if run["input"] == "with-approval" else "original-input",
         "review_state": state, "review_required": inputs["review_required"],
         "completion_inputs": inputs,
         "verifier_tool": run["verifier_tool"] or None, "codex_project_trusted": run["codex_project_trusted"], "global_entry": run.get("global_entry", "personal"),
         "baseline_changed_after_approval": run["baseline_changed"],
         "global_instructions": run["global_instructions"],
         "claude_project_settings": run["claude_project_settings"] or None}
    # 예전 검토기 출력에 남은 대기는 나머지 입력이 부족해도 버리지 않는다.
    if evidence.get("completion", observed.get("verify_run_completion")) == "waiting-user":
        m["completion"] = "waiting-user"
    m["completion"] = _completed(m, check_verdict(m))
    m["completion_inputs_missing"] = not _known_inputs(inputs)
    return m


def write_meta(path, run):
    """한 번의 실행 결과를 <이름>.meta.json 으로 쓴다."""
    Path(path).write_text(json.dumps(initial_result(run), ensure_ascii=False, indent=1), encoding="utf-8")


def rejudge_result(record, check, output, judge_version, check_sha):
    updated = copy.deepcopy(record)
    updated.setdefault("rejudge_history", []).append({
        "verdict": check_verdict(record), "check_output": record.get("check_output", ""),
        "completion": record.get("completion"), "judge_version": record.get("judge_version"),
        "check_sha": record.get("check_sha"),
        "completion_inputs": copy.deepcopy(record.get("completion_inputs")),
        "completion_inputs_missing": record.get("completion_inputs_missing"),
    })
    updated.update(completion=_completed(record, check), check_passed=check == PASS,
                   check_needs_review=check == REVIEW, check_unverified=check == UNVERIFIED,
                   check_output=output, rejudged=True, check_sha=check_sha, judge_version=judge_version,
                   completion_inputs_missing=not _known_inputs(record.get("completion_inputs")))
    return updated


if __name__ == "__main__":  # python3 -I evals/result.py <meta.json> < 실행 사실(JSON)
    write_meta(sys.argv[1], json.load(sys.stdin))
