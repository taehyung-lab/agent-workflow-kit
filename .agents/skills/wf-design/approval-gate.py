"""승인 관문: 사용자가 이번 메시지로 승인하기 전에는 에이전트가 제품 파일을 쓰지 못하게 막는다.

하네스(Codex·Claude Code) 훅으로 세 번 불린다.
- `approval-gate.py prompt` (UserPromptSubmit): 사용자 메시지가 들어올 때 승인인지와, 그때의 제품 파일 상태 지문을 기록한다.
  승인은 그 메시지가 시작한 턴에만 유효하다. 다음 사용자 메시지가 승인이 아니면 다시 닫힌다.
- `approval-gate.py pre` (PreToolUse): 승인되지 않은 턴에 쓰기 도구로 `work/` 밖을 바꾸거나,
  읽기 전용으로 확인되지 않는 셸 명령·이름으로 쓰기임이 드러나는 도구를 쓰려 하면 거절한다.
- `approval-gate.py stop` (Stop): 승인되지 않은 턴인데 제품 파일 상태가 턴 시작 때와 달라졌으면(셸의 숨은 쓰기 등
  PreToolUse 가 놓친 경로) 답을 끝내지 못하게 하고 되돌리게 한다.

예: 사용자가 "회원 탈퇴 기능을 만들어 주세요" 라고만 보내면 에이전트는 코드를 읽을 수는 있지만 accounts.py 를 고치려는 순간
거절 사유가 돌아온다. 에이전트는 만들 결과와 미정을 보여 주고 묻는다. 사용자가 "승인합니다" 라고 답한 턴에 쓰기가 열린다.

전제: 에이전트가 일부러 관문을 부수려 하지는 않지만 묻지 않고 넘어가려 할 수는 있다. 승인 기록(`.git/awk-gate/`)과
이 파일은 Codex 작업 공간 쓰기 모드에서는 각각 읽기 전용(.git)·작업 공간 안이다. Claude 는 같은 보호가 없다.
의도적인 위조까지 막으려면 하네스의 읽기 전용 실행 모드(운영체제 수준 쓰기 제한)를 함께 써야 한다.
승인이 허용하는 범위(어느 파일·어떤 동작)는 기계로 보지 않는다. 결과가 승인한 내용과 맞는지는 검증자가 본다.
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
"""
import hashlib, json, os, re, subprocess, sys
from pathlib import Path

TAG = "[approval-gate]"
# 사용자 메시지가 승인 표현을 담고, 부정·질문·조건·인용 표지가 없을 때만 승인으로 본다.
APPROVE = r"(승인합니다|승인할게|승인해요|승인이요|^\s*승인\s*[.!]?\s*$|진행해|진행 해|진행합시다|진행하세요|바로\s*(구현|진행|만들|고쳐|바꿔)|go ahead|approved?\b)"
NOT_APPROVE = r"(마세요|말고|말아|하지\s*마|않|보류|금지|여부|검토|예시|인지|일까|할까|나요|\?|？|다만|단,|제외|빼고|\bnot\b|don't|\bno\b)"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "unified_exec"}
WRITE_NAME = r"(write|edit|create|delete|remove|update|patch|move|rename|insert|replace|upload|stdin|commit|push)"
NOT_WRITE = {"TodoWrite", "update_plan", "ExitPlanMode", "EnterPlanMode"}  # 이름에 쓰기 낱말이 있지만 파일을 바꾸지 않는 계획 도구
ALLOWED_WRITE_DIR = "work"  # 설계 기록(work/<작업명>/work.md)은 승인 전에도 쓸 수 있다
SPEC = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude",
        ":(exclude)**/__pycache__/**", ":(exclude)**/.pytest_cache/**", ":(exclude)**/*.pyc", ":(exclude)CLAUDE.md", ":(exclude)AGENTS.md"]
READ_ONLY = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sed", "awk", "pwd", "echo", "printf", "nl", "sort",
             "uniq", "cut", "tr", "file", "stat", "tree", "du", "which", "type", "jq", "diff", "cmp", "basename", "dirname",
             "realpath", "date", "cd", "true", "test", "[", "column", "od", "sha256sum", "shasum", "md5"}
GIT_READ = {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame", "grep", "cat-file", "shortlog", "describe"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
RTK_READ = {"read", "ls", "grep", "find", "json", "log", "diff", "deps", "gain"}
OPERATORS = ["&&", "||", ";;", ">>", "&>", ">&", "<>", "<<<", "<<", ";", "|", "&", ">", "<", "(", ")"]
GLOB = "\x01"  # 따옴표 밖의 {} * ? [ ~: 셸이 실행 때 다른 인자로 펼칠 수 있다
EXPANDS = "\x00$"  # 셸이 실행 때 펼치는 $(작은따옴표 밖). 환경 변수 지정 값에서만 허용한다
SHELL_WORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "fi", "done", "}"}
MAX_STOP_BLOCKS = 2
TEST_RUN = re.compile(r"^(rtk\s+)?(python3?(\s+-B)?\s+-m\s+(unittest|pytest)|pytest)"
                      r"(\s+(discover|-q|-v|-x|(-k|-s|-p|-t)\s+[\w./:*?-]+|[\w./:][\w./:-]*))*$")
# 패키지 매니저로 돌리는 프로젝트의 기존 검사 스크립트(테스트·타입 검사·린트·전체 검사). 스크립트 이름 뒤에는 파일 경로만 받는다
# (옵션을 붙이면 출력 파일·고치기 같은 쓰기가 열릴 수 있어 승인이 필요하다). 도구를 직접 부르는 실행(npx tsc 등)도 승인이 필요하다.
JS_CHECK = re.compile(r"^(rtk\s+)?(pnpm|npm|yarn|bun)(\s+(--dir|-C|--filter|--prefix|--workspace|-w)\s+[^\s-]\S*)*(\s+run)?"
                      r"\s+(test|typecheck|type-check|lint|check)(\s+[^\s-][^\s]*)*$")
VERSION = re.compile(r"^(rtk\s+)?(command\s+-v\s+[\w.-]+|[\w.-]+\s+(--version|-v|-V))$")  # 도구 존재·버전 확인
REASON = (f"{TAG} 사용자가 이번 메시지에서 승인하지 않아 제품 파일 쓰기와 읽기 전용으로 확인되지 않는 셸 명령을 막았습니다. "
          "읽어서 조사한 뒤, 사용자가 받을 결과(원문·계약 근거와 함께)와 아직 정해지지 않은 점, 확인 방법을 보여 주고 "
          "추천과 함께 승인을 물으세요. 다른 명령으로 우회하지 마세요. 사용자가 '승인합니다'·'진행해 주세요' 처럼 답한 턴에 쓰기가 열립니다. "
          "설계 기록은 work/ 아래에 쓸 수 있습니다.")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args, ok=(0,)):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패")
    return r.stdout


def locate(cwd):
    out = git(cwd or ".", "rev-parse", "--show-toplevel", "--absolute-git-dir").decode().split("\n")
    return Path(out[0]), Path(out[1], "awk-gate")


def product_state(root):
    """제품 파일(work/·키트·지침·캐시 제외)의 HEAD 대비 상태 지문."""
    head = git(root, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)).strip()
    h = hashlib.sha256(head + (git(root, "diff", "--binary", "HEAD", *SPEC) if head else b""))
    for f in sorted(x for x in git(root, "ls-files", "-z", "--others", "--exclude-standard", *SPEC).decode().split("\0") if x):
        p = Path(root, f)
        h.update(f.encode() + b"\0" + (p.read_bytes() if p.is_file() and not p.is_symlink() else b"link"))
    return h.hexdigest()


def is_approval(prompt):
    return bool(re.search(APPROVE, prompt, re.I | re.M)) and not re.search(NOT_APPROVE, prompt, re.I)


def tokens(cmd):
    """따옴표를 지키며 셸 명령을 낱말과 연산자로 나눈다. (낱말, 연산자인가) 목록. 해석할 수 없으면 None."""
    out, cur, quoted, i, q = [], "", False, 0, None

    def flush():
        nonlocal cur, quoted
        if cur or quoted:
            out.append((cur, False))
        cur, quoted = "", False

    while i < len(cmd):
        c = cmd[i]
        if q:
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < len(cmd):
                i += 1; cur += cmd[i]
            else:
                cur += EXPANDS if (c == "$" and q == '"') else c
        elif c in "'\"":
            q, quoted = c, True
        elif c == "\\" and i + 1 < len(cmd):
            i += 1; cur += cmd[i]; quoted = True
        elif c in " \t":
            flush()
        elif c == "\n":
            flush(); out.append((";", True))
        else:
            op = next((o for o in OPERATORS if cmd.startswith(o, i)), None)
            if op:
                flush(); out.append((op, True)); i += len(op); continue
            cur += EXPANDS if c == "$" else (GLOB + c if c in "{}*?[~" else c)
        i += 1
    if q:
        return None
    flush()
    return out


def shell_read_only(cmd):
    """셸 명령이 읽기만 하는지. 판단할 수 없으면 읽기 전용이 아니라고 본다."""
    if not cmd.strip() or "`" in cmd or "$(" in cmd or "<(" in cmd or ">(" in cmd:
        return False
    toks = tokens(cmd)
    if toks is None:
        return False
    toks.append((";", True))
    segment, i = [], 0
    while i < len(toks):
        tok, op = toks[i]
        if op and tok in ("&&", "||", ";", ";;", "|", "&", "(", ")"):
            if segment and not segment_read_only(segment):
                return False
            segment = []
        elif op and tok in (">", ">>", "&>", ">&"):
            target = toks[i + 1][0] if i + 1 < len(toks) and not toks[i + 1][1] else ""
            if not (target == "/dev/null" or (tok == ">&" and target.isdigit())):
                return False
            if segment and segment[-1].isdigit():
                segment.pop()  # 2>/dev/null 의 2
            i += 1
        elif op and tok in ("<", "<<", "<<<"):
            i += 1
        elif op:
            return False  # <> 처럼 읽기·쓰기를 겸하는 연산자
        else:
            segment.append(tok)
        i += 1
    return True


def segment_read_only(seg):
    while seg and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]) or seg[0] in SHELL_WORDS):  # 환경 변수 지정·if/then 같은 셸 문법어
        seg = seg[1:]
    if seg[:1] == ["for"] or seg in (["fi"], ["done"], ["}"], ["esac"]):
        return True
    if not seg:
        return True
    name, args = seg[0], seg[1:]
    if "/" in name:  # 경로로 부른 실행 파일은 이름만으로 믿지 않는다
        return False
    if name in ("sh", "bash", "zsh") and len(args) == 2 and args[0] in ("-c", "-lc"):  # sh -c '<읽기 명령>'
        return shell_read_only(args[1])
    if name == "rtk" and [a for a in args if not a.startswith("-")][:1] == ["proxy"]:  # rtk proxy <명령>: 명령을 그대로 실행
        return segment_read_only(args[[a for a in args].index("proxy") + 1:])
    if name in ("export", "unset"):  # 이 셸의 환경 변수만 바꾼다(예: Node 버전에 맞춘 PATH)
        return all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*(=.*)?$", x, re.S) for x in args)
    if name == "env":  # env -u NAME NAME=VALUE <명령>: 환경만 바꿔 뒤 명령을 실행한다
        rest = list(args)
        while rest and (rest[0] in ("-u", "--unset") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[0])):
            rest = rest[2:] if rest[0] in ("-u", "--unset") else rest[1:]
        return segment_read_only(rest) if rest else True
    if any(EXPANDS in x for x in seg):  # 실행 때 펼쳐질 값($VAR)은 어떤 인자·옵션이 될지 미리 알 수 없다
        return False
    joined = " ".join(seg)
    if GLOB in joined and (TEST_RUN.match(joined.replace(GLOB, "")) or JS_CHECK.match(joined.replace(GLOB, ""))):
        return False  # 검사 실행에 펼쳐질 인자를 넘기면 어떤 옵션이 될지 미리 알 수 없다
    joined, seg = joined.replace(GLOB, ""), [x.replace(GLOB, "") for x in seg]
    name, args = seg[0], seg[1:]
    if VERSION.match(joined):
        return True
    if TEST_RUN.match(joined) or JS_CHECK.match(joined):  # 조사 중 기존 검사 실행은 둔다. 숨은 쓰기는 턴 끝 상태 검사가 잡는다
        return True
    if name == "rtk":  # rtk 는 명령 출력을 줄여 주는 도구다
        while args and args[0].startswith("-"):  # rtk 자체 선택 항목(--raw-output=true 등)
            args = args[1:]
        if args[:1] == ["proxy"]:
            return segment_read_only(args[1:])
        if args and (args[0] in READ_ONLY or args[0] in ("git", "rm")):
            return segment_read_only(args)
        return bool(args) and args[0] in RTK_READ and not any(a.startswith("-o") or a.startswith("--output") for a in args)
    if name == "git":
        rest = list(args)
        while rest and rest[0].startswith("-"):
            opt = rest.pop(0)
            if opt in GIT_VALUE_OPTS and rest:
                rest.pop(0)
        return bool(rest) and rest[0] in GIT_READ and not any(a.startswith("--output") or a == "-o" for a in rest)
    if name == "rm":  # 테스트가 만든 캐시(__pycache__·.pytest_cache)를 치우는 것만 둔다
        targets = [a for a in args if not a.startswith("-")]
        return bool(targets) and all(re.search(r"(^|/)(__pycache__|\.pytest_cache)(/|$)", a) and ".." not in a for a in targets)
    if name not in READ_ONLY:
        return False
    if name == "sed":
        if any(a.startswith("-i") or a.startswith("--in-place") or a in ("-f", "--file") for a in args):
            return False
        scripts = [a for a in args if not a.startswith("-")][:1]
        write_cmd = r"(^|[;{}\s\d$!])[wWe](\s|$)"  # w 파일, W 파일, e 명령
        write_flag = r"s(.)(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1[gpIiM0-9]*[we]"  # s/a/b/w 파일
        return not any(re.search(write_cmd, s) or re.search(write_flag, s) for s in scripts)
    if name == "sort" and any(a.startswith("-o") or a.startswith("--output") for a in args):
        return False
    if name == "uniq" and len([a for a in args if not a.startswith("-")]) > 1:  # uniq 입력 출력: 두 번째 파일에 쓴다
        return False
    if (name == "tree" and any(a.startswith("-o") for a in args)) or (name == "file" and any(a.startswith("-C") for a in args)):
        return False
    if name == "date" and any(not a.startswith(("+", "-u", "-R", "-I", "-r", "-j", "-f")) or a == "-s" for a in args):
        return False  # 날짜 출력 형식·변환만 둔다(시스템 날짜 설정 제외)
    if name == "find" and any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls") for a in args):
        return False
    if name == "awk" and any(a == "-f" or re.search(r"(system|print[^;]*>|getline|close|fflush)", a) for a in args):
        return False
    return True


def write_targets(inp):
    text = "\n".join(str(v) for v in inp.values() if isinstance(v, str))
    found = [a or b for a, b in re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", text, re.M)]
    return found or [inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""]


def inside_work(root, path):
    if not path:
        return False
    p = Path(path) if Path(path).is_absolute() else root / path
    try:
        return Path(os.path.realpath(p)).relative_to(os.path.realpath(root)).parts[:1] == (ALLOWED_WRITE_DIR,)
    except ValueError:
        return False


def decide(data, root, approved):
    tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    if approved:
        return None
    if not isinstance(inp, dict):
        return REASON
    if tool in WRITE_TOOLS:
        return None if all(inside_work(root, t) for t in write_targets(inp)) else REASON
    if tool in SHELL_TOOLS:
        cmd = inp.get("command", inp.get("cmd", ""))
        cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        return None if shell_read_only(cmd) else REASON
    if tool not in NOT_WRITE and re.search(WRITE_NAME, tool, re.I):  # 이름으로 쓰기임이 드러나는 도구(MCP 파일 쓰기, 열린 셸에 입력 보내기 등)
        return REASON
    return None  # 읽기·검색·하위 에이전트 등은 막지 않는다(하위 에이전트의 도구도 같은 훅을 지난다)


def main(mode, data):
    root, state = locate(data.get("cwd"))
    sid = data.get("session_id")
    key = hashlib.sha256(str(sid).encode()).hexdigest()[:24] if sid else None
    flag, start, blocks = (state / f"{key}.approved", state / f"{key}.start", state / f"{key}.blocks") if key else (None,) * 3
    if mode == "prompt":
        if not key:
            return
        state.mkdir(exist_ok=True)
        approved = is_approval(str(data.get("prompt") or ""))
        flag.write_text("1" if approved else "0")
        start.write_text(product_state(root))
        blocks.write_text("0")
        log({"event": "prompt", "approved": approved})
        return
    approved = bool(key) and flag.is_file() and flag.read_text().strip() == "1"
    if mode == "stop":
        if approved or not key or not start.is_file():
            return
        changed = product_state(root) != start.read_text().strip()
        n = int(blocks.read_text() or 0) if blocks.is_file() else 0
        log({"event": "stop", "changed": changed, "blocks": n})
        if changed and n < MAX_STOP_BLOCKS:
            blocks.write_text(str(n + 1))
            print(json.dumps({"decision": "block", "reason": f"{TAG} 사용자가 이번 메시지에서 승인하지 않았는데 제품 파일이 턴 시작 때와 달라졌습니다. "
                              "이번 턴에 바꾼 제품 파일을 턴 시작 상태로 되돌리고(사용자가 이전에 만든 변경은 그대로 둡니다), "
                              "만들 결과와 미정을 보여 주고 승인을 물으세요."}, ensure_ascii=False))
        elif changed:
            print(f"{TAG} 미승인 변경이 남은 채 끝났다(되돌리기 요청 {n}회)", file=sys.stderr)
        return
    reason = decide(data, root, approved)
    inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    log({"event": "pre", "tool": data.get("tool_name"), "approved": approved, "denied": bool(reason),
         "input": str(inp.get("command") or inp.get("cmd") or inp.get("file_path") or "")[:200]})
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}, ensure_ascii=False))


if __name__ == "__main__":
    mode, data = (sys.argv[1] if len(sys.argv) > 1 else "pre"), {}
    try:
        data = json.load(sys.stdin)
        main(mode, data)
    except Exception as e:  # 훅 자체 오류: 쓰기·셸만 막고 읽기 도구는 그대로 둔다. 턴 끝 검사는 기록만 남긴다.
        log({"error": repr(e), "mode": mode})
        tool = str(data.get("tool_name") or "") if isinstance(data, dict) else ""
        if mode == "pre" and (not data or tool in WRITE_TOOLS | SHELL_TOOLS or re.search(WRITE_NAME, tool, re.I)):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": f"{TAG} 승인 관문 오류로 쓰기를 막았습니다: {e!r}"}}, ensure_ascii=False))
        print(f"{TAG} 훅 오류: {e!r}", file=sys.stderr)
