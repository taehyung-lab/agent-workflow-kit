"""승인 관문: 사용자가 이번 메시지로 승인하기 전에는 에이전트가 제품 파일을 쓰지 못하게 막는다.

하네스(Codex·Claude Code) 훅으로 두 번 불린다.
- `approval-gate.py prompt` (UserPromptSubmit): 사용자 메시지가 들어올 때 승인인지 기록한다.
  승인은 그 메시지가 시작한 턴에만 유효하다. 다음 사용자 메시지가 승인이 아니면 다시 닫힌다.
- `approval-gate.py pre` (PreToolUse): 도구를 쓰기 직전에, 승인되지 않은 턴이면 쓰기를 거절한다.
  거절 대상: 파일 쓰기 도구(Write·Edit·MultiEdit·NotebookEdit·apply_patch)로 `work/` 밖을 바꾸는 것,
  읽기 전용 목록에 없는 셸 명령(파일로 내보내기 `>` 포함). 읽기 도구와 읽기 전용 셸 명령은 그대로 둔다.

예: 사용자가 "회원 탈퇴 기능을 만들어 주세요" 라고만 보내면 에이전트는 코드를 읽을 수는 있지만 accounts.py 를 고치려는 순간
거절 사유가 돌아온다. 에이전트는 만들 결과와 미정을 보여 주고 묻는다. 사용자가 "승인합니다" 라고 답한 턴에 쓰기가 열린다.

승인 여부는 사용자 메시지만 보고 정한다(에이전트가 쓴 말은 승인 근거가 아니다). 승인 상태는 `.git/awk-gate/` 에 두는데,
Codex 작업 공간 쓰기 모드에서는 `.git` 이 읽기 전용이라 에이전트가 고칠 수 없다. Claude 는 같은 보호가 없으므로
셸 쓰기가 막힌 상태에서만 지켜진다. 훅 자체가 실패하거나 승인 기록이 없으면 쓰기를 막는 쪽으로 처리한다.
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
"""
import json, os, re, shlex, subprocess, sys
from pathlib import Path

TAG = "[approval-gate]"
# 사용자 메시지가 이 표현을 담으면 승인으로 본다. 부정("승인하지 마세요")은 승인이 아니다.
APPROVE = r"(승인|진행해|진행 해|진행합시다|진행하세요|바로\s*(구현|진행|만들|고쳐|바꿔)|go ahead|approve)"
DENY_WORDS = r"(승인|진행)\S*\s*(하지\s*마|하지\s*말|않|금지|보류|전에)"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
ALLOWED_WRITE_DIR = "work"  # 설계 기록(work/<작업명>/work.md)은 승인 전에도 쓸 수 있다
READ_ONLY = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sed", "awk", "pwd", "echo", "printf", "nl", "sort",
             "uniq", "cut", "tr", "file", "stat", "tree", "du", "which", "type", "jq", "diff", "cmp", "basename", "dirname",
             "realpath", "date", "cd", "true", "test", "[", "less", "column", "od", "xxd", "sha256sum", "shasum", "md5"}
GIT_READ = {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame", "grep", "branch", "remote", "cat-file"}
SEPARATORS = {";", "|", "||", "&&", "&", "(", ")"}
REASON = (f"{TAG} 사용자가 이번 메시지에서 승인하지 않아 제품 파일 쓰기와 읽기 전용이 아닌 셸 명령을 막았습니다. "
          "읽어서 조사한 뒤, 사용자가 받을 결과(원문·계약 근거와 함께)와 아직 정해지지 않은 점, 확인 방법을 보여 주고 "
          "추천과 함께 승인을 물으세요. 우회하지 마세요. 사용자가 '승인합니다'·'진행해 주세요' 처럼 답한 턴에 쓰기가 열립니다. "
          "설계 기록은 work/ 아래에 쓸 수 있습니다.")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def state_dir(cwd):
    r = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--show-toplevel", "--absolute-git-dir"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("git 저장소를 찾지 못했다")
    root, gitdir = r.stdout.split("\n")[:2]
    return Path(root), Path(gitdir, "awk-gate")


def is_approval(prompt):
    return bool(re.search(APPROVE, prompt, re.I)) and not re.search(DENY_WORDS, prompt)


def shell_read_only(cmd):
    """셸 명령이 읽기만 하는지. 판단할 수 없으면 읽기 전용이 아니라고 본다."""
    if "`" in cmd or "$(" in cmd or "<(" in cmd or ">(" in cmd:
        return False
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        return False
    segment, i = [], 0
    while i <= len(tokens):
        tok = tokens[i] if i < len(tokens) else ";"
        if tok in SEPARATORS:
            if segment and not segment_read_only(segment):
                return False
            segment = []
        elif tok.startswith(">") or tok.startswith("&>"):
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if not (target == "/dev/null" or (tok in (">&", "&>") and target.isdigit()) or (tok == ">&" and target == "1")):
                return False
            i += 1
        elif tok == "<" or tok == "<<" or tok == "<<<":
            i += 1
        else:
            segment.append(tok)
        i += 1
    return True


def segment_read_only(seg):
    while seg and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]):  # 앞에 붙은 환경 변수 지정
        seg = seg[1:]
    if not seg:
        return True
    name, args = os.path.basename(seg[0]), seg[1:]
    if name == "rtk":  # rtk 는 명령을 그대로 넘기는 토큰 절약 도구다
        return segment_read_only([a for a in args if a != "proxy"])
    if name == "git":
        sub = [a for a in args if not a.startswith("-")][:1]
        return bool(sub) and sub[0] in GIT_READ and not (sub[0] == "branch" and len([a for a in args if not a.startswith("-")]) > 1)
    if name not in READ_ONLY:
        return False
    if name == "sed" and any(a.startswith("-i") or a == "--in-place" for a in args):
        return False
    if name == "find" and any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls") for a in args):
        return False
    if name == "awk" and any(re.search(r"(system|print[^;]*>|getline)", a) for a in args):
        return False
    return True


def write_targets(tool, inp):
    if tool == "apply_patch":
        return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", str(inp.get("command", "")), re.M)
    return [inp.get("file_path") or inp.get("notebook_path") or ""]


def inside_work(root, path):
    if isinstance(path, tuple):
        path = next((p for p in path if p), "")
    if not path:
        return False
    p = Path(path) if Path(path).is_absolute() else root / path
    try:
        return Path(os.path.realpath(p)).relative_to(os.path.realpath(root)).parts[:1] == (ALLOWED_WRITE_DIR,)
    except ValueError:
        return False


def decide(data, root, approved):
    tool, inp = data.get("tool_name") or "", data.get("tool_input") or {}
    if approved:
        return None
    if tool in WRITE_TOOLS:
        return None if all(inside_work(root, t) for t in write_targets(tool, inp)) else REASON
    if tool in ("Bash", "shell", "exec_command", "local_shell"):
        cmd = inp.get("command", "")
        cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        return None if shell_read_only(cmd) else REASON
    return None  # 읽기·검색·하위 에이전트 등은 막지 않는다(하위 에이전트의 쓰기도 같은 훅을 지난다)


def main(mode, data):
    root, state = state_dir(data.get("cwd"))
    session = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data.get("session_id") or "default"))
    flag = state / f"{session}.approved"
    if mode == "prompt":
        state.mkdir(exist_ok=True)
        approved = is_approval(str(data.get("prompt") or ""))
        flag.write_text("1" if approved else "0")
        log({"event": "prompt", "approved": approved})
        return
    approved = flag.is_file() and flag.read_text().strip() == "1"
    reason = decide(data, root, approved)
    log({"event": "pre", "tool": data.get("tool_name"), "approved": approved, "denied": bool(reason),
         "input": str((data.get("tool_input") or {}).get("command") or (data.get("tool_input") or {}).get("file_path") or "")[:200]})
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}, ensure_ascii=False))


if __name__ == "__main__":
    mode, data = (sys.argv[1] if len(sys.argv) > 1 else "pre"), {}
    try:
        data = json.load(sys.stdin)
        main(mode, data)
    except Exception as e:  # 훅 자체 오류는 쓰기·셸만 막는 쪽으로 처리한다. 읽기 도구는 그대로 둔다.
        log({"error": repr(e)})
        if mode == "pre" and (data.get("tool_name") in WRITE_TOOLS | {"Bash", "shell", "exec_command", "local_shell"} or not data):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": f"{TAG} 승인 관문 오류로 쓰기를 막았습니다: {e!r}"}}, ensure_ascii=False))
