"""새 세션 기록(JSONL)을 읽어 도구 호출 순서와 마지막 답을 자르지 않고 돌려준다.

Claude(`claude -p --output-format stream-json`)와 Codex(`codex exec --json`) 두 형식을 읽는다.
판정은 이 함수가 돌려준 원문으로 한다. 화면에 보여 줄 때만 줄여 쓴다.
사건 형식(type 이름·필드)을 아는 곳은 이 파일뿐이다. 관찰(observe.py)은 여기서 낸 호출 목록으로 정책(무엇을 편집·검증자 흔적으로 볼지)만 정한다.
실행기가 남기는 기록 파일의 이름(<이름>.jsonl·<이름>.tN.jsonl·<이름>.rollout.jsonl)도 여기서만 정한다.
"""
import hashlib, json, re
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
    log = Path(log)
    if TURN_LOG.search(log.name):
        log = log.with_name(TURN_LOG.sub('.jsonl', log.name))
    return _beside(log, ".rollout.jsonl")


def events(path, errors="strict"):
    """기록의 사건(JSON 한 줄)을 순서대로 낸다. JSON 이 아닌 줄은 건너뛴다. errors 는 UTF-8 이 아닌 바이트를 다루는 방식이다(open 의 errors)."""
    with open(path, encoding="utf-8", errors=errors) as f:
        for _, event in _decoded_events(f):
            yield event


def _decoded_events(lines, strict=False):
    """같은 사건 해석을 사용하되, 부재 판정에는 손상된 줄을 건너뛰지 않는다."""
    for number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except ValueError:
            if strict and line.strip():
                raise ValueError(f'{number}행의 사건 JSON이 손상됐다') from None
            continue
        if strict and not isinstance(value, dict):
            raise ValueError(f'{number}행이 사건 객체가 아니다')
        yield number, value


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


def agent_events(path, harness, turn=1):
    """지정 턴의 생성·실행 결과·평문 반환. 암호화된 지시문과 역할 추측은 내보내지 않는다.

    기존 최종 검증 관찰과 달리, 없다는 결론에는 온전한 해당 턴이 필요하다.
    생성과 답변 내용의 옳음은 별개이며 여기서는 실제 사건만 연결한다.
    """
    source = {'path': str(Path(path).resolve()), 'sha256': None}
    result = {'state': 'unverified', 'harness': harness, 'turn': turn,
              'turn_complete': False, 'source': source, 'agents': [], 'reason': ''}
    try:
        raw = Path(path).read_bytes()
        source['sha256'] = hashlib.sha256(raw).hexdigest()
        numbered = list(_decoded_events(raw.decode('utf-8').splitlines(), strict=True))
        if not numbered or type(turn) is not int or turn < 1:
            raise ValueError('관찰할 턴과 원본 사건이 필요하다')
        if harness == 'codex':
            agents, complete, scope = _codex_agents(numbered, turn)
        elif harness == 'claude':
            agents, complete, scope = _claude_agents(numbered)
        else:
            raise ValueError('지원하지 않는 하네스')
        result.update(agents=agents, turn_complete=complete, lines=scope)
        if not complete:
            result['reason'] = '해당 턴의 완료를 원본에서 확인하지 못했다'
        elif any(a['state'] in ('attempted', 'started', 'unverified') for a in agents):
            result['reason'] = '생성 실행 결과 또는 평문 반환을 모두 확인하지 못했다'
        else:
            result['state'] = 'observed' if agents else 'none'
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        result['reason'] = f'원본을 온전히 읽지 못했다: {exc}'
    return result


def _codex_agents(numbered, turn):
    starts = [(i, e.get('payload') or {}) for i, (_, e) in enumerate(numbered)
              if e.get('type') == 'event_msg' and (e.get('payload') or {}).get('type') == 'task_started']
    if not starts:
        starts = [(i, e.get('payload') or {}) for i, (_, e) in enumerate(numbered)
                  if e.get('type') == 'event_msg' and (e.get('payload') or {}).get('type') == 'user_message']
    if len(starts) < turn:
        return [], False, []
    first, marker = starts[turn - 1]
    end = starts[turn][0] if len(starts) > turn else len(numbered)
    selected = numbered[first:end]
    agents, by_call, complete = [], {}, False
    for line, event in selected:
        payload = event.get('payload') or {}
        kind = payload.get('type')
        if event.get('type') == 'event_msg' and kind in ('task_complete', 'turn_complete'):
            if not marker.get('turn_id') or not payload.get('turn_id') or payload['turn_id'] == marker['turn_id']:
                complete = True
        if event.get('type') != 'response_item':
            continue
        if kind == 'function_call' and str(payload.get('name', '')).split('.')[-1] == 'spawn_agent':
            agent = {'call_id': payload.get('call_id'), 'spawn_line': line, 'state': 'attempted', 'returns': []}
            # Only non-secret addressing metadata is retained from arguments.
            try:
                args = json.loads(payload.get('arguments') or '{}')
                if not isinstance(args, dict):
                    raise TypeError('생성 인자가 객체가 아니다')
                agent.update(task_name=args.get('task_name'), fork_turns=args.get('fork_turns'))
            except (ValueError, TypeError):
                agent['state'] = 'unverified'
            agents.append(agent)
            if isinstance(payload.get('call_id'), str) and payload['call_id'].strip():
                by_call[payload['call_id']] = agent
            else:
                agent['state'] = 'unverified'
        elif kind == 'custom_tool_call' and re.search(r'\bspawn_agent\s*\(', str(payload.get('input', ''))):
            # A nested code call alone does not prove that its spawn succeeded.
            agents.append({'call_id': payload.get('call_id'), 'spawn_line': line, 'state': 'unverified', 'returns': []})
        elif kind == 'function_call_output' and payload.get('call_id') in by_call:
            agent = by_call[payload['call_id']]
            agent['result_line'] = line
            try:
                output = json.loads(payload.get('output') or '{}')
                address = output.get('task_name') or output.get('agent_id') or output.get('id')
                agent.update(state='started' if address else 'unverified', address=address)
                if output.get('error') or output.get('isError'):
                    agent['state'] = 'failed'
            except (ValueError, TypeError, AttributeError):
                agent['state'] = 'unverified'
        elif kind == 'agent_message':
            for part in payload.get('content') or []:
                text = part.get('text', '') if isinstance(part, dict) else ''
                returned = re.search(r'Message Type:\s*FINAL_ANSWER\s*\n.*?Sender:\s*([^\s]+)\s*\nPayload:\s*\n(.*)', text, re.S)
                if not returned:
                    continue
                sender, body = returned.groups()
                matches = [a for a in agents if a.get('address') == sender]
                if len(matches) == 1:
                    matches[0]['returns'].append({'line': line, 'sender': sender, 'text': body})
                    matches[0]['state'] = 'returned'
    return agents, complete, [selected[0][0], selected[-1][0]]


def _claude_agents(numbered):
    agents, by_id, complete = [], {}, False
    uses, results = set(), set()
    # A readable message is not evidence of a particular worker's return when
    # the addressing is missing or ambiguous, including collisions with Bash.
    for _, event in numbered:
        for part in (event.get('message') or {}).get('content') or []:
            if not isinstance(part, dict) or part.get('type') not in ('tool_use', 'tool_result'):
                continue
            is_use = part['type'] == 'tool_use'
            key = part.get('id' if is_use else 'tool_use_id')
            seen = uses if is_use else results
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError('도구 호출·실행 결과의 ID가 없거나 비었거나 중복됐다')
            seen.add(key)
    if results - uses:
        raise ValueError('도구 실행 결과에 대응하는 호출 ID가 없다')
    for line, event in numbered:
        if event.get('type') == 'result':
            complete = not event.get('is_error', False)
        for part in (event.get('message') or {}).get('content') or []:
            if not isinstance(part, dict):
                continue
            if part.get('type') == 'tool_use' and part.get('name') in ('Agent', 'Task'):
                background = (part.get('input') or {}).get('run_in_background', False)
                agent = {'call_id': part.get('id'), 'spawn_line': line, 'state': 'attempted',
                         'run_in_background': background, 'returns': []}
                agents.append(agent); by_id[part.get('id')] = agent
            elif part.get('type') == 'tool_result' and part.get('tool_use_id') in by_id:
                agent = by_id[part['tool_use_id']]
                body = part.get('content')
                if isinstance(body, list):
                    body = '\n'.join(p.get('text', '') for p in body if isinstance(p, dict) and p.get('type') == 'text')
                agent['result_line'] = line
                if part.get('is_error'):
                    agent['state'] = 'failed'
                elif agent['run_in_background'] is not False:
                    # This result acknowledges a background launch. The parent's
                    # result event cannot establish that the worker returned.
                    agent['state'] = ('started' if agent['run_in_background'] is True
                                      and isinstance(body, str) and body.strip() else 'unverified')
                elif isinstance(body, str) and body.strip():
                    agent.update(state='returned', returns=[{'line': line, 'text': body}])
                else:
                    agent['state'] = 'unverified'
    return agents, complete, [numbered[0][0], numbered[-1][0]]


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
