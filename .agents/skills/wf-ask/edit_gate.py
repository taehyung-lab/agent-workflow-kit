"""제품 파일을 고치기 직전 관문(Claude PreToolUse 훅, 켤 때만 설치).

요구 표(work/ask/situations.json)가 있으면, 실제 대화 기록(훅 입력의 transcript_path)에서 사용자 턴과 그 사이 보낸 글을
다시 만들어 situations.py 와 같은 확인을 한다. 막는 경우:
  - 미정 줄이 남았다(질문을 보내고 답을 받는다)
  - 사용자 답으로 닫은 줄이나 독자(work/ask/reader.json)가 정한 결과를 바꾼 줄이, 그 줄의 질문을 보낸 뒤의 사용자 말이 아니다
  - 확정 줄의 인용이 대화나, 처음 편집하려던 때 커밋의 합의 문서에 없다
요구 표가 없거나, 고치는 파일이 저장소 밖·work/·.agents/·.claude/ 이면 통과한다.
에이전트가 쓴 파일이 아니라 대화 기록을 읽으므로 사용자 말과 보낸 글은 꾸밀 수 없다.
막을 때는 종료 코드 2 와 이유(stderr)를 낸다. 훅이 고장 나면 막지 않는다(종료 0).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import situations  # noqa: E402

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FREE_DIRS = ("work", ".agents", ".claude", ".git")


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return ""


def turns(transcript):
    """대화 기록에서 사용자 턴 목록과, 턴마다 그 뒤에 보낸 글 목록."""
    users, sent = [], []
    for line in Path(transcript).read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain") or entry.get("isMeta"):
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user":
            if isinstance(content, list) and any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content):
                continue
            text = _text(content).strip()
            if text and not text.startswith("<"):
                users.append(text)
                sent.append("")
        elif entry.get("type") == "assistant" and users:
            sent[-1] += "\n" + _text(content)
    return users, sent


def _renumber(table, users):
    """인용이 처음 나온 사용자 턴을 그 줄의 원문 번호로 쓴다(에이전트가 센 번호에 기대지 않는다)."""
    for item in table.get("situations") or []:
        by = item.get("decided_by") or {}
        if by.get("kind") in ("요청", "답", "기준"):
            quote = situations._plain(str(by.get("quote", "")))
            found = [n for n, text in enumerate(users, 1) if quote and quote in situations._plain(text)]
            if found:
                item["source"] = [found[0]]


def check(event):
    if event.get("tool_name") not in EDIT_TOOLS:
        return None
    # 셸에서 cd 하면 cwd 가 바뀌므로, 저장소 위치는 Claude 가 주는 프로젝트 경로로 정한다
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    target = Path((event.get("tool_input") or {}).get("file_path") or (event.get("tool_input") or {}).get("notebook_path") or "")
    target = (root / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        rel = target.relative_to(root)
    except ValueError:
        return None
    if not rel.parts or rel.parts[0] in FREE_DIRS:
        return None
    table_path = root / "work/ask/situations.json"
    if not table_path.is_file():
        return None
    users, sent = turns(event["transcript_path"])
    table = json.loads(table_path.read_text(encoding="utf-8"))
    _renumber(table, users)
    reader_path = root / "work/ask/reader.json"
    reader = json.loads(reader_path.read_text(encoding="utf-8")) if reader_path.is_file() else {}
    mark = root / "work/ask/.gate-base"  # 첫 편집 시도 때의 커밋: 합의 문서는 이 판에서 찾는다
    if not mark.is_file():
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        mark.write_text(head)
    start = mark.read_text().strip()
    problems = situations.reader_kept(table, reader, users, [root]) if reader else []
    problems += situations.answers_unbound(table, reader, sent)
    result = situations.classify(table, users, [root], start or None)
    problems += [f"{d['id']}: {d['reason']}" for d in result["demoted"]]
    if result["open"]:
        problems.append("미정 줄이 남았다: " + ", ".join(str(i.get("id")) for i in result["open"])
                        + ". 그 줄의 질문(기본값 포함)을 사용자에게 보내고, 답을 받은 뒤 표에 그 답을 인용한다")
    return problems or None


def main():
    try:
        event = json.load(sys.stdin)
        problems = check(event)
    except Exception as exc:  # 훅 고장은 막지 않는다
        print(f"edit_gate: 확인하지 못함({exc})", file=sys.stderr)
        return 0
    if problems:
        print("제품 파일 편집 전 요구 표 확인(work/ask/situations.json)에 걸렸다:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
