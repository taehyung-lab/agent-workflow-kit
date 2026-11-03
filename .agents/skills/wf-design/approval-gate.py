"""승인 관문: 사용자가 승인하기 전에는 에이전트가 수정 도구로 제품 파일을 쓰지 못하게 막는다.

하네스(Codex·Claude Code) 훅으로 세 번 불린다.
- `approval-gate.py prompt` (UserPromptSubmit): 사용자 메시지가 들어올 때 승인 상태를 정하고, 그때의 제품 파일별 지문을 기록한다.
  - 승인 메시지("승인합니다"·"진행해 주세요" 같은 고정 규칙)면 승인을 연다. 그때 이 작업의 승인 대상 지도와, 모든 지도의
    기준 지문(`## 증거` 절을 뺀 내용)을 묶어 둔다.
  - 철회("취소합니다"·"멈춰 주세요")나, 승인 말이 들어 있지만 승인이 아닌 메시지("승인하지 않습니다"·"진행해도 될까요?")면 닫는다.
  - 그 밖의 메시지(상태 질문 "어디까지 됐어요?" 등)는 승인 상태를 그대로 둔다. 메시지의 뜻을 더 분류하지 않는다.
- `approval-gate.py pre` (PreToolUse): 승인 상태가 아니면 수정 도구(Edit·Write·apply_patch 등)로 `work/` 밖을 바꾸거나,
  이름으로 쓰기임이 드러나는 도구(MCP 파일 쓰기 등)를 쓰려 하면 거절한다. 셸 명령은 내용을 해석하지 않고 거절하지 않는다.
- `approval-gate.py stop` (Stop): 승인 상태가 아닌 턴에 제품 파일이 턴 시작 때와 달라졌으면 바뀐 파일 이름을 알리고 한 번 더 답하게 한다.
  관문은 아무 파일도 되돌리지 않는다. 에이전트가 자기가 바꾼 것이 확실한 파일만 되돌리고, 섞였으면 사용자에게 알린다.
  끝없는 반복을 막으려고 한 턴에 MAX_STOP_BLOCKS 번까지만 그렇게 하고, 그 뒤에도 남으면 턴을 끝내되 표준 오류에 남긴다.

승인 상태 = 열린 승인이 있고, 이 세션이 쓴 지도(승인 대상 지도와 승인 뒤 새로 쓴 지도)의 기준이 승인 때와 같다.
- 승인 대상: 승인 메시지가 경로로 가리킨 지도, 그리고 승인 전에 이 세션이 쓴 지도. 둘 다 없으면 대화 안의 계획에 대한 승인이다.
  다른 세션·사용자가 쓴 다른 작업의 지도는 연결하지 않는다(그 지도가 바뀌어도 이 승인은 닫히지 않는다).
- 이 세션이 지도를 썼는지는 수정 도구의 대상 경로와, 이 세션의 턴 동안 기준이 바뀐 지도로 안다.
- 승인 뒤 이 세션이 지도의 기준을 고치거나(조건 추가·삭제·수정), 지도를 지우거나, 기준이 있는 새 지도를 쓰면 닫힌다.
  `## 증거` 절만 바뀌면 그대로 열려 있다. 에이전트가 파일에 "approved: true" 를 써도 승인이 되지 않는다(사용자 메시지만 연다).

예: 사용자가 "회원 탈퇴 기능을 만들어 주세요" 라고만 보내면 에이전트는 코드를 읽고 검사를 돌릴 수는 있지만 accounts.py 를 Edit 로
고치려는 순간 거절 사유가 돌아온다. "승인합니다" 뒤 "어디까지 됐어요?" 라고 물어도 계속 쓸 수 있다. 에이전트가 승인 뒤
work/withdraw/work.md 의 기준에 조건을 더하면 다음 Edit 이 거절되고 다시 묻게 된다.

보장 범위(설치·문서에 그대로 밝힌다):
- 사전 차단은 수정 도구뿐이다. 셸 쓰기는 미리 막지 않고 턴 끝에 사후 감지한다. 감지 시점에는 이미 쓰기가 일어났다.
- 사후 감지 범위는 git 이 아는 파일과 무시되지 않은 새 파일(키트·하네스 설정·work/ 제외)이다. 무시된 파일·저장소 밖·외부 효과
  (배포·네트워크·데이터베이스)는 보지 않는다. 셸을 막지 않는다는 것은 외부 효과를 허락한다는 뜻이 아니다(AGENTS.md 실행 경계).
- 턴 시작 전부터 있던 사용자의 미커밋 변경은 시작 지문에 들어가므로 알림 대상이 아니다. 턴 도중 사용자·다른 작업이 바꾼 파일은
  에이전트 변경과 구별하지 못하므로 알림에 섞일 수 있다. 그래서 관문은 되돌리지 않고, 일괄 되돌리기도 시키지 않는다.
  같은 이유로 이 세션의 턴 도중 다른 작업이 지도 기준을 바꾸면 이 세션이 쓴 것으로 보고 닫는다(다시 묻는 쪽으로 틀린다).
- 승인 뒤 사용자가 지도에 올리지 않은 범위 변경을 말로만 하면("그런데 재가입은 막아 주세요") 관문은 닫지 않는다. 메시지 뜻을
  분류하지 않기 때문이다. 에이전트가 지도 기준을 고치면 닫히고, 고치지 않은 채 구현하면 독립 검증자가 원문과 대조해 잡아야 한다.
- 관문은 대화 기록을 읽지 않는다. 지도 없이 대화로 승인한 작업은 승인 메시지 원문만 기록하고, 무엇을 승인했는지는 검증자가 본다.
- 생성물(빌드 산출물·캐시)은 프로젝트의 .gitignore 가 정한다. 관문에 언어·도구별 예외는 없다.
- 실수 방지 장치다. 승인 기록(`.git/awk-gate/`)이나 이 파일을 일부러 고치는 것까지 막지는 않는다.
승인이 허용하는 범위(어느 파일·어떤 동작)는 기계로 보지 않는다. 결과가 승인한 내용과 맞는지는 검증자가 본다.
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
"""
import hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

TAG = "[approval-gate]"
# 승인 판별(고정 규칙, 표현 목록을 늘리지 않는다). 사용자의 평소 말투에서 분명한 승인만 잡는다.
# - 승인 말이 완결된 형태로 있고(뒤가 공백·문장 끝·구두점, 조사 "라고·는·도" 등이 바로 붙지 않음) 그 문장이 질문·부정이 아니면 승인.
#   승인 말 앞뒤의 범위 제한("영어 문구 빼고 진행해주세요", "진행해주세요 영어 문구 빼고")은 승인을 막지 않는다.
# - 메시지에 철회 문장("취소합니다", "아직 시작하지 마세요", "멈춰 주세요")이 있으면 승인이 아니다.
# - 애매한 말(예문 속 승인, 철회 뒤 재승인 등)을 다 가리지는 못한다. 그 경우 에이전트가 쓰기 전에 다시 확인한다(AGENTS.md 2항).
_SUFFIX = r"(주세요|주십시오|주시죠|줘요|줘|요)"
APPROVE = (r"(진행\s*해\s*" + _SUFFIX + r"|진행하세요|진행합시다|승인(합니다|할게요|할게|해요|이요)"
           r"|바로\s*(구현|진행|만들어|고쳐|바꿔|수정|적용|반영)\s*(해)?\s*" + _SUFFIX + r"|go ahead|approved?)(?=[\s.!~…,:;。]|$)"
           r"|(진행해|승인)(?=\s*[.!~…]*\s*$)")  # 꼬리 없는 "진행해"·"승인"은 문장을 끝낼 때만
NOT_APPROVE = r"(\?|？|까요|나요|을지|는지|인지|않|안\s*(돼|됩|했)|아니|\bnot\b|don't|never)"  # 승인 말이 든 문장 안의 질문·부정
REVOKE = r"(승인\s*하지\s*않|승인\s*(을\s*)?(취소|철회)|^\s*((취소|중지|보류)\s*(합니다|할게요|해\s*주세요|해요)|멈춰|그만|잠깐|아니요|아뇨|wait\b|stop\b|cancel\b)|(^|\s)(시작하지|진행하지|하지)\s*마(세요|요|십시오)?\s*$|(취소|중지|보류)(합니다|할게요|해\s*주세요)\s*$|멈춰\s*주세요\s*$|무시해\s*주세요\s*$)"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
# 셸 실행 도구. 명령 내용을 해석하지 않는다(쓰기는 턴 끝 사후 감지). write_stdin 은 열린 셸에 입력을 보내는 도구다.
SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "unified_exec", "write_stdin"}
WRITE_NAME = r"(write|edit|create|delete|remove|update|patch|move|rename|insert|replace|upload|commit|push)"
NOT_WRITE = {"TodoWrite", "update_plan", "ExitPlanMode", "EnterPlanMode"}  # 이름에 쓰기 낱말이 있지만 파일을 바꾸지 않는 계획 도구
ALLOWED_WRITE_DIR = "work"  # 작업 지도(work/<작업명>/work.md)는 승인 전에도 쓸 수 있다(승인을 물으려면 먼저 써야 한다)
# 제품 파일에서 빼는 것: 키트(.agents·AGENTS.md·CLAUDE.md), 하네스 설정(.claude·.codex), 작업 지도(work/). 언어·도구별 예외는 두지 않는다.
SPEC = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude", ":(exclude)CLAUDE.md", ":(exclude)AGENTS.md"]
MAP_NAME = "work.md"  # 작업 지도 파일 이름(work/<작업명>/work.md). 이 이름의 파일만 지도로 본다.
MAX_STOP_BLOCKS = 2
SHOWN_FILES = 20  # 알림에 보여 줄 바뀐 파일 수(나머지는 개수만)
REASON = (f"{TAG} 사용자 승인이 없어 제품 파일을 바꾸는 수정 도구를 막았습니다. "
          "읽어서 조사한 뒤, 사용자가 받을 결과(원문·계약 근거와 함께)와 아직 정해지지 않은 점, 확인 방법을 보여 주고 "
          "추천과 함께 승인을 물으세요. 답에는 이 관문·규칙 설명 없이 계획과 질문만 쓰세요. 셸 등 다른 경로로 같은 쓰기를 하지 마세요"
          "(턴 끝에 바뀐 파일이 드러납니다). 사용자가 '승인합니다'·'진행해 주세요' 처럼 답하면 쓰기가 열립니다. "
          "작업 지도는 work/<작업명>/work.md 에 쓸 수 있습니다. 조사용 셸(프로젝트 검사 실행 포함)은 막지 않지만, "
          "배포·삭제·외부 서비스 쓰기 같은 외부 효과는 승인과 별개로 요청이 허용한 범위 안에서만 합니다.")


CHANGED_REASON = (f"{TAG} 승인 뒤 이 작업의 지도 기준이 바뀌어(조건 추가·삭제·수정, 지도 삭제, 기준이 있는 새 지도) 승인이 닫혔습니다: {{maps}}. "
                  "바뀐 기준은 사용자가 승인한 것이 아닙니다. 무엇이 왜 바뀌었는지 보여 주고 다시 승인을 물으세요. "
                  "실행 결과는 `## 증거` 절에만 적으면 승인이 유지됩니다.")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args, ok=(0,)):
    # 저장소 설정의 외부 프로그램(fsmonitor·외부 diff·textconv)이 관문의 상태 수집 중에 실행되지 않게 끈다.
    r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "diff.external=", *args], capture_output=True)
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패")
    return r.stdout


def locate(cwd):
    out = git(cwd or ".", "rev-parse", "--show-toplevel", "--absolute-git-dir").decode().split("\n")
    return Path(out[0]), Path(out[1], "awk-gate")


def product_files(root, seen=None, prefix=""):
    """제품 파일별 지문 {경로: 지문}. 파일 목록만 git 에서 받고 내용은 디스크에서 직접 읽는다
    (git diff 는 저장소 설정의 clean filter·외부 diff 같은 프로그램을 실행할 수 있어 쓰지 않는다)."""
    files = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", *SPEC).decode().split("\0")
    seen = (seen or set()) | {os.path.realpath(root)}
    out = {}
    for f in sorted(set(x for x in files if x)):
        p, name = Path(root, f), prefix + f
        if p.is_symlink():
            out[name] = "link:" + os.readlink(p)
        elif p.is_file():
            mode = "x" if os.access(p, os.X_OK) else "-"  # 실행 권한 변경도 제품 변경이다(git 이 기록하는 유일한 권한)
            try:
                body = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:  # 읽을 수 없게 된 파일도 변경으로 센다(크기·수정 시각·권한으로 지문을 만든다)
                st = p.stat()
                body = f"unreadable:{st.st_mode}:{st.st_size}:{st.st_mtime_ns}"
            out[name] = mode + body
        elif p.is_dir() and (p / ".git").exists() and os.path.realpath(p) not in seen:  # 하위 저장소(몇 단계든): 체크아웃 버전과 파일
            out[name] = "sub:" + git(p, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)).decode().strip()
            out.update(product_files(p, seen, name.rstrip("/") + "/"))
        else:
            out[name] = "missing"
    return out


def criteria(text):
    """지도에서 승인 대상인 부분: `## 증거` 절(다음 `## ` 제목 전까지)을 뺀 나머지의 지문. 증거 갱신은 승인 대상이 아니다."""
    body = re.sub(r"^## 증거[^\n]*\n.*?(?=^## |\Z)", "", text, flags=re.M | re.S)
    body = "\n".join(l.rstrip() for l in body.strip().splitlines())
    return hashlib.sha256(body.encode()).hexdigest() if body else None


def maps(root):
    """work/ 아래 모든 지도의 기준 지문 {경로: 지문}."""
    out = {}
    base = Path(root, ALLOWED_WRITE_DIR)
    for f in sorted(base.rglob(MAP_NAME)) if base.is_dir() else []:
        try:
            out[str(f.relative_to(root))] = criteria(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            out[str(f.relative_to(root))] = "unreadable"
    return out


def rel_map(root, path):
    """수정 도구 대상이 지도면 저장소 기준 상대 경로, 아니면 None."""
    if not path or not inside_work(root, path) or Path(path).name != MAP_NAME:
        return None
    p = Path(path) if Path(path).is_absolute() else root / path
    return str(Path(os.path.realpath(p)).relative_to(os.path.realpath(root)))


def named_maps(root, prompt):
    """승인 메시지가 경로로 가리킨 지도(work/.../work.md 또는 work/<작업명>). 있는 것만."""
    found = []
    for m in re.findall(r"work/[\w./-]+", prompt):
        m = m.rstrip("./")
        cand = m if m.endswith("/" + MAP_NAME) else m + "/" + MAP_NAME
        if Path(root, cand).is_file():
            found.append(cand)
    return found


def mentions_approval(prompt):
    """승인 말(고정 규칙)이 들어 있는가. 물음표도 문장 끝으로 본다("진행해 주세요?" 는 승인 말이 든 질문)."""
    return bool(re.search(APPROVE, re.sub(r"[?？]", ".", prompt), re.I | re.M))


def is_revoke(prompt):
    return any(re.search(REVOKE, x.strip(), re.I) for x in re.split(r"[.!?。？\n]+", prompt) if x.strip())


def is_approval(prompt):
    sentences = [x.strip() for x in re.split(r"[.!?。？\n]+", prompt) if x.strip()]
    if any(re.search(REVOKE, x, re.I) for x in sentences):
        return False
    for m in re.finditer(APPROVE, prompt, re.I | re.M):
        start = max(prompt.rfind(c, 0, m.start()) for c in ".!?。？\n") + 1
        ends = [i for i in (prompt.find(c, m.end()) for c in ".!?。？\n") if i >= 0]
        end = min(ends) + 1 if ends else len(prompt)
        if not re.search(NOT_APPROVE, prompt[start:end], re.I):
            return True
    return False


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


def decide(data, root, approved, reason=REASON):
    tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    if approved or tool in SHELL_TOOLS or tool in NOT_WRITE:
        return None
    if not isinstance(inp, dict):
        return reason
    if tool in WRITE_TOOLS:
        return None if all(inside_work(root, t) for t in write_targets(inp)) else reason
    if re.search(WRITE_NAME, tool, re.I):  # 이름으로 쓰기임이 드러나는 도구(MCP 파일 쓰기 등)
        return reason
    return None  # 읽기·검색·하위 에이전트 등은 막지 않는다(하위 에이전트의 도구도 같은 훅을 지난다)


def changed_files(start, now):
    return sorted(p for p in set(start) | set(now) if start.get(p) != now.get(p))


def stop_message(changed, closed):
    shown = ", ".join(changed[:SHOWN_FILES]) + (f" 외 {len(changed) - SHOWN_FILES}개" if len(changed) > SHOWN_FILES else "")
    why = f"승인 뒤 이 작업의 지도 기준이 바뀌어 승인이 닫혔는데({', '.join(closed)})" if closed else "사용자 승인이 없는데"
    return (f"{TAG} {why} 턴 시작 뒤 제품 파일이 바뀌었습니다: {shown}. "
            "관문은 아무것도 되돌리지 않았습니다. 이 가운데 이번 턴에 당신이 바꾼 것이 확실한 파일만 턴 시작 상태로 되돌리세요. "
            "사용자나 다른 작업이 바꿨을 수 있거나 변경이 섞였으면 되돌리지 말고(checkout·stash·reset 같은 일괄 되돌리기 금지) "
            "어떤 파일이 바뀌었는지 사용자에게 알리세요. 그다음 만들 결과와 미정을 보여 주고 승인을 물으세요.")


def read_json(path, default):
    try:
        v = json.loads(path.read_text())
    except FileNotFoundError:
        return default
    if not isinstance(v, type(default)):
        raise ValueError(f"관문 기록 형식이 다르다: {path.name}")
    return v


def touch(rec, turn_maps, now_maps, extra=()):
    """이 세션이 쓴 지도 목록을 늘린다: 수정 도구 대상(extra)과, 이번 턴 동안 기준이 바뀐 지도(턴 시작 기록이 있을 때만)."""
    t = set(rec.get("touched", [])) | set(extra)
    if turn_maps is not None:
        t |= {m for m in set(turn_maps) | set(now_maps) if turn_maps.get(m) != now_maps.get(m)}
    rec["touched"] = sorted(t)


def status(rec, now_maps):
    """(승인 상태, 기준이 바뀐 지도 목록). 승인이 열려 있어도 이 세션이 쓴 지도의 기준이 승인 때와 다르면 닫힌 것이다."""
    if not rec.get("approved"):
        return False, []
    snap = rec.get("snapshot", {})
    changed = sorted(m for m in set(rec.get("targets", {})) | set(rec.get("touched", [])) if now_maps.get(m) != snap.get(m))
    return not changed, changed


def main(mode, data):
    try:
        root, state = locate(data.get("cwd"))
    except RuntimeError:
        return  # git 저장소가 아니면 상태를 잴 수 없고 키트 설치 프로젝트도 아니다
    if not (root / ".agents" / "agent-workflow-kit.version").is_file():
        return  # 키트가 설치된 프로젝트에서만 동작한다(키트 원본 저장소·관문 파일만 복사된 곳은 그대로 둔다)
    sid = data.get("session_id")
    key = hashlib.sha256(str(sid).encode()).hexdigest()[:24] if sid else None
    if not key:
        if mode == "pre":
            reason = decide(data, root, False)
            if reason:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                         "permissionDecisionReason": reason}}, ensure_ascii=False))
        return
    approval, start, blocks = state / f"{key}.approval", state / f"{key}.start", state / f"{key}.blocks"
    turnmaps = state / f"{key}.maps"
    rec = read_json(approval, {})
    now_maps = maps(root)
    if mode == "prompt":
        state.mkdir(exist_ok=True)
        prompt = str(data.get("prompt") or "")
        if is_approval(prompt):
            # 승인 대상: 메시지가 가리킨 지도 + 승인 전에 이 세션이 쓴 지도. 없으면 대화 안의 계획.
            targets = {m: "승인 메시지가 경로로 가리킴" for m in named_maps(root, prompt)}
            for m in rec.get("touched", []):
                if now_maps.get(m) is not None:  # 승인 때 있는 지도만 대상이다(없는 지도를 승인 뒤 만들면 아래 status 가 닫는다)
                    targets.setdefault(m, "승인 전에 이 세션이 쓴 지도")
            rec = {"approved": True, "prompt": prompt, "targets": targets, "snapshot": now_maps, "touched": rec.get("touched", []),
                   "conversation_only": not targets, "approved_at": time.time()}
            decision = "open"
        elif is_revoke(prompt) or mentions_approval(prompt):
            rec = {"approved": False, "closed_by": prompt, "touched": rec.get("touched", [])}  # 철회, 또는 승인 말이 있지만 승인이 아닌 메시지
            decision = "close"
        else:
            decision = "keep"  # 상태 질문 등: 뜻을 분류하지 않고 승인 상태를 그대로 둔다
        approval.write_text(json.dumps(rec, ensure_ascii=False))
        turnmaps.write_text(json.dumps(now_maps, ensure_ascii=False))
        start.write_text(json.dumps(product_files(root), ensure_ascii=False))
        blocks.write_text("0")
        (state / f"{key}.laststop").unlink(missing_ok=True)  # 앞 턴의 턴 끝 판단을 새 턴에 다시 쓰지 않는다
        ok, closed = status(rec, now_maps)
        log({"event": "prompt", "decision": decision, "approved": ok, "targets": sorted(rec.get("targets", {})), "closed_maps": closed})
        return
    turn_maps = read_json(turnmaps, {}) if turnmaps.is_file() else None
    if mode == "pre":
        tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        extra = [m for m in (rel_map(root, t) for t in write_targets(inp)) if m] if tool in WRITE_TOOLS else []
        touch(rec, turn_maps, now_maps, extra)
        if state.is_dir():
            approval.write_text(json.dumps(rec, ensure_ascii=False))
        ok, closed = status(rec, now_maps)
        reason = decide(data, root, ok, CHANGED_REASON.format(maps=", ".join(closed)) if closed else REASON)
        log({"event": "pre", "tool": data.get("tool_name"), "approved": ok, "denied": bool(reason), "closed_maps": closed,
             "input": str(inp.get("command") or inp.get("cmd") or inp.get("file_path") or "")[:200]})
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}, ensure_ascii=False))
        return
    # stop
    touch(rec, turn_maps, now_maps)
    if state.is_dir() and rec:
        approval.write_text(json.dumps(rec, ensure_ascii=False))
    ok, closed = status(rec, now_maps)
    if ok or not start.is_file():
        return
    begin = read_json(start, {})
    now = product_files(root)
    changed = changed_files(begin, now)
    digest = hashlib.sha256(json.dumps(now, sort_keys=True).encode()).hexdigest()
    begin_digest = hashlib.sha256(json.dumps(begin, sort_keys=True).encode()).hexdigest()
    # 같은 턴 끝에 관문이 두 번 불리면(사용자 전역 훅과 프로젝트 훅을 둘 다 등록·신뢰한 경우) 앞의 판단을 그대로 낸다.
    last = state / f"{key}.laststop"
    if last.is_file():
        prev = json.loads(last.read_text() or "{}")
        if time.time() - prev.get("t", 0) < 5 and prev.get("now") == digest and prev.get("start") == begin_digest:
            if prev.get("out"):
                print(prev["out"])
            return
    n = int(blocks.read_text() or 0) if blocks.is_file() else 0
    log({"event": "stop", "changed": bool(changed), "files": changed[:SHOWN_FILES], "blocks": n, "closed_maps": closed})
    out = ""
    if changed and n < MAX_STOP_BLOCKS:
        blocks.write_text(str(n + 1))
        out = json.dumps({"decision": "block", "reason": stop_message(changed, closed)}, ensure_ascii=False)
        print(out)
    elif changed:
        print(f"{TAG} 승인 없는 턴의 제품 파일 변경이 남은 채 끝났다(알림 {n}회): {', '.join(changed[:SHOWN_FILES])}", file=sys.stderr)
    last.write_text(json.dumps({"t": time.time(), "start": begin_digest, "now": digest, "out": out}, ensure_ascii=False))


if __name__ == "__main__":
    mode, data = (sys.argv[1] if len(sys.argv) > 1 else "pre"), {}
    try:
        data = json.load(sys.stdin)
        main(mode, data)
    except Exception as e:  # 훅 자체 오류: 수정 도구만 막고 읽기·셸은 그대로 둔다(셸은 평소에도 미리 막지 않는다). 턴 끝 검사는 알린다.
        log({"error": repr(e), "mode": mode})
        tool = str(data.get("tool_name") or "") if isinstance(data, dict) else ""
        if mode == "stop":  # 턴 끝 검사를 하지 못했으면 승인 전 변경이 없다고 볼 수 없으므로 알리고 멈춘다
            print(json.dumps({"decision": "block", "reason": f"{TAG} 승인 관문이 제품 파일 상태를 확인하지 못했습니다({e!r}). "
                              "이번 턴에 당신이 바꾼 것이 확실한 제품 파일만 되돌리고, 상태를 사용자에게 알리세요."}, ensure_ascii=False))
        if mode == "pre" and (not data or tool in WRITE_TOOLS or (tool not in SHELL_TOOLS | NOT_WRITE and re.search(WRITE_NAME, tool, re.I))):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": f"{TAG} 승인 관문 오류로 쓰기를 막았습니다: {e!r}"}}, ensure_ascii=False))
        print(f"{TAG} 훅 오류: {e!r}", file=sys.stderr)
