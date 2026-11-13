"""새 세션 기록(JSONL)을 읽어 도구 호출 순서와 마지막 답을 자르지 않고 돌려준다.

Claude(`claude -p --output-format stream-json`)와 Codex(`codex exec --json`) 두 형식을 읽는다.
판정은 이 함수가 돌려준 원문으로 한다. 화면에 보여 줄 때만 줄여 쓴다.
사건 형식(type 이름·필드)을 아는 곳은 이 파일뿐이다. 관찰(observe.py)은 여기서 낸 호출 목록으로 정책(무엇을 편집·검증자 흔적으로 볼지)만 정한다.
실행기가 남기는 기록 파일의 이름(<이름>.jsonl·<이름>.tN.jsonl·<이름>.rollout.jsonl)도 여기서만 정한다.
"""
import json, re
from pathlib import Path

# 오류 사건이 든 줄: Codex 의 error·turn.failed, Claude 의 오류 결과(is_error). 줄을 풀지 않고 원문 바이트에서 찾는다.
ERROR_EVENT = re.compile(rb'"type": ?"(error|turn\.failed)"|"is_error": ?true')
TURN_LOG = re.compile(r"\.t(\d+)\.jsonl$")


def _beside(log, suffix):
    """판정용 기록 <이름>.jsonl 옆의 <이름><suffix>."""
    log = Path(log)
    return log.parent / (log.name[: -len(".jsonl")] + suffix)


def turn_log(log, n):
    """N 번째 턴의 기록 <이름>.tN.jsonl. 실행기는 턴마다 이 파일을 남기고, <이름>.jsonl 은 모든 턴을 순서대로 이은 것이다."""
    return _beside(log, f".t{n}.jsonl")


def turn_logs(log):
    """남아 있는 턴 기록을 턴 순서대로."""
    return sorted(Path(log).parent.glob(_beside(log, ".t*.jsonl").name), key=lambda p: int(TURN_LOG.search(p.name).group(1)))


def last_turn_log(log):
    """마지막 턴 기록(가장 큰 N). 턴 기록이 없으면 주어진 파일 자체다."""
    turns = turn_logs(log)
    return turns[-1] if turns else Path(log)


def rollout_log(log):
    """Codex 세션 원본 기록 <이름>.rollout.jsonl(실행기가 세션을 닫을 때 남긴다)."""
    return _beside(log, ".rollout.jsonl")


def events(path, errors="strict"):
    """기록의 사건(JSON 한 줄)을 순서대로 낸다. JSON 이 아닌 줄은 건너뛴다. errors 는 UTF-8 이 아닌 바이트를 다루는 방식이다(open 의 errors)."""
    with open(path, encoding="utf-8", errors=errors) as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def is_codex(path):
    """Codex exec 기록인가(첫 사건이 thread.started 등 Codex 형식)."""
    for event in events(path):
        return event.get("type", "").startswith(("thread.", "turn.", "item."))
    return False


def session_id(path):
    """다음 턴이 이어 갈 세션 id(Claude 는 session_id, Codex 는 thread_id). 기록에 없으면 빈 글. 객체가 아닌 사건을 만나면 거기서 그만 찾는다."""
    for event in events(path, errors="replace"):
        if not isinstance(event, dict):
            break
        if event.get("session_id") or event.get("thread_id"):
            return str(event.get("session_id") or event.get("thread_id"))
    return ""


def error_lines(path):
    """오류 사건이 든 줄을 원문 바이트 그대로 돌려준다(일반 답이 든 줄은 내지 않는다)."""
    return [line for line in Path(path).read_bytes().split(b"\n") if ERROR_EVENT.search(line)]


def calls(path):
    """도구 호출을 두 하네스 공통 모양으로 순서대로 돌려준다: [{"kind", "name", "input"}].
    kind 는 tool(Claude 도구 호출: name 은 도구 이름, input 은 그 입력), command(Codex 셸 명령: input.command),
    edit(Codex 파일 변경: input.paths), agent(Codex 하위 에이전트 도구: name 은 도구 이름, input.prompt·receiver_thread_ids)다.
    agent 는 완료 전 사건(item.started 등)에서도 낸다(시작만 남은 호출도 맡긴 흔적이다)."""
    found = []
    for event in events(path):
        item = event.get("item") or {}
        if event.get("type") == "assistant":
            for part in (event.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    found.append({"kind": "tool", "name": part.get("name"), "input": part.get("input") or {}})
        if item.get("type") == "collab_tool_call":
            found.append({"kind": "agent", "name": item.get("tool"), "input": item})
        if event.get("type") == "item.completed" and item.get("type") == "file_change":
            found.append({"kind": "edit", "name": None, "input": {"paths": [str(c.get("path", "")) for c in item.get("changes", [])]}})
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            found.append({"kind": "command", "name": None, "input": {"command": item.get("command", "")}})
    return found


def rollout_calls(path):
    """Codex 원본 기록(rollout)에서 마지막 사용자 턴 뒤의 도구 호출을 돌려준다: [{"name", "code"}]. 사건이 하나도 없으면 None.
    함수 호출(function_call)은 name 이 도구 이름이고, 코드 실행 도구(custom_tool_call)는 name 이 None 이며 code 가 실행한 코드다."""
    found, seen = [], 0
    for event in events(path):
        seen += 1
        payload = event.get("payload") or {}
        if event.get("type") == "event_msg" and payload.get("type") in ("user_message", "task_started"):
            found = []  # 새 사용자 턴이 시작되면 다시 센다(원본 형식에 따라 둘 중 하나로 표시된다)
        elif event.get("type") == "response_item" and payload.get("type") == "function_call":
            found.append({"name": payload.get("name"), "code": ""})
        elif event.get("type") == "response_item" and payload.get("type") == "custom_tool_call":
            found.append({"name": None, "code": str(payload.get("input", ""))})
    return found if seen else None


def read(path):
    """(steps, final) 을 돌려준다. steps 는 "도구: 입력" 문자열 목록, final 은 마지막 답 전체다."""
    steps, final = [], ""
    for event in events(path):
        kind = event.get("type")
        if kind == "assistant":
            for part in event.get("message", {}).get("content", []):
                if part.get("type") == "tool_use":
                    steps.append(f"{part.get('name')}: {json.dumps(part.get('input'), ensure_ascii=False)}")
        elif kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "command_execution":
                steps.append("cmd: " + item.get("command", ""))
            elif item.get("type") == "file_change":
                steps.append("edit: " + json.dumps([c.get("path") for c in item.get("changes", [])], ensure_ascii=False))
        elif kind in ("turn.failed", "error"):
            steps.append("ERROR: " + json.dumps(event, ensure_ascii=False))
        final = _answer(event, final)
    return steps, final


def _answer(event, final):
    """이 사건까지 본 마지막 답. 사건에 답이 없으면 받은 final 그대로다. 객체가 아닌 사건·부분은 건너뛴다."""
    if not isinstance(event, dict):
        return final
    kind = event.get("type")
    if kind == "assistant":
        for part in (event.get("message") or {}).get("content", []) or []:
            if isinstance(part, dict) and part.get("type") == "text":
                final = part.get("text", "")
    elif kind == "result":
        final = event.get("result") or final
    elif kind == "item.completed" and (event.get("item") or {}).get("type") == "agent_message":
        final = event["item"].get("text", "")
    return final


def replies(path):
    """이 기록에서 에이전트가 사용자에게 쓴 글 전부를 순서대로. 한 턴에 글을 여러 번 나눠 쓰는 경우(질문 목록을 앞 글에, "위 질문에 답해 달라"를
    마지막 글에) 마지막 답만 읽으면 질문을 놓친다. 기록을 열 수 없으면 빈 목록이다."""
    found = []
    try:
        for event in events(path, errors="replace"):
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "assistant":
                found += [part.get("text", "") for part in (event.get("message") or {}).get("content", []) or []
                          if isinstance(part, dict) and part.get("type") == "text"]
            elif kind == "item.completed" and (event.get("item") or {}).get("type") == "agent_message":
                found.append(event["item"].get("text", ""))
    except OSError:
        return []
    return [text for text in found if text.strip()]


def final_answer(path):
    """마지막 답 전체(read 의 final 과 같은 규칙). 검토자 기록처럼 온전하지 않을 수 있는 기록용이다:
    기록을 열 수 없으면 빈 글이고, UTF-8 이 아닌 바이트와 객체가 아닌 사건은 멈추지 않고 넘긴다."""
    final = ""
    try:
        for event in events(path, errors="replace"):
            final = _answer(event, final)
    except OSError:
        return ""
    return final


def commands(path):
    """셸 명령과 그 결과를 짝지어 순서대로 돌려준다: [{"command", "output", "exit_code"}].
    Claude 는 Bash 호출(tool_use id)을 같은 id 의 tool_result 와 잇고(is_error 면 머리줄 "Exit code N" 의 N 을 종료 코드로 하고 출력에서 뺀다. 없으면 1),
    Codex 는 command_execution 의 aggregated_output·exit_code 를 쓴다. 결과가 기록에 없으면 output·exit_code 는 None 이다."""
    found, by_id = [], {}
    for event in events(path):
        kind = event.get("type")
        if kind in ("assistant", "user"):
            for part in event.get("message", {}).get("content", []) or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use" and part.get("name") == "Bash":
                    by_id[part.get("id")] = {"command": str((part.get("input") or {}).get("command", "")), "output": None, "exit_code": None}
                    found.append(by_id[part.get("id")])
                elif part.get("type") == "tool_result" and part.get("tool_use_id") in by_id:
                    body = part.get("content")
                    if isinstance(body, list):
                        body = "\n".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                    body = str(body or "")
                    code = re.match(r"(?:Error: )?Exit code (\d+)\n?", body) if part.get("is_error") else None
                    by_id[part["tool_use_id"]].update(output=body[code.end():] if code else body,
                                                      exit_code=(int(code.group(1)) if code else 1) if part.get("is_error") else 0)
        elif kind == "item.completed" and (event.get("item") or {}).get("type") == "command_execution":
            item = event["item"]
            found.append({"command": str(item.get("command", "")), "output": item.get("aggregated_output"), "exit_code": item.get("exit_code")})
    return found


if __name__ == "__main__":
    import sys

    s, f = read(sys.argv[1])
    for n, step in enumerate(s, 1):
        print(f"{n}. {step[:200]}")
    print("--- 마지막 답 ---")
    print(f)
