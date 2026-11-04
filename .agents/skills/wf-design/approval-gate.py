"""승인 관문: 사용자가 승인하기 전에는 에이전트가 수정 도구로 제품 파일을 쓰지 못하게 막는다.

하네스(Codex·Claude Code) 훅으로 세 번 불린다.
- `prompt` (UserPromptSubmit): 사용자 메시지가 승인인지 정하고, 턴 시작의 제품 파일 지문을 남긴다.
- `pre` (PreToolUse): 승인 상태가 아니면 수정 도구로 `work/` 밖을 바꾸거나 이름으로 쓰기임이 드러나는 도구(MCP 파일 쓰기 등)를 거절한다.
  셸 명령은 해석하지 않고 거절하지 않는다(어느 언어의 검사든 승인 없이 돈다).
- `stop` (Stop): 승인 상태가 아닌데 턴 시작 뒤 제품 파일이 바뀌었으면 바뀐 파일 이름을 알리고 한 번 더 답하게 한다(사후 감지).
  관문은 아무것도 되돌리지 않는다.

승인 수명·보장 범위·한계는 .agents/skills/README.md 「승인 관문」이 원본이다(여기에 다시 적지 않는다). 요약: 대화 승인은 그 턴만,
지도 승인은 승인 턴이 끝날 때의 `## 기준`에 묶여 기준 변경·새 지도·철회·지도 정리 때 닫힌다. 승인 턴 안의 지도 쓰기는 옮겨 적기로 본다.

셸 명령: `approval-gate.py status [--session ID]` 는 승인 상태를 JSON 으로 보여 준다(평가 실행기가 쓴다). 승인을 바꾸지 않는다.
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄, 측정용). AWK_GATE_PROMPT_FROM=runner(평가 실행기가 보낸 사용자 아닌 입력: 승인을 바꾸지 않는다).
"""
import hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

TAG = "[approval-gate]"
# 승인 판별(고정 규칙, 표현 목록을 늘리지 않는다). 사용자의 평소 말투에서 분명한 승인만 잡는다.
# - 승인 말이 완결된 형태로 있고 그 문장이 질문·부정이 아니면 승인. 앞뒤의 범위 제한("영어 문구 빼고 진행해주세요")은 막지 않는다.
# - 메시지에 철회 문장("취소합니다", "아직 시작하지 마세요")이 있으면 승인이 아니다.
# - 애매한 말(예문 속 승인 등)은 다 가리지 못한다. 그 경우 에이전트가 쓰기 전에 다시 확인한다(AGENTS.md 2항).
_SUFFIX = r"(주세요|주십시오|주시죠|줘요|줘|요)"
APPROVE = (r"(진행\s*해\s*" + _SUFFIX + r"|진행하세요|진행합시다|승인(합니다|할게요|할게|해요|이요)"
           r"|바로\s*(구현|진행|만들어|고쳐|바꿔|수정|적용|반영)\s*(해)?\s*" + _SUFFIX + r"|go ahead|approved?)(?=[\s.!~…,:;。]|$)"
           r"|(진행해|승인)(?=\s*[.!~…]*\s*$)")  # 꼬리 없는 "진행해"·"승인"은 문장을 끝낼 때만
NOT_APPROVE = r"(\?|？|까요|나요|을지|는지|인지|않|안\s*(돼|됩|했)|아니|\bnot\b|don't|never)"  # 승인 말이 든 문장 안의 질문·부정
REVOKE = r"(승인\s*하지\s*않|승인\s*(을\s*)?(취소|철회)|^\s*((취소|중지|보류)\s*(합니다|할게요|해\s*주세요|해요)|멈춰|그만|잠깐|아니요|아뇨|wait\b|stop\b|cancel\b)|(^|\s)(시작하지|진행하지|하지)\s*마(세요|요|십시오)?\s*$|(취소|중지|보류)(합니다|할게요|해\s*주세요)\s*$|멈춰\s*주세요\s*$|무시해\s*주세요\s*$)"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}
SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "unified_exec", "write_stdin"}  # 내용을 해석하지 않는다
WRITE_NAME = r"(write|edit|create|delete|remove|update|patch|move|rename|insert|replace|upload|commit|push)"
NOT_WRITE = {"TodoWrite", "update_plan", "ExitPlanMode", "EnterPlanMode"}  # 이름에 쓰기 낱말이 있지만 파일을 바꾸지 않는 계획 도구
ALLOWED_WRITE_DIR = "work"  # 작업 지도는 승인 전에도 쓸 수 있다(승인을 물으려면 먼저 써야 한다)
# 제품 파일에서 빼는 것: 키트(.agents·AGENTS.md·CLAUDE.md), 하네스 설정(.claude·.codex), 작업 지도(work/). 언어·도구별 예외는 없다.
SPEC = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude", ":(exclude)CLAUDE.md", ":(exclude)AGENTS.md"]
MAP_NAME = "work.md"
STATE_DIR = "awk-gate"  # .git/awk-gate: 훅만 쓴다
MAX_STOP_BLOCKS = 2
SHOWN_FILES = 20
REASON = (f"{TAG} 사용자 승인이 없어 제품 파일을 바꾸는 수정 도구를 막았습니다. "
          "정해지지 않은 결정이 있으면 질문과 추천을 쓰세요. 결정이 다 정해졌으면 바꿀 내용과 확인 방법을 짧게 보여 주고 승인을 물으세요"
          "(여러 턴이 걸리는 일은 먼저 work/<작업명>/work.md 에 지도를 쓰고 그 지도로 승인을 받습니다). "
          "답에는 이 관문 설명을 쓰지 마세요. 셸 등 다른 경로로 같은 쓰기를 하지 마세요(턴 끝에 바뀐 파일이 드러납니다). "
          "배포·삭제·외부 서비스 쓰기 같은 외부 효과는 승인과 별개로 요청이 허용한 범위에서만 합니다.")
CLOSED_REASON = (f"{TAG} 승인한 작업 지도의 `## 기준`이 바뀌었거나 승인 밖의 새 지도가 생겨 승인이 닫혔습니다: {{maps}}. "
                 "무엇이 바뀌었는지(새 작업이면 그 계획을) 보여 주고 다시 승인을 물으세요. 실행 결과·설계는 `## 기준` 밖에 적으면 승인이 유지됩니다.")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args, ok=(0,), input=None):
    # 저장소 설정의 외부 프로그램(fsmonitor·외부 diff)이 상태 수집 중에 실행되지 않게 끈다.
    r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "diff.external=", *args], capture_output=True, input=input)
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패")
    return r.stdout


def locate(cwd):
    out = git(cwd or ".", "rev-parse", "--show-toplevel", "--absolute-git-dir").decode().split("\n")
    return Path(out[0]), Path(out[1], STATE_DIR)


def product_files(root, seen=None, prefix=""):
    """제품 파일별 지문 {경로: 지문}. 목록만 git 에서 받고 내용은 디스크에서 직접 읽는다(clean filter 를 실행하지 않게)."""
    files = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", *SPEC).decode().split("\0")
    seen = (seen or set()) | {os.path.realpath(root)}
    out = {}
    for f in sorted(set(x for x in files if x)):
        p, name = Path(root, f), prefix + f
        if p.is_symlink():
            out[name] = "link:" + os.readlink(p)
        elif p.is_file():
            mode = "x" if os.access(p, os.X_OK) else "-"
            try:
                body = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                st = p.stat()
                body = f"unreadable:{st.st_mode}:{st.st_size}:{st.st_mtime_ns}"
            out[name] = mode + body
        elif p.is_dir() and (p / ".git").exists() and os.path.realpath(p) not in seen:  # 하위 저장소
            out[name] = "sub:" + git(p, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)).decode().strip()
            out.update(product_files(p, seen, name.rstrip("/") + "/"))
        else:
            out[name] = "missing"
    return out


def snapshot_files(root, state):
    """지금 제품 파일 내용을 git 객체로 보존하고 목록 파일 이름을 돌려준다. 지도 승인 때 남겨 검증기가 승인 뒤 변경만 보게 한다.
    하위 저장소·읽을 수 없는 파일은 내용을 보존하지 못했다고 적는다(검증기는 미확인으로 다룬다)."""
    files = sorted(set(x for x in git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", *SPEC).decode().split("\0") if x))
    out, regular = {}, []
    for f in files:
        p = Path(root, f)
        if p.is_symlink():
            out[f] = {"link": os.readlink(p)}
        elif p.is_file() and "\n" not in f and os.access(p, os.R_OK):
            regular.append(f)
        elif p.exists():
            out[f] = {"unsaved": "하위 저장소·읽을 수 없는 파일은 내용을 보존하지 않았다"}
    blobs = git(root, "hash-object", "-w", "--no-filters", "--stdin-paths", input="\n".join(regular).encode()).decode().split() if regular else []
    if len(blobs) != len(regular):
        raise RuntimeError("시작 상태 보존 실패")
    for f, b in zip(regular, blobs):
        out[f] = {"blob": b, "exec": os.access(Path(root, f), os.X_OK)}
    body = json.dumps(out, ensure_ascii=False, sort_keys=True)
    name = f"snap-{hashlib.sha256(body.encode()).hexdigest()[:20]}.json"
    if not (state / name).is_file():
        (state / name).write_text(body)
    return name


def criteria_text(text):
    """작업 지도의 `## 기준` 절 본문(빈 줄·줄 끝 공백 제외). 절이 없으면 None. 이 절만 승인 대상이다."""
    m = re.search(r"^## 기준[^\n]*\n(.*?)(?=^#{1,2} |\Z)", text or "", re.M | re.S)
    if not m:
        return None
    return "\n".join(l.rstrip() for l in m.group(1).splitlines() if l.strip())


def criteria(text):
    body = criteria_text(text)
    return None if body is None else hashlib.sha256(body.encode()).hexdigest()


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


def inside(root, path, top):
    if not path:
        return False
    p = os.path.realpath(Path(path) if Path(path).is_absolute() else root / path)
    top = os.path.realpath(top)
    return p == top or p.startswith(top + os.sep)


def last_answer(path):
    """하네스가 넘긴 대화 기록(transcript_path)에서 에이전트의 마지막 답 글. 읽지 못하면 None.
    Claude Code 기록({"type": "assistant", "message": ...})과 Codex 기록({"type": "response_item", "payload": ...})을 읽는다.
    사용자 메시지가 나오면 새 답이 시작된다(도구 결과만 든 줄은 사용자 메시지로 보지 않는다). 기록 끝 2MB 만 읽는다."""
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    answers, cur = [], []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        msg = e.get("message") if e.get("type") in ("user", "assistant") else (e.get("payload") if e.get("type") == "response_item" else None)
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant"):
            continue
        content = msg.get("content")
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content if isinstance(content, list) else []
        texts = [str(x.get("text") or "") for x in parts if isinstance(x, dict) and x.get("type") in ("text", "output_text", "input_text")]
        if msg["role"] == "user":
            if texts:  # 사용자 메시지(도구 결과만 든 줄은 아님): 앞 답을 닫는다
                if cur:
                    answers.append("\n".join(cur))
                cur = []
        else:
            cur += [t for t in texts if t.strip()]
    if cur:
        answers.append("\n".join(cur))
    return answers[-1] if answers else ""


def rel_map(root, path):
    """수정 도구 대상이 지도면 저장소 기준 상대 경로, 아니면 None."""
    if not inside(root, path, Path(root, ALLOWED_WRITE_DIR)) or Path(path).name != MAP_NAME:
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


def verify_record(root, path):
    """경로가 검토기의 기록(work/<작업명>/verify/ 또는 지도 없는 검토의 work/review/)인가."""
    if not inside(root, path, Path(root, ALLOWED_WRITE_DIR)):
        return False
    rel = Path(os.path.realpath(Path(path) if Path(path).is_absolute() else root / path)).relative_to(os.path.realpath(root)).parts
    return (len(rel) >= 3 and rel[2] == "verify") or (len(rel) >= 2 and rel[1] == "review")  # work/<작업명>/verify/, work/review/


def decide(data, root, state, approved, reason=REASON):
    tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    if tool in WRITE_TOOLS and isinstance(inp, dict) and any(inside(root, t, state) for t in write_targets(inp)):
        return f"{TAG} 승인 관문 기록(.git/{STATE_DIR})은 수정 도구로 바꿀 수 없습니다. 승인은 사용자 메시지로만 열립니다."
    if tool in WRITE_TOOLS and isinstance(inp, dict) and any(verify_record(root, t) for t in write_targets(inp)):
        return f"{TAG} 검증 기록(work/<작업명>/verify/)은 수정 도구로 바꿀 수 없습니다. 검증 실행기만 씁니다."
    if approved or tool in SHELL_TOOLS or tool in NOT_WRITE:
        return None
    if not isinstance(inp, dict):
        return reason
    if tool in WRITE_TOOLS:
        return None if all(inside(root, t, Path(root, ALLOWED_WRITE_DIR)) for t in write_targets(inp)) else reason
    if re.search(WRITE_NAME, tool, re.I):
        return reason
    return None  # 읽기·검색·하위 에이전트 등은 막지 않는다(하위 에이전트의 도구도 같은 훅을 지난다)


def changed_files(start, now):
    return sorted(p for p in set(start) | set(now) if start.get(p) != now.get(p))


def stop_message(changed, closed):
    shown = ", ".join(changed[:SHOWN_FILES]) + (f" 외 {len(changed) - SHOWN_FILES}개" if len(changed) > SHOWN_FILES else "")
    if closed:
        return (f"{TAG} 승인한 지도의 기준이 바뀌어 승인이 닫혔습니다({', '.join(closed)}). 이번 턴에 바뀐 제품 파일: {shown}. "
                "관문은 아무것도 되돌리지 않았습니다. 승인이 열려 있을 때 바꾼 것은 그대로 두고, 기준이 바뀐 뒤에 당신이 바꾼 것이 확실한 파일만 되돌리세요. "
                "무엇이 왜 바뀌었는지 사용자에게 보여 주고 다시 승인을 물으세요.")
    return (f"{TAG} 사용자 승인이 없는데 제품 파일이 바뀌었습니다: {shown}. "
            "관문은 아무것도 되돌리지 않았습니다. 이 가운데 이번 턴에 당신이 바꾼 것이 확실한 파일만 되돌리세요. "
            "사용자나 다른 작업이 바꿨을 수 있으면 되돌리지 말고(checkout·stash·reset 같은 일괄 되돌리기 금지) 사용자에게 알리세요. "
            "그다음 바꿀 내용을 보여 주고 승인을 물으세요.")


def read_json(path, default):
    try:
        v = json.loads(path.read_text())
    except FileNotFoundError:
        return default
    if not isinstance(v, type(default)):
        raise ValueError(f"관문 기록 형식이 다르다: {path.name}")
    return v


def touch(rec, turn_maps, now_maps, extra=()):
    """이 세션이 쓴 지도: 수정 도구 대상(extra)과, 이번 턴에 기준이 바뀌거나 생기거나 사라진 지도."""
    t = set(rec.get("touched", [])) | set(extra)
    if turn_maps is not None:
        t |= {m for m in set(turn_maps) | set(now_maps) if turn_maps.get(m) != now_maps.get(m)}
    rec["touched"] = sorted(t)


def bind(rec, root, now_maps):
    """승인 턴 끝에 승인 대상을 정한다. 승인 턴 안에서 지도를 쓰거나 고친 것은 승인 내용을 옮겨 적은 것으로 본다.
    대상 지도(승인 메시지가 가리킨 것·승인 전에 이 세션이 쓴 것·이번 턴에 쓴 것 가운데 `## 기준`이 있는 것)가 있으면 지도 승인으로
    그때의 기준에 묶고, 없으면 대화 승인이므로 닫는다."""
    cand = set(rec.get("targets", {})) | set(rec.get("wrote", []))  # 셸로 만든 지도·다른 세션의 지도는 묶지 않는다(구별할 수 없다)
    targets = {m: now_maps[m] for m in sorted(cand) if now_maps.get(m) and now_maps[m] != "unreadable"}
    rec.pop("binding", None)
    rec["touched"], rec["wrote"] = [], []
    if targets:
        rec.update(kind="map", targets=targets,
                   criteria={m: criteria_text(Path(root, m).read_text(encoding="utf-8", errors="replace")) for m in targets})
    else:
        rec.update(kind="conversation", targets={}, criteria={}, approved=False, closed_by="turn-end")


def settle(rec, now_maps):
    """승인 턴이 끝난 지도 승인의 유효성을 본다. 승인 밖 변화가 있으면 닫는다(사용자가 다시 승인할 때까지). 돌려줌: 닫힌 원인 지도 목록."""
    if not rec.get("approved") or rec.get("binding") or rec.get("kind") != "map":
        return []
    targets = rec.get("targets", {})
    removed = [m for m in targets if m not in now_maps]
    changed = [m for m in targets if m in now_maps and now_maps[m] != targets[m]]
    new = [m for m in rec.get("touched", []) if m not in targets and now_maps.get(m)]  # `## 기준`이 있는 새 지도만
    if changed or new:
        rec.update(approved=False, closed_by="criteria", closed_maps=sorted(changed + new))
        return rec["closed_maps"]
    if removed and len(removed) == len(targets):  # 승인한 지도를 모두 정리했다: 작업 완료로 닫는다
        rec.update(approved=False, closed_by="map-removed", closed_maps=sorted(removed))
    return []


def status_json(rec):
    """평가·사람이 보는 상태. waiting: 사용자 답이 필요한 상태(승인 전, 철회, 기준 변경으로 닫힘).
    대화 승인이 턴 끝에 닫힌 것과 작업을 마치며 지도를 정리한 것은 대기가 아니다. 관문 기록이 없으면 알 수 없으므로 대기로 세지 않는다."""
    approved = bool(rec.get("approved"))
    waiting = bool(rec.get("seen")) and not approved and rec.get("closed_by") not in ("turn-end", "map-removed")
    return {"approved": approved, "kind": rec.get("kind"), "targets": sorted(rec.get("targets", {})), "closed_by": rec.get("closed_by"),
            "waiting": waiting, "recorded": bool(rec.get("seen"))}


def approved_record(root, state, map_path):
    """검증기가 쓴다(읽기만): 이 지도를 승인 대상으로 가진 세션 기록 중 가장 최근 승인. 승인 턴이 아직 끝나지 않았으면(그 턴 안에서
    지도를 쓰고 바로 검증) 이 세션이 쓴 지도도 대상으로 보고 지금의 기준 글을 승인 기준으로 쓴다. 없으면 None."""
    best = None
    for f in state.glob("*.approval") if state.is_dir() else []:
        try:
            rec = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("binding") and rec.get("approved"):
            now_maps = maps(root)
            if map_path in set(rec.get("targets", {})) | set(rec.get("wrote", [])) and now_maps.get(map_path):
                rec = {**rec, "targets": {**rec.get("targets", {}), map_path: now_maps[map_path]},
                       "criteria": {**rec.get("criteria", {}), map_path: criteria_text(Path(root, map_path).read_text(encoding="utf-8", errors="replace"))}}
        if map_path in rec.get("targets", {}) and (best is None or rec.get("approved_at", 0) > best.get("approved_at", 0)):
            best = rec
    return best


def advance(rec, event, root, now_maps, turn_maps=None, prompt="", extra=(), runner=False, snapshot=None, plan=None, event_key=None):
    """승인 상태가 바뀌는 유일한 곳. 사건(prompt·pre·stop) 하나와 지금 관찰(지도 지문)을 받아 다음 기록을 낸다.
    파일 읽기·쓰기와 도구 거절은 main 이 맡는다. 돌려줌: (새 기록, {decision, closed(닫힌 원인 지도), reset_start(턴 끝 감지 시작점을 지금으로)})."""
    was_open = bool(rec.get("approved"))
    info = {"decision": None, "closed": [], "reset_start": False}
    if event == "prompt":
        last = rec.get("last_prompt") or {}
        # 같은 사건의 두 번째 훅 호출(전역·프로젝트 훅 병용): 메시지와 대화 기록 상태가 모두 같으면 기록을 바꾸지 않는다.
        # 대화 기록 경로가 없으면 가릴 수 없으므로 거르지 않는다(사용자가 같은 말을 다시 보낸 것과 구별할 수 없다).
        if event_key and last.get("key") == event_key and time.time() - last.get("t", 0) < 30:
            info["decision"] = "duplicate"
            return rec, info
        if rec.get("binding"):  # 앞 턴이 Stop 없이 끝났으면 지금 묶는다
            bind(rec, root, now_maps)
        settle(rec, now_maps)  # 턴 사이에 승인한 지도의 기준이 바뀌었으면 닫힘으로 남긴다
        if runner:
            info["decision"] = "runner"  # 평가 실행기가 보낸 사용자 아닌 입력(검증 반환 등): 승인을 바꾸지 않는다
        elif is_approval(prompt):
            # 후보: 승인 메시지가 가리킨 지도, 승인 전에 이 세션이 수정 도구로 쓴 지도, 둘 다 없으면 지난 승인의 지도. 턴 끝(bind)에 확정한다.
            targets = {m: now_maps[m] for m in named_maps(root, prompt) if now_maps.get(m)}
            for m in rec.get("wrote", []):
                if now_maps.get(m):
                    targets.setdefault(m, now_maps[m])
            if not targets:
                targets = {m: now_maps[m] for m in rec.get("targets", {}) if now_maps.get(m)}
            # 검토 입력 고정: 승인 전 사용자 메시지(요청 원문)와 승인 직전 에이전트가 보여 준 계획을 그대로 남긴다(에이전트가 나중에 요약한 글로 대신하지 않는다)
            # 철회·기준 변경으로 닫힌 같은 작업을 다시 승인하면 앞선 원문·추가 요구를 이어 간다(작업을 마치고 닫힌 경우는 새 작업으로 본다)
            carried = (rec.get("requests", []) + rec.get("after", [])) if rec.get("closed_by") in ("revoke", "criteria") else []
            rec = {"approved": True, "binding": True, "kind": "map" if targets else "conversation", "targets": targets, "criteria": {},
                   "prompt": prompt, "requests": carried + rec.get("pending", []) + [prompt], "plan": plan() if plan else None,
                   "after": [], "touched": [], "wrote": [], "approved_at": time.time(), "base": snapshot() if snapshot else None, "pending": []}
            info["decision"] = "open"
        elif is_revoke(prompt) or mentions_approval(prompt):
            rec.update(approved=False, closed_by="revoke")
            info["decision"] = "close"
        else:
            if rec.get("approved"):
                rec.setdefault("after", []).append(prompt)  # 승인 뒤 사용자 메시지(검증자가 범위 변경을 대조한다)
            else:
                pend = rec.get("pending", []) + [prompt]  # 다음 승인의 요청 원문(승인 전 사용자 메시지). 길어지면 첫 원문은 남기고 가운데를 줄인다
                rec["pending"] = pend if len(pend) <= 40 else [pend[0], f"(가운데 사용자 메시지 {len(pend) - 39}개 생략)"] + pend[-38:]
            info["decision"] = "keep"
        rec["seen"] = True
        rec["last_prompt"] = {"key": event_key, "t": time.time()}
        return rec, info
    touch(rec, turn_maps, now_maps, extra)
    if event == "pre":
        rec["wrote"] = sorted(set(rec.get("wrote", [])) | set(extra))
    info["closed"] = settle(rec, now_maps)
    if event == "stop" and rec.get("binding"):
        bind(rec, root, now_maps)
    # 승인 중에 작업이 끝나면(대화 승인의 턴 끝, 지도 정리) 승인 중 변경은 알리지 않고 지금부터 본다. 기준 변경으로 닫힌 것은 그대로 둔다.
    done = ("turn-end", "map-removed") if event == "stop" else ("map-removed",)
    info["reset_start"] = was_open and rec.get("closed_by") in done
    return rec, info


def prompt_event_key(data):
    """같은 사용자 메시지 사건을 가리는 열쇠: 메시지 + 대화 기록 파일의 크기·수정 시각. 대화 기록이 없으면 None."""
    tp = data.get("transcript_path")
    try:
        st = os.stat(tp) if tp else None
    except OSError:
        st = None
    return hashlib.sha256(f"{data.get('prompt')}\0{tp}\0{st.st_size}\0{st.st_mtime_ns}".encode()).hexdigest() if st else None


def latest_approval(state, sid=None):
    """검토기가 쓴다(읽기만): 지도 없이 승인한 일의 승인 기록. 세션 id 가 있으면 그 세션의 것, 없으면 가장 최근 승인. 없으면 None."""
    files = [state / f"{hashlib.sha256(str(sid).encode()).hexdigest()[:24]}.approval"] if sid else (sorted(state.glob("*.approval")) if state.is_dir() else [])
    recs = []
    for f in files:
        try:
            r = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and r.get("approved_at"):
            recs.append(r)
    return max(recs, key=lambda r: r["approved_at"]) if recs else None


def main(mode, data):
    try:
        root, state = locate(data.get("cwd"))
    except RuntimeError:
        return 0  # git 저장소가 아니면 키트 설치 프로젝트도 아니다
    if not (root / ".agents" / "agent-workflow-kit.version").is_file():
        return 0  # 키트가 설치된 프로젝트에서만 동작한다(키트 원본 저장소는 그대로 둔다)
    sid = data.get("session_id")
    key = hashlib.sha256(str(sid).encode()).hexdigest()[:24] if sid else None
    if mode == "status":
        rec = read_json(state / f"{key}.approval", {}) if key else {}
        print(json.dumps(status_json(rec), ensure_ascii=False))
        return 0
    if not key:
        if mode == "pre":
            reason = decide(data, root, state, False)
            if reason:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                         "permissionDecisionReason": reason}}, ensure_ascii=False))
        return 0
    approval, start, blocks, turnmaps = (state / f"{key}.{n}" for n in ("approval", "start", "blocks", "maps"))
    rec = read_json(approval, {})
    now_maps = maps(root)
    turn_maps = read_json(turnmaps, {}) if turnmaps.is_file() else None
    if mode == "prompt":
        state.mkdir(exist_ok=True)
        rec, info = advance(rec, "prompt", root, now_maps, prompt=str(data.get("prompt") or ""),
                            runner=os.environ.get("AWK_GATE_PROMPT_FROM") == "runner", snapshot=lambda: snapshot_files(root, state),
                            plan=lambda: last_answer(data.get("transcript_path")), event_key=prompt_event_key(data))
        decision = info["decision"]
        approval.write_text(json.dumps(rec, ensure_ascii=False))
        turnmaps.write_text(json.dumps(now_maps, ensure_ascii=False))
        start.write_text(json.dumps(product_files(root), ensure_ascii=False))
        blocks.write_text("0")
        (state / f"{key}.laststop").unlink(missing_ok=True)
        log({"event": "prompt", "decision": decision, **status_json(rec)})
        return 0
    if mode == "pre":
        tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        extra = [m for m in (rel_map(root, t) for t in write_targets(inp)) if m] if tool in WRITE_TOOLS else []
        rec, info = advance(rec, "pre", root, now_maps, turn_maps, extra=extra)
        closed = info["closed"]
        if state.is_dir():
            if info["reset_start"]:
                start.write_text(json.dumps(product_files(root), ensure_ascii=False))
            approval.write_text(json.dumps(rec, ensure_ascii=False))
        reason = decide(data, root, state, bool(rec.get("approved")), CLOSED_REASON.format(maps=", ".join(closed)) if closed else REASON)
        log({"event": "pre", "tool": tool, "approved": bool(rec.get("approved")), "denied": bool(reason), "closed_maps": closed,
             "input": str(inp.get("command") or inp.get("cmd") or inp.get("file_path") or "")[:200]})
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}, ensure_ascii=False))
        return 0
    # stop
    rec, info = advance(rec, "stop", root, now_maps, turn_maps)
    closed = info["closed"]
    if not state.is_dir():
        return 0
    now = product_files(root)
    if info["reset_start"]:
        start.write_text(json.dumps(now, ensure_ascii=False))
    if rec:
        approval.write_text(json.dumps(rec, ensure_ascii=False))
    if rec.get("approved") or not start.is_file():
        return 0
    begin = read_json(start, {})
    changed = changed_files(begin, now)
    digest = hashlib.sha256(json.dumps(now, sort_keys=True).encode()).hexdigest()
    begin_digest = hashlib.sha256(json.dumps(begin, sort_keys=True).encode()).hexdigest()
    # 같은 턴 끝에 관문이 두 번 불리면(전역 훅과 프로젝트 훅을 둘 다 등록한 경우) 앞의 판단을 그대로 낸다.
    last = state / f"{key}.laststop"
    if last.is_file():
        prev = json.loads(last.read_text() or "{}")
        if time.time() - prev.get("t", 0) < 5 and prev.get("now") == digest and prev.get("start") == begin_digest:
            if prev.get("out"):
                print(prev["out"])
            return 0
    n = int(blocks.read_text() or 0) if blocks.is_file() else 0
    shown_closed = closed or (rec.get("closed_maps", []) if rec.get("closed_by") == "criteria" else [])
    log({"event": "stop", "changed": bool(changed), "files": changed[:SHOWN_FILES], "blocks": n, "closed_maps": shown_closed})
    out = ""
    if changed and n < MAX_STOP_BLOCKS:
        blocks.write_text(str(n + 1))
        out = json.dumps({"decision": "block", "reason": stop_message(changed, shown_closed)}, ensure_ascii=False)
        print(out)
    elif changed:
        print(f"{TAG} 승인 없는 제품 파일 변경이 남은 채 끝났다(알림 {n}회): {', '.join(changed[:SHOWN_FILES])}", file=sys.stderr)
    last.write_text(json.dumps({"t": time.time(), "start": begin_digest, "now": digest, "out": out}, ensure_ascii=False))
    return 0


USAGE = "사용: approval-gate.py status [--session <id>]   (prompt·pre·stop 은 하네스 훅이 표준 입력 JSON 과 함께 부른다)"

if __name__ == "__main__":
    mode, data = (sys.argv[1] if len(sys.argv) > 1 else "pre"), {}
    if mode in ("-h", "--help", "help"):
        print(USAGE)
        sys.exit(0)
    if mode not in ("prompt", "pre", "stop", "status"):
        print(f"{TAG} 오류: 알 수 없는 명령 {mode!r}\n{USAGE}", file=sys.stderr)
        sys.exit(2)
    if mode == "status":
        args = sys.argv[2:]
        sid = args[args.index("--session") + 1] if "--session" in args[:-1] else next(
            (os.environ[k] for k in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID") if os.environ.get(k)), None)
        try:
            sys.exit(main("status", {"cwd": os.getcwd(), "session_id": sid}))
        except Exception as e:
            print(f"{TAG} 오류: status 실패: {e!r}", file=sys.stderr)
            sys.exit(1)
    try:
        data = json.load(sys.stdin)
        main(mode, data)
    except Exception as e:  # 훅 자체 오류: 수정 도구만 막고 읽기·셸은 그대로 둔다. 턴 끝 검사는 알린다.
        log({"error": repr(e), "mode": mode})
        tool = str(data.get("tool_name") or "") if isinstance(data, dict) else ""
        if mode == "stop":
            print(json.dumps({"decision": "block", "reason": f"{TAG} 승인 관문이 제품 파일 상태를 확인하지 못했습니다({e!r}). "
                              "이번 턴에 당신이 바꾼 것이 확실한 제품 파일만 되돌리고, 상태를 사용자에게 알리세요."}, ensure_ascii=False))
        if mode == "pre" and (not data or tool in WRITE_TOOLS or (tool not in SHELL_TOOLS | NOT_WRITE and re.search(WRITE_NAME, tool, re.I))):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": f"{TAG} 승인 관문 오류로 쓰기를 막았습니다: {e!r}"}}, ensure_ascii=False))
        print(f"{TAG} 훅 오류: {e!r}", file=sys.stderr)
