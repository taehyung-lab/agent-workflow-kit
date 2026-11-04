"""새 세션 기록(JSONL)을 읽어 도구 호출 순서와 마지막 답을 자르지 않고 돌려준다.

Claude(`claude -p --output-format stream-json`)와 Codex(`codex exec --json`) 두 형식을 읽는다.
판정은 이 함수가 돌려준 원문으로 한다. 화면에 보여 줄 때만 줄여 쓴다.
"""
import json, re


def read(path):
    """(steps, final) 을 돌려준다. steps 는 "도구: 입력" 문자열 목록, final 은 마지막 답 전체다."""
    steps, final = [], ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "assistant":
                for part in event.get("message", {}).get("content", []):
                    if part.get("type") == "tool_use":
                        steps.append(f"{part.get('name')}: {json.dumps(part.get('input'), ensure_ascii=False)}")
                    elif part.get("type") == "text":
                        final = part.get("text", "")
            elif kind == "result":
                final = event.get("result") or final
            elif kind == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "command_execution":
                    steps.append("cmd: " + item.get("command", ""))
                elif item.get("type") == "file_change":
                    steps.append("edit: " + json.dumps([c.get("path") for c in item.get("changes", [])], ensure_ascii=False))
                elif item.get("type") == "agent_message":
                    final = item.get("text", "")
            elif kind in ("turn.failed", "error"):
                steps.append("ERROR: " + json.dumps(event, ensure_ascii=False))
    return steps, final


def commands(path):
    """셸 명령과 그 결과를 짝지어 순서대로 돌려준다: [{"command", "output", "exit_code"}].
    Claude 는 Bash 호출(tool_use id)을 같은 id 의 tool_result 와 잇고(is_error 면 머리줄 "Exit code N" 의 N 을 종료 코드로 하고 출력에서 뺀다. 없으면 1),
    Codex 는 command_execution 의 aggregated_output·exit_code 를 쓴다. 결과가 기록에 없으면 output·exit_code 는 None 이다."""
    found, by_id = [], {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
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
