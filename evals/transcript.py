"""새 세션 기록(JSONL)을 읽어 도구 호출 순서와 마지막 답을 자르지 않고 돌려준다.

Claude(`claude -p --output-format stream-json`)와 Codex(`codex exec --json`) 두 형식을 읽는다.
판정은 이 함수가 돌려준 원문으로 한다. 화면에 보여 줄 때만 줄여 쓴다.
"""
import json


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


if __name__ == "__main__":
    import sys

    s, f = read(sys.argv[1])
    for n, step in enumerate(s, 1):
        print(f"{n}. {step[:200]}")
    print("--- 마지막 답 ---")
    print(f)
