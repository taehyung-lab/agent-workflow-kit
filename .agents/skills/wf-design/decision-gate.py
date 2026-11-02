"""결정 표 관문: 제품 파일을 바꾼 턴의 답이 결정 표로 끝나는지, 표가 지켜졌는지를 모델 판단 없이 검사한다.

하네스(Codex·Claude Code) 훅으로 두 번 불린다.
- `decision-gate.py prompt` (UserPromptSubmit): 사용자 턴이 시작될 때 제품 파일 상태의 지문을 남긴다.
- `decision-gate.py stop` (Stop): 답을 마치려 할 때 그 턴에 제품 파일이 바뀌었으면 마지막 답의 결정 표를 검사한다.

결정 표 형식(AGENTS.md 「필요한 단계만」): `결정 표` 줄 아래 사용자가 받는 결과마다 한 줄
  - <결과> | 원문 "<사용자 메시지에서 그대로 옮긴 말>"
  - <결과> | 계약 <저장소 안 파일 경로>
  - <결과> | 미확인
검사(모두 기계 판정):
  1. 제품 파일을 바꿨는데 결정 표가 없으면 막는다.
  2. 원문 인용이 이 세션의 사용자 메시지에 그대로 없으면 막는다.
  3. 계약 경로가 저장소에 없으면 막는다.
  4. 미확인 줄이 있는데 답이 질문으로 끝나지 않으면 막는다.
  5. 미확인 줄이 있는데 그 턴에 제품 파일을 바꿨으면 한 번 막아, 미확인 결과에 기대는 변경을 되돌리게 한다.
막을 때는 사유를 새 지시로 돌려준다. 한 턴에 MAX_BLOCKS 번까지만 막고, 그 뒤에는 표준 오류에 남기고 통과시킨다.
원문 인용이 결과를 실제로 뒷받침하는지는 판단이므로 여기서 보지 않는다(검토자의 몫).
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
"""
import hashlib, json, os, re, subprocess, sys
from pathlib import Path

MAX_BLOCKS = 3
TAG = "[decision-gate]"  # 훅이 돌려준 지시는 대화 기록에 사용자 메시지로 남으므로, 이 표지가 든 메시지는 원문에서 뺀다
INJECTED = ("# AGENTS.md instructions", "<environment_context", "<user_instructions", "<INSTRUCTIONS>", "<skill>",
            "<system-reminder>", "<command-", "<local-command")
SPEC = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude",
        ":(exclude)**/__pycache__", ":(exclude)CLAUDE.md", ":(exclude)AGENTS.md"]
QUESTION = r"(\?|？|여쭙|정해 주|알려 주|골라 주|답해 주|어느 쪽|어떻게 할까|원하시)"
FORMAT = ("`결정 표` 줄 아래 사용자가 받는 결과마다 `- <결과> | 원문 \"<사용자 메시지에서 그대로 옮긴 말>\"`, "
          "`- <결과> | 계약 <저장소 안 파일 경로>`, `- <결과> | 미확인` 중 하나로 적습니다.")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패")
    return r.stdout


def product_state(root):
    """제품 파일(키트·작업 기록·캐시 제외)의 HEAD 대비 상태 지문."""
    h = hashlib.sha256(git(root, "rev-parse", "HEAD") + git(root, "diff", "--binary", "HEAD", *SPEC))
    for f in sorted(x for x in git(root, "ls-files", "-z", "--others", "--exclude-standard", *SPEC).decode().split("\0") if x):
        p = Path(root, f)
        h.update(f.encode() + (p.read_bytes() if p.is_file() and not p.is_symlink() else b"link"))
    return h.hexdigest()


def user_messages(path):
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
            texts = [c.get("text", "") for c in p.get("content", []) if c.get("type") == "input_text"]
        elif e.get("type") == "user" and not e.get("isMeta"):
            c = (e.get("message") or {}).get("content")
            texts = [c] if isinstance(c, str) else [x.get("text", "") for x in c or [] if x.get("type") == "text"]
        else:
            continue
        out += [t for t in texts if t.strip() and TAG not in t and not t.lstrip().startswith(INJECTED)]
    return out


def squash(s):
    return re.sub(r"\s+", "", s)


def table(answer):
    """마지막 `결정 표` 줄 아래의 `- 결과 | 출처` 줄들. 표가 없으면 None."""
    lines = answer.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip().strip("*#: ").startswith("결정 표")]
    if not starts:
        return None
    rows = []
    for l in lines[starts[-1] + 1:]:
        s = l.strip()
        if not s:
            if rows:
                break
            continue
        if not s.startswith(("-", "*")) or "|" not in s:
            break
        result, source = s.lstrip("-* ").rsplit("|", 1)
        rows.append((result.strip(), source.strip().strip("`")))
    return rows


def problems(answer, rows, root, originals, changed):
    if rows is None or not rows:
        return [f"이번 턴에 제품 파일을 바꿨는데 답에 결정 표가 없습니다. {FORMAT}"]
    said = squash("\n".join(originals))
    found, unknown = [], []
    for result, source in rows:
        if source.startswith("원문"):
            quotes = re.findall(r"[\"“”'‘’「」](.+?)[\"“”'‘’「」]", source)
            if not quotes:
                found.append(f"'{result}' 의 원문 출처에 따옴표로 옮긴 사용자 말이 없습니다.")
            for q in quotes:
                if squash(q) not in said:
                    found.append(f"'{result}' 의 원문 인용 \"{q}\" 가 사용자 메시지에 그대로 없습니다. 사용자 말을 그대로 옮기거나 출처를 미확인으로 고치세요.")
        elif source.startswith("계약"):
            path = source[2:].strip().split()[0] if source[2:].strip() else ""
            if not path or not Path(root, path.split(":")[0]).exists():
                found.append(f"'{result}' 의 계약 경로 `{path}` 가 저장소에 없습니다.")
        elif source.startswith("미확인"):
            unknown.append(result)
        else:
            found.append(f"'{result}' 의 출처 `{source}` 는 원문·계약·미확인 중 하나가 아닙니다. {FORMAT}")
    if unknown and not re.search(QUESTION, answer[-600:]):
        found.append("미확인 결과(" + ", ".join(unknown) + ")가 있는데 답이 사용자에게 묻는 질문으로 끝나지 않습니다. 추천과 함께 물으세요.")
    if unknown and changed:
        found.append("미확인 결과(" + ", ".join(unknown) + ")가 있는데 이번 턴에 제품 파일을 바꿨습니다. 그 결과에 기대는 코드·검사·문서는 답 전 상태로 되돌리고, "
                     "남긴 변경은 미확인 결과와 무관한 것만 두세요. 되돌렸으면 표는 그대로 두고 다시 답하세요.")
    return found


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "stop"
    data = json.load(sys.stdin)
    root = git(data.get("cwd") or ".", "rev-parse", "--show-toplevel").decode().strip()
    state = Path(git(root, "rev-parse", "--absolute-git-dir").decode().strip(), "awk-gate")
    state.mkdir(exist_ok=True)
    session = str(data.get("session_id") or "default")
    start_file = state / f"{session}.start"
    if mode == "prompt":
        start_file.write_text(product_state(root))
        (state / f"{session}.blocks").write_text("0")
        log({"event": "prompt"})
        return 0
    now = product_state(root)
    start = start_file.read_text().strip() if start_file.is_file() else None
    answer = data.get("last_assistant_message") or ""
    rows = table(answer)
    # 턴 시작 지문이 없으면(훅 등록 전 시작 등) HEAD 대비 변경이 있는지로 본다.
    changed = now != start if start else bool(git(root, "status", "--porcelain", *SPEC).strip())
    if not changed:  # 바꾸지 않았거나 되돌려 턴 시작과 같아졌으면 검사하지 않는다
        log({"event": "stop", "skip": "no-change"})
        return 0
    originals = user_messages(data["transcript_path"]) if data.get("transcript_path") else []
    found = problems(answer, rows, root, originals, changed)
    blocks_file = state / f"{session}.blocks"
    blocks = int(blocks_file.read_text() or 0) if blocks_file.is_file() else 0
    log({"event": "stop", "changed": changed, "rows": rows, "problems": found, "blocks": blocks})
    if not found:
        return 0
    if blocks >= MAX_BLOCKS:
        print("decision-gate: 막는 횟수 한도에 닿아 남은 문제를 통과시켰다: " + " / ".join(found), file=sys.stderr)
        return 0
    blocks_file.write_text(str(blocks + 1))
    reason = f"{TAG} 결정 표 검사에서 다음 문제가 있어 답을 끝내지 않았습니다.\n- " + "\n- ".join(found)
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 훅 자체 오류는 답을 막지 않는다. 대신 기록과 표준 오류에 남긴다.
        log({"error": repr(e)})
        print(f"decision-gate: 훅 오류로 결정 표를 검사하지 못했다: {e!r}", file=sys.stderr)
        sys.exit(0)
