"""평가 결과의 완료 근거와 재판정 이력을 한 곳에서 보존한다.

완료 규칙 자체는 설치 검토 도구의 completion을 쓴다. 이 module은 그 규칙에
필요한 입력을 실행과 재판정 사이에 잃지 않게 한다. 구기록의 없는 입력은
False로 복원하지 않는다.
"""
import copy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verdict import completion

REVIEW_STATES = {"off", "ok", "returned", "incomplete", "unverified"}


def _known_inputs(inputs):
    return (isinstance(inputs, dict) and inputs.get("version") == 1
            and isinstance(inputs.get("review_state"), str) and inputs["review_state"] in REVIEW_STATES
            and all(type(inputs.get(k)) is bool for k in ("review_required", "gate_waiting"))
            and all(isinstance(inputs.get(k), list)
                    and all(isinstance(v, str) for v in inputs[k]) for k in ("open_decisions", "unconfirmed")))


def check_verdict(record):
    if record.get("check_passed"):
        return "PASS"
    if record.get("check_needs_review"):
        return "REVIEW"
    return "UNVERIFIED" if record.get("check_unverified") else "FAIL"


def _completed(record, check):
    inputs = record.get("completion_inputs")
    if _known_inputs(inputs):
        return completion(inputs["review_state"], check,
                          inputs["gate_waiting"] or bool(inputs["open_decisions"]),
                          inputs["review_required"], unresolved=bool(inputs["unconfirmed"]))
    # 예전 저장 형식에는 미정·미확인 입력이 없다. 기존 대기와 실패는 보존하되
    # PASS만 다시 얻었다고 그 공백이 해소된 것으로 보지 않는다.
    previous = record.get("completion")
    state = record.get("review_state", record.get("verifier", "unverified"))
    waiting = record.get("gate_waiting") is True or previous == "waiting-user"
    return completion(state, check, waiting, required=True, unresolved=True)


def initial_result(e):
    """실행기가 관찰한 근거를 저장한 뒤 그 근거로 완료를 계산한다."""
    observed, review = json.loads(e["E_OBS"] or "{}"), json.loads(e["E_VJSON"] or "{}")
    state = e["E_VSTATE"]
    evidence = review
    if state == "off":
        state = observed.get("verify_run", "none")
        if state in REVIEW_STATES - {"off"}:
            evidence = observed.get("verify_run_inputs") or {}
        elif state in ("error", "unknown"):
            state, evidence = "unverified", {}
        else:
            state, evidence = "off", {"open_decisions": [], "unconfirmed": []}
    inputs = {"version": 1, "review_state": state, "review_required": e["E_REQUIRED"] == "true",
              "gate_waiting": e["E_WAITING"] == "true",
              "open_decisions": evidence.get("open_decisions"), "unconfirmed": evidence.get("unconfirmed")}
    m = {"case": e["E_CASE"], "kit_ref": e["E_REF"], "kit_commit": e["E_COMMIT"], "harness": e["E_HARNESS"],
         "run": int(e["E_RUN"]), "harness_version": e["E_VERSION"], "exit_code": int(e["E_RC"]), "seconds": int(e["E_SEC"]),
         "agents_md_bytes": int(e["E_BYTES"]), "check_passed": e["E_CHECK_RC"] == "0",
         "check_needs_review": e["E_CHECK_RC"] == "2", "check_unverified": e["E_CHECK_RC"] == "3",
         "approval_gate": e["E_GATE"] == "true", "input": e["E_INPUT"], "user_turns": int(e["E_TURNS"]),
         "planned_turns": int(e["E_PLANNED"]), "unapproved_turns": int(e["E_WAIT"] or 0),
         "check_output": e["E_VERDICT"], "observed": observed, "verifier": e["E_VSTATE"],
         "verify_reason": e["E_VREASON"], "verify_rounds": int(e["E_VROUNDS"]),
         "verifier_exit_code": int(e["E_VRC"]) if e["E_VRC"] else None,
         "out_of_scope": review.get("out_of_scope", []), "verifier_conditions": review.get("conditions", []),
         "lang": e["E_LANG"] or None, "judge_version": e["E_JUDGE"],
         "stage": "after-approval" if e["E_INPUT"] == "with-approval" else "original-input",
         "review_state": state, "review_required": inputs["review_required"],
         "completion_inputs": inputs, "gate_waiting": inputs["gate_waiting"],
         "verifier_tool": e["E_VTOOL"] or None, "codex_project_trusted": e["E_CTRUST"] == "true",
         "baseline_changed_after_approval": e["E_BCHANGED"] == "true",
         "global_instructions": {"~/.claude/CLAUDE.md": e["E_G1"], "~/.agents/USER.md": e["E_G2"],
                                 "~/.codex/AGENTS.md": e["E_G3"], "global skills": e["E_G4"], "plugins": e["E_G5"]},
         "claude_project_settings": e.get("E_CSET") or None}
    # 예전 검토기 출력에 남은 대기는 나머지 입력이 부족해도 버리지 않는다.
    if evidence.get("completion", observed.get("verify_run_completion")) == "waiting-user":
        m["completion"] = "waiting-user"
    m["completion"] = _completed(m, check_verdict(m))
    m["completion_inputs_missing"] = not _known_inputs(inputs)
    return m


def rejudge_result(record, check, output, judge_version, check_sha):
    updated = copy.deepcopy(record)
    updated.setdefault("rejudge_history", []).append({
        "verdict": check_verdict(record), "check_output": record.get("check_output", ""),
        "completion": record.get("completion"), "judge_version": record.get("judge_version"),
        "check_sha": record.get("check_sha"),
        "completion_inputs": copy.deepcopy(record.get("completion_inputs")),
        "completion_inputs_missing": record.get("completion_inputs_missing"),
    })
    updated.update(completion=_completed(record, check), check_passed=check == "PASS",
                   check_needs_review=check == "REVIEW", check_unverified=check == "UNVERIFIED",
                   check_output=output, rejudged=True, check_sha=check_sha, judge_version=judge_version,
                   completion_inputs_missing=not _known_inputs(record.get("completion_inputs")))
    return updated


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(json.dumps(initial_result(os.environ), ensure_ascii=False, indent=1), encoding="utf-8")
