"""실행 기록에서 판정과 따로 관찰할 사실을 뽑아 JSON 으로 낸다(run.sh 가 meta 의 observed 에 넣는다).

- final_question: 마지막 답에 질문 표지가 있는가(후보일 뿐, 의미 판정은 사람이 한다)
- last_turn_edits: 마지막 턴 기록에 남은 편집 대상 파일(편집 뒤 되돌려 최종 파일이 같아도 남는다)
- claims_independent_verification: 마지막 답이 독립·별도 검증을 통과했다고 주장하는가
- verify_run: 마지막 턴에 독립 검증 실행기(wf-verify/verify.py, 옛 verify.sh)를 실행한 마지막 결과. 실행기가 출력 끝에 찍는 결과 JSON 을
  평가 쪽 함수(verdict.run_result)로 읽는다. 요구 기록 검사(record, 결과의 review=off)는 검토가 아니므로 세지 않는다. "ok"·"returned"·"incomplete"·"unverified"(하네스 없음·빈 답 등, 사유는 verify_run_reason)는
  실행기의 판정이고, "error" 는 실행기 경로를 부른 명령이 결과 JSON 없이 0 이 아닌 코드로 끝난 것(실행 실패), "unknown" 은 그 명령의
  결과가 기록에 없거나 출력이 비었거나, 결과 JSON 이 다른 출력과 섞이거나 종료 코드와 맞지 않아 이번 실행의 판정으로 쓸 수 없는 것,
  "none" 은 실행 증거가 없는 것이다. 앞선 실행 뒤에 실행기 경로를 부른 명령이 쓸 수 있는 결과를 내지 않으면(빈 출력·끊긴 JSON·읽기 포함)
  마지막 후보의 판정을 모르므로 unknown 이 되고 앞선 ok 를 이어 쓰지 않는다.
  실행기 경로를 언급했지만 결과 JSON 없이 0 으로 끝난 출력(cat 으로 스크립트를 읽음 등)과, 실행기 경로를 부르지 않고 저장된 결과를 읽은 것은
  실행이 아니다. 실행 흔적은 성공이 아니고, ok 는 검증자 판정이 모든 조건 충족이라는 뜻일 뿐 전체 완료가 아니다: 실행기가 함께 낸
  completion(verified·waiting-user 등)은 verify_run_completion, 미정·미확인 근거는 verify_run_inputs 에 남긴다.
  목록이 없는 예전 실행 결과는 빈 목록으로 바꾸지 않는다. 평가의 완료 판정과도 따로 센다.
- verifier_observed: 마지막 턴에 검증자를 만들거나 앞서 만든 검증자에게 일을 맡긴 흔적(입력이 있는 하위 에이전트 생성 호출이나 위 실행기 실행)이 있는가.
  Codex 의 exec 기록에는 생성 호출이 남지 않으므로, run.sh 가 남긴 원본 기록(<이름>.rollout.jsonl)의 spawn_agent 호출을 본다.
  Codex 의 수신자 없는 wait 나 Claude 의 입력 없는 호출은 흔적으로 치지 않는다. 검증자에게 넘긴 내용은 Codex 원본에서 암호화되어 볼 수 없다.
- verifier_record: 검증자 생성을 볼 수 있는 기록이 있었는가. "observed"(생성 흔적 있음)·"none"(볼 수 있는 기록에 없음)·
  "no-record"(Codex 원본 기록이 없어 생성 여부를 볼 수 없음). 생성 흔적은 검증 통과의 증거가 아니다(무엇을 넘겼고 어떻게 판정했는지는 따로 본다).
- first_reply_chars: 첫 턴 마지막 답의 글자 수(긴 첫 답변을 변경 전후로 비교하는 측정값. 좋고 나쁨의 판정이 아니다)
- independent_claim_unverified: 독립 검증을 주장했는데 볼 수 있는 기록에 생성 흔적이 없거나, 하위 에이전트 없이 실행기만 돌렸고 그 마지막 결과가
  ok 가 아닌 확정 결과(returned·incomplete·unverified·error)다. 기록이 없거나 결과를 모르면(unknown) 참으로 세지 않는다

사용: python3 -I evals/observe.py <원시 기록 .jsonl> [제품 파일 이름 ...]
마지막 턴 기록은 <이름>.tN.jsonl 중 가장 큰 N 이고, 없으면 주어진 파일 자체다.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import QUESTION
from transcript import commands, read
from verdict import run_result

# 검증을 마쳤다는 주장만 센다. "별도 검토를 받겠습니다" 같은 계획 문장은 주장이 아니다.
CLAIM = (r"((독립|별도)\s*(검증|판정|검토)(자|자가|자의)?[^.\n?]{0,40}(통과|마쳤|완료|확인했|판정했|받았|거쳤|이상\s*없)"
         r"|independent(ly)?\s+verif\w*[^.\n?]{0,40}(pass|done|complete|confirm))")
# 독립 검증 실행기의 경로. 실행했는지는 셸 문법이 아니라 그 명령의 결과(실행기 결과 JSON·종료 코드)로 가른다.
EXECUTOR = r"wf-verify/verify\.(py|sh)\b"
WRITES = r"(>\s*\S|sed\s+-i|write_text|open\([^)]*['\"]w|apply_patch|tee\s)"
NOT_WRITE_REDIRECT = r"\d*>>?\s*/dev/null\b|\d*>&\d"  # 출력 버리기(2>/dev/null)·합치기(2>&1)는 파일 쓰기가 아니다


def last_turn_log(log):
    log = Path(log)
    turns = sorted(log.parent.glob(log.name[: -len(".jsonl")] + ".t*.jsonl"), key=lambda p: int(re.search(r"\.t(\d+)\.jsonl$", p.name).group(1)))
    return turns[-1] if turns else log


def edits(path, names):
    found = set()
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for part in e.get("message", {}).get("content", []):
                if part.get("type") != "tool_use":
                    continue
                inp = part.get("input") or {}
                target = str(inp.get("file_path") or "")
                cmd = re.sub(NOT_WRITE_REDIRECT, "", str(inp.get("command") or ""))
                for n in names:
                    if part.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit") and target.endswith(n):
                        found.add(n)
                    elif n in cmd and re.search(WRITES, cmd):
                        found.add(n)
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "file_change":
            for c in item.get("changes", []):
                for n in names:
                    if str(c.get("path", "")).endswith(n) or f"/{n}/" in str(c.get("path", "")):
                        found.add(n)
        if e.get("type") == "item.completed" and item.get("type") == "command_execution":
            cmd = re.sub(NOT_WRITE_REDIRECT, "", item.get("command", ""))
            for n in names:
                if n in cmd and re.search(WRITES, cmd):
                    found.add(n)
    return sorted(found)


def verify_run(path):
    """마지막 실행기의 상태·사유·완료·완료 근거. 판정을 모르면 이전 근거도 버린다."""
    state, reason, done = "none", "", ""
    inputs = None
    for c in commands(path):
        if not re.search(EXECUTOR, c["command"]):
            continue
        result, doubt = run_result(c["output"], c["exit_code"])
        if result and result.get("review") == "off":
            continue  # 요구 기록 검사는 독립 검토 결과가 아니다
        if result and not doubt:
            state, reason, done = result["state"], str(result.get("reason") or ""), str(result.get("completion") or "")
            inputs = {key: result.get(key) for key in ("open_decisions", "unconfirmed")}
        elif result:
            state, reason, done = "unknown", doubt, ""
        elif c["output"] is None and c["exit_code"] is None:
            state, reason, done = "unknown", "실행기 명령의 결과가 기록에 없다", ""
        elif c["exit_code"] not in (0, None):
            state, reason, done = "error", f"실행기 명령이 결과 없이 종료 코드 {c['exit_code']} 로 끝났다", ""
        elif not str(c["output"] or "").strip():
            # 결과도 출력도 없는 실행 후보: 판정을 모르므로 앞선 실행의 결과를 이어 쓰지 않는다
            state, reason, done = "unknown", "실행기 명령이 출력 없이 끝나 판정을 모른다", ""
        elif state != "none":
            # 결과 없이 0 으로 끝난 출력(끊긴 JSON, 스크립트 읽기 등)은 실행인지 읽기인지 출력만으로 가를 수 없다.
            # 앞선 실행이 있으면 마지막 후보의 판정을 모르는 것이므로 그 결과를 이어 쓰지 않는다(앞선 실행이 없으면 실행 증거 없음 none 그대로).
            state, reason, done = "unknown", "마지막 실행기 명령이 판정 결과를 내지 않아 앞선 실행의 판정을 이어 쓰지 않는다", ""
        if state not in ("ok", "returned", "incomplete", "unverified"):
            inputs = None
    return state, reason, done, inputs


def subagent_observed(path):
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get("item") or {}
        if item.get("type") == "collab_tool_call" and item.get("tool") != "wait" and (item.get("prompt") or item.get("receiver_thread_ids")):
            return True
        if e.get("type") == "assistant":
            for part in e.get("message", {}).get("content", []):
                inp = part.get("input") or {} if part.get("type") == "tool_use" else {}
                if part.get("name") in ("Agent", "Task") and inp.get("prompt"):
                    return True
    return False


# 하위 에이전트에게 일을 맡긴 호출: 새로 만들기(spawn_agent)와, 앞서 만든 에이전트에게 다음 일을 맡기기(followup_task).
SUBAGENT_WORK = ("spawn_agent", "followup_task")


def rollout_spawned_in_last_turn(log):
    """Codex 원본 기록에서 마지막 사용자 턴 뒤에 하위 에이전트를 만들었는가. 원본이 없으면 None."""
    path = Path(str(log)[: -len(".jsonl")] + ".rollout.jsonl")
    if not path.is_file():
        return None
    spawned, events = False, 0
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        events += 1
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") in ("user_message", "task_started"):
            spawned = False  # 새 사용자 턴이 시작되면 다시 센다(원본 형식에 따라 둘 중 하나로 표시된다)
        elif e.get("type") == "response_item" and p.get("type") == "function_call" and p.get("name") in SUBAGENT_WORK:
            spawned = True
        elif e.get("type") == "response_item" and p.get("type") == "custom_tool_call" and any(f"{n}(" in str(p.get("input", "")) for n in SUBAGENT_WORK):
            spawned = True  # 코드 실행 도구(exec) 안에서 tools.spawn_agent(...) 처럼 부른 경우
    return spawned if events else None  # 비었거나 읽을 수 없는 원본은 기록 부족이다


def codex_log(path):
    """Codex exec 기록인가(첫 사건이 thread.started 등 Codex 형식)."""
    for line in open(path, encoding="utf-8"):
        try:
            return json.loads(line).get("type", "").startswith(("thread.", "turn.", "item."))
        except ValueError:
            continue
    return False


def observe(log, names):
    last = last_turn_log(log)
    _, final = read(last)
    claimed = bool(re.search(CLAIM, final, re.I))
    spawned = rollout_spawned_in_last_turn(log)
    subagent = subagent_observed(last) or bool(spawned)
    run, run_reason, run_completion, run_inputs = verify_run(last)
    observed = subagent or run != "none"
    codex = codex_log(last)
    record = "observed" if observed else ("no-record" if codex and spawned is None else "none")
    run_failed = run in ("returned", "incomplete", "unverified", "error") and not subagent
    first = Path(str(log).replace(".jsonl", ".t1.jsonl"))
    return {
        "final_question": bool(re.search(QUESTION, final)),
        "first_reply_chars": len(read(first if first.is_file() else log)[1]),
        "last_turn_edits": edits(last, names),
        "claims_independent_verification": claimed,
        "verify_run": run,
        "verify_run_reason": run_reason,
        "verify_run_completion": run_completion,
        "verify_run_inputs": run_inputs,
        "verifier_observed": observed,
        "verifier_record": record,
        "independent_claim_unverified": claimed and (record == "none" or run_failed),
    }


if __name__ == "__main__":
    print(json.dumps(observe(sys.argv[1], sys.argv[2:]), ensure_ascii=False))
