"""승인 관문: 사용자가 승인하기 전에는 에이전트가 수정 도구로 제품 파일을 쓰지 못하게 막고, 지금 작업의 승인 상태를 관리한다.

하네스(Codex·Claude Code) 훅으로 세 번 불린다.
- `approval-gate.py prompt` (UserPromptSubmit): 사용자 메시지가 들어올 때 지금 작업의 승인 상태를 정하고, 제품 파일별 지문을 기록한다.
  - 승인 메시지("승인합니다"·"진행해 주세요" 같은 고정 규칙)면 승인을 연다. 승인은 이 훅에만 들어오는 사용자 메시지로만 열린다.
  - 철회("취소합니다")나, 승인 말이 들어 있지만 승인이 아닌 메시지("승인하지 않습니다"·"진행해도 될까요?")면 닫는다.
  - 그 밖의 메시지(상태 질문 "어디까지 됐어요?", 새 요청 등)는 승인 상태를 그대로 둔다. 메시지의 뜻을 더 분류하지 않는다.
- `approval-gate.py pre` (PreToolUse): 승인 상태가 아니면 수정 도구(Edit·Write·apply_patch 등)로 `work/` 밖을 바꾸거나,
  이름으로 쓰기임이 드러나는 도구(MCP 파일 쓰기 등)를 쓰려 하면 거절한다. 셸 명령은 내용을 해석하지 않고 거절하지 않는다.
  관문 기록(`.git/awk-gate/`)을 수정 도구로 바꾸는 것은 승인과 관계없이 거절한다.
- `approval-gate.py stop` (Stop): 승인 상태가 아닌 턴에 제품 파일이 턴 시작 때와 달라졌으면 바뀐 파일 이름을 알리고 한 번 더 답하게 한다.
  관문은 아무 파일도 되돌리지 않는다. 에이전트가 자기가 바꾼 것이 확실한 파일만 되돌리고, 섞였으면 사용자에게 알린다.
  끝없는 반복을 막으려고 한 턴에 MAX_STOP_BLOCKS 번까지만 그렇게 하고, 그 뒤에도 남으면 턴을 끝내되 표준 오류에 남긴다.
- `approval-gate.py status`·`task begin <작업명>`·`task done` (셸에서 직접 실행): 지금 작업의 상태를 보여 주거나, 에이전트가
  새 작업 시작·작업 완료를 선언한다. 선언은 승인을 닫고 새 작업을 시작할 뿐 승인을 열지 못한다. 작업은 하네스가 셸에 넘기는
  세션 id(CLAUDE_CODE_SESSION_ID·CODEX_THREAD_ID) 나 --session 으로 고르고, 없으면 기록이 하나일 때만 고른다.

작업 기록과 기준 지문:
- 작업 기록은 작업 지도 파일(work/<작업명>/work.md)이든, 승인을 물은 에이전트 답(하네스가 넘기는 대화 기록의 마지막 답)이든
  같은 양식의 `## 기준` 절이다. 관문은 그 절의 지문(빈 줄·줄 끝 공백을 뺀 내용의 해시)으로 "같은 기준인가"만 본다.
  그래서 대화에서 보여 준 기준을 승인 뒤 지도 파일로 그대로 옮기거나 지도를 다른 경로로 옮겨도 승인이 유지된다.
- 승인 때 묶는 것: 승인 메시지가 경로로 가리킨 지도, 지난 승인 뒤 이 세션이 쓰며 기준이 바뀐 지도, 이 작업에서 에이전트가
  답으로 보여 준 마지막 기준. 셋 다 없으면 지난 승인의 대상을 그대로 다시 묶는다(철회 뒤 같은 계획을 다시 승인한 경우).
- 승인이 닫히는 경우(닫힘은 사용자가 다시 승인할 때까지 유지된다. 에이전트가 기록을 되돌려도 다시 열리지 않는다):
  사용자 철회, 승인 대상 지도의 기준이 승인 밖 기준으로 바뀌거나 사라짐, 승인 때 없던 기준(이 세션이 쓴 새 지도나 답에 보여 준
  새 `## 기준`)이 나타남. 마지막 경우는 에이전트가 새 작업이나 새 기준을 내놓았다는 뜻이므로, 다음 승인은 그 새 기록만 묶고
  이전 작업의 지도·사용자 원문을 새 작업으로 넘기지 않는다. 승인 때 이미 있던 다른 작업의 지도가 바뀌는 것은 상관하지 않는다.
- 작업 시작 상태: 관문은 매 사용자 턴 시작에 제품 파일 내용을 git 객체로 남기고, 작업이 시작된 턴(세션의 첫 요청, `task begin`,
  승인 밖 새 기준이 처음 나타난 턴)의 것을 그 작업의 시작 상태로 묶는다. 승인 때 덮지 않는다. 검증기는 이 상태부터의 변경을 본다.
- 에이전트가 파일에 "approved: true" 를 쓰거나 답에 "승인합니다" 를 써도 승인이 되지 않는다(사용자 메시지만 연다).

예: 사용자가 "회원 탈퇴 기능을 만들어 주세요" 라고만 보내면 에이전트는 코드를 읽고 검사를 돌릴 수는 있지만 accounts.py 를 Edit 로
고치려는 순간 거절 사유가 돌아온다. "승인합니다" 뒤 "어디까지 됐어요?" 라고 물어도 계속 쓸 수 있다. 사용자가 이어서
"이제 비밀번호 변경도 만들어 주세요" 라고 하면, 에이전트가 그 새 작업의 기준을 지도나 답으로 내놓는 순간 탈퇴 작업의 승인은
닫히고 비밀번호 변경 계획에 대한 승인을 다시 묻게 된다.

보장 범위(설치·문서에 그대로 밝힌다):
- 작업이 바뀌었는지는 에이전트가 판단한다. 관문은 에이전트가 내놓은 기준이 승인한 기준과 같은지만 본다. 에이전트가 새 요청을
  기존 작업으로 잘못 보고 새 기준 없이 바로 쓰면 관문은 막지 못한다(독립 검증자가 사용자 원문과 대조해 잡아야 한다).
- 사전 차단은 수정 도구뿐이다. 셸 쓰기는 미리 막지 않고 턴 끝에 사후 감지한다. 감지 시점에는 이미 쓰기가 일어났다.
- 사후 감지 범위는 git 이 아는 파일과 무시되지 않은 새 파일(키트·하네스 설정·work/ 제외)이다. 무시된 파일·저장소 밖·외부 효과
  (배포·네트워크·데이터베이스)는 보지 않는다. 셸을 막지 않는다는 것은 외부 효과를 허락한다는 뜻이 아니다(AGENTS.md 실행 경계).
- 턴 시작 전부터 있던 사용자의 미커밋 변경은 시작 지문에 들어가므로 알림 대상이 아니다. 턴 도중 사용자·다른 작업이 바꾼 파일은
  에이전트 변경과 구별하지 못하므로 알림에 섞일 수 있다. 그래서 관문은 되돌리지 않고, 일괄 되돌리기도 시키지 않는다.
  같은 이유로 이 세션의 턴 도중 다른 작업이 새 지도를 쓰면 이 세션이 쓴 것으로 보고 닫는다(다시 묻는 쪽으로 틀린다).
- 승인 뒤 사용자가 기준에 올리지 않은 범위 변경을 말로만 하면("그런데 재가입은 막아 주세요") 관문은 닫지 않는다. 메시지 뜻을
  분류하지 않기 때문이다. 에이전트가 기준을 고쳐 내놓으면 닫히고, 고치지 않은 채 구현하면 독립 검증자가 원문과 대조해 잡아야 한다.
- 대화의 기준은 하네스가 훅에 대화 기록 경로(transcript_path)를 넘기고 답에 `## 기준` 절이 있을 때만 읽힌다. 읽지 못하면 그 기준은
  없는 것으로 보고, 승인 뒤 처음 쓴 지도는 새 기준으로 닫힌다(다시 묻는 쪽으로 틀린다). 대화 기록은 이 판단에만 쓰고 뜻을 해석하지 않는다.
- 생성물(빌드 산출물·캐시)은 프로젝트의 .gitignore 가 정한다. 관문에 언어·도구별 예외는 없다.
- 실수 방지 장치다. 승인 기록(`.git/awk-gate/`)을 셸로 고치거나 이 파일을 일부러 고치는 것까지 막지는 않는다.
승인이 허용하는 범위(어느 파일·어떤 동작)는 기계로 보지 않는다. 결과가 승인한 내용과 맞는지는 검증자가 본다.
환경 변수: AWK_GATE_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
  AWK_GATE_PROMPT_FROM=runner(평가 실행기가 하네스를 띄울 때만 준다): 그 턴의 입력은 사용자 메시지가 아니므로 승인 상태를 바꾸지 않는다.
  사용자가 직접 쓰는 세션에서는 주지 않는다.
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


CHANGED_REASON = (f"{TAG} 승인 뒤 승인 밖의 기준이 나타나 이 작업의 승인이 닫혔습니다: {{maps}}. "
                  "승인한 기준이 바뀌었거나(조건 추가·삭제·수정, 기준 절·지도 삭제), 새 작업이나 새 기준을 지도·답으로 내놓은 경우입니다. "
                  "바뀐 기준은 사용자가 승인한 것이 아닙니다. 무엇이 왜 바뀌었는지(새 작업이면 그 계획을) 보여 주고 다시 승인을 물으세요. "
                  "실행 결과·내부 설계는 `## 기준` 밖(`## 증거` 등)에 적으면 승인이 유지되고, 승인한 기준을 그대로 다른 지도로 옮겨도 유지됩니다.")
STATE_DIR = "awk-gate"  # 관문 기록 폴더(.git/awk-gate). 수정 도구로는 바꿀 수 없다.
# 하네스가 셸 명령에 넘기는 세션 id(관문 훅의 session_id 와 같은 값). 에이전트·검증기가 자기 작업을 고를 때 쓴다.
SESSION_ENV = ("AWK_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")


def log(what):
    if os.environ.get("AWK_GATE_LOG"):
        try:
            with open(os.environ["AWK_GATE_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args, ok=(0,), input=None):
    # 저장소 설정의 외부 프로그램(fsmonitor·외부 diff·textconv)이 관문의 상태 수집 중에 실행되지 않게 끈다.
    r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "diff.external=", *args], capture_output=True, input=input)
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패")
    return r.stdout


def locate(cwd):
    out = git(cwd or ".", "rev-parse", "--show-toplevel", "--absolute-git-dir").decode().split("\n")
    return Path(out[0]), Path(out[1], STATE_DIR)


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


def criteria_text(text):
    """작업 기록(지도 파일이나 에이전트 답)에서 승인 대상인 `## 기준` 절 본문. 다음 `#`·`##` 제목 전까지이고, 빈 줄·줄 끝 공백·
    닫는 코드 울타리는 뺀다(같은 기준을 대화에서 파일로 옮겨도 같은 값이 되게). 기준 절이 없으면 None.
    결과·범위·완료 기준만 승인 대상이다. 담당자·설계(내부 함수 이름 등)·`## 증거` 를 고쳐도 값은 그대로다."""
    m = re.search(r"^## 기준[^\n]*\n(.*?)(?=^#{1,2} |\Z)", text or "", re.M | re.S)
    if not m:
        return None
    lines = [l.rstrip() for l in m.group(1).splitlines() if l.strip()]
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()
    return "\n".join(lines)


def criteria(text):
    """기준 절의 지문(해시). 기준 절이 없으면 None."""
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


def inside_state(root, path):
    """경로가 관문 기록 폴더(.git/awk-gate) 안인가. worktree 의 .git 파일도 실제 git 폴더로 풀어 본다."""
    if not path:
        return False
    p = os.path.realpath(Path(path) if Path(path).is_absolute() else root / path)
    try:
        state = os.path.realpath(locate(root)[1])
    except RuntimeError:
        return False
    return p == state or p.startswith(state + os.sep)


def decide(data, root, approved, reason=REASON):
    tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    if tool in WRITE_TOOLS and isinstance(inp, dict) and any(inside_state(root, t) for t in write_targets(inp)):
        return f"{TAG} 승인 관문 기록(.git/{STATE_DIR})은 수정 도구로 바꿀 수 없습니다. 승인은 사용자 메시지로만 열립니다."
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


def new_task(state, now_maps, messages=(), name=None, base=None):
    """세션 안의 작업 하나(현재 작업). 작업 id·승인 근거(사용자 메시지)·승인 기준·검증 결과를 이 기록이, 이 작업의 사용자 원문은
    task-<id>.messages.jsonl 이 자르지 않고 갖는다. 전이: waiting(승인 전) → approved(사용자 승인) → closed(사용자 철회 user,
    승인 대상 기준 변경 criteria, 승인 밖 새 기준 new-criteria, 에이전트의 새 작업 선언 new-task, 에이전트의 완료 선언 done).
    approved 는 prompt 훅이 사용자 승인 메시지를 받았을 때만 True 가 된다. 다른 경로(pre·stop·task 명령·검증기)는 닫거나 기록만 한다."""
    rec = {"id": os.urandom(6).hex(), "name": name, "approved": False, "state": "waiting", "prompt": None, "targets": {}, "hashes": [],
           "criteria": {}, "snapshot": {}, "conversation_only": False, "touched": [], "boundary": now_maps, "proposal": None,
           "pending_since": None, "pending_base": None, "message_count": 0, "verify": {}, "started_at": time.time(),
           "base_files": base}  # base_files: 작업 시작 때 제품 파일 상태(검증기 diff 의 기준). 승인 때 덮지 않는다.
    for m in messages:
        add_message(state, rec, m)
    return rec


def messages_file(state, rec):
    return state / f"task-{rec['id']}.messages.jsonl"


def read_messages(state, rec):
    """이 작업의 사용자 원문 전부(자르지 않는다). 기록 수가 맞지 않으면 None(검증기가 미확인으로 다룬다)."""
    f = messages_file(state, rec)
    try:
        msgs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        msgs = []
    return msgs if len(msgs) == rec.get("message_count", 0) else None


def add_message(state, rec, prompt):
    state.mkdir(exist_ok=True)
    with messages_file(state, rec).open("a", encoding="utf-8") as f:
        f.write(json.dumps(prompt, ensure_ascii=False) + "\n")
    rec["message_count"] = rec.get("message_count", 0) + 1


def current_index(rec):
    """지금 턴의 사용자 원문 위치(새 작업이 시작되면 그 원문부터 새 작업의 원문이 된다)."""
    return max(rec.get("message_count", 0) - 1, 0)


def rotate(state, rec, now_maps, start, name=None, base=None):
    """새 작업을 시작한다. 앞 작업의 지도·검증 결과를 넘기지 않고, 사용자 원문은 start 번째부터만 가져간다.
    새 작업의 시작 상태는 그 작업의 첫 턴이 시작될 때의 제품 파일 상태다(그 턴에 승인 없이 바뀐 것은 diff 에 보인다)."""
    msgs = (read_messages(state, rec) or [])[start:] if start is not None else []
    return new_task(state, now_maps, msgs, name, base or rec.get("pending_base") or rec.get("turn_base"))


def mark_pending(rec, index, base):
    """승인 밖 새 기준(새 작업일 수 있다)이 처음 나타난 턴을 기억한다: 그 턴의 사용자 원문 위치와 턴 시작 때 제품 파일 상태."""
    if rec.get("pending_since") is None:
        rec["pending_since"], rec["pending_base"] = index, base


def touch(rec, turn_maps, now_maps, extra=()):
    """이 세션이 지난 승인 뒤 쓴 지도 목록을 늘린다: 수정 도구 대상(extra)과, 이번 턴 동안 기준이 바뀐 지도(턴 시작 기록이 있을 때만).
    승인 전에 새 기준이 처음 나타난 턴을 기억해 둔다(새 작업이면 그 턴의 사용자 원문부터 새 작업의 원문이 된다)."""
    t = set(rec.get("touched", [])) | set(extra)
    if turn_maps is not None:
        t |= {m for m in set(turn_maps) | set(now_maps) if turn_maps.get(m) != now_maps.get(m)}
    rec["touched"] = sorted(t)
    boundary = rec.get("boundary", {})
    if any(now_maps.get(m) is not None and now_maps.get(m) != boundary.get(m) for m in t):
        mark_pending(rec, current_index(rec), rec.get("turn_base"))


def status(rec, now_maps):
    """(승인 상태, 승인 밖 기준이 나타난 기록 목록). 승인이 열려 있어도 다음이면 닫힌 것이다.
    - 승인 대상 지도의 기준이 승인한 지문 밖으로 바뀜(사라졌는데 같은 기준이 다른 지도에 없으면 삭제로 본다. 있으면 옮긴 것이다).
    - 승인 때 기준이 없던 지도(새 지도 포함)에 이 세션이 승인 밖 기준을 씀(새 작업이나 새 기준을 내놓음).
    승인 때 이미 다른 기준이 있던 지도(다른 작업의 기록)의 변화는 보지 않는다.
    지문이 같다는 것은 정규화한 글이 같다는 뜻일 뿐이다. 뜻이 같은지(다르게 쓴 같은 계획)는 보지 않는다."""
    if not rec.get("approved"):
        return False, rec.get("closed_maps", [])
    allowed = set(rec.get("hashes", []))
    snap, targets, touched = rec.get("snapshot", {}), rec.get("targets", {}), set(rec.get("touched", []))
    bad = []
    for m in sorted(set(snap) | set(now_maps)):
        old, new = snap.get(m), now_maps.get(m)
        if old == new or (new is not None and new in allowed):
            continue
        if m in targets:
            if new is None and any(v in allowed for v in now_maps.values() if v):
                continue  # 같은 기준이 다른 지도에 있다: 기록을 옮긴 것
            bad.append(m)
        elif old is None and new is not None and m in touched:
            bad.append(m)
    return not bad, bad


def close(rec, kind, why, closed_maps=()):
    """승인을 닫는다. 닫힘은 사용자가 다시 승인할 때까지 유지된다(기록을 되돌려도 열리지 않는다)."""
    rec.update(approved=False, state="closed", closed_kind=kind, closed_by=why, closed_maps=sorted(closed_maps), closed_at=time.time())


def settle(rec, now_maps):
    """승인 밖 기준이 나타났으면 닫고, 지금 승인 상태를 돌려준다."""
    ok, bad = status(rec, now_maps)
    if rec.get("approved") and not ok:
        mark_pending(rec, current_index(rec), rec.get("turn_base"))
        close(rec, "criteria" if any(m in rec.get("targets", {}) for m in bad) else "new-criteria", "승인 밖 기준", bad)
    return bool(rec.get("approved"))


def see_answer(rec, answer):
    """에이전트의 마지막 답에 `## 기준` 절이 있으면 이 작업의 대화 기록으로 기억한다. 승인 중인데 승인 밖 기준이면 닫는다."""
    body = criteria_text(answer) if answer else None
    if body is None:
        return
    h = hashlib.sha256(body.encode()).hexdigest()
    if rec.get("approved") and h in rec.get("hashes", []):
        return  # 승인한 기준을 다시 보여 준 것
    mark_pending(rec, current_index(rec), rec.get("turn_base"))  # 그 답이 답한 사용자 메시지와 그 턴의 시작 상태부터
    rec["proposal"] = {"hash": h, "text": body}
    if rec.get("approved"):
        close(rec, "new-criteria", "답에 보여 준 승인 밖 기준", ["대화의 답"])


def snapshot_files(root, state):
    """지금 제품 파일 내용을 git 객체로 보존하고(clean filter 를 쓰지 않는 --no-filters) 그 목록 파일 이름을 돌려준다.
    관문은 매 사용자 턴 시작에 이것을 남기고, 작업이 시작된 턴의 것을 그 작업의 시작 상태로 묶는다. 검증기는 시작 상태와 비교해
    이번 작업의 변경만 본다: 작업 전부터 있던 사용자 미커밋 변경은 시작 상태에 들어가고, 요청 뒤 승인 전에 바뀐 것은 diff 에 보인다.
    무시된 파일은 넣지 않고, 하위 저장소·읽을 수 없는 파일은 내용을 보존하지 못했다고 적는다(검증기는 미확인으로 다룬다)."""
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


def open_approval(rec, root, state, prompt, now_maps, answer):
    """사용자 승인 메시지로 승인을 연다(관문에서 승인이 열리는 유일한 자리). 이 작업의 승인 기준을 정하고, 앞 작업과 대상이
    겹치지 않는 새 기준이면 새 작업으로 넘긴다(앞 작업의 지도·사용자 원문·검증 결과를 가져가지 않는다)."""
    prev_targets, prev_hashes, prev_criteria = rec.get("targets", {}), set(rec.get("hashes", [])), rec.get("criteria", {})
    targets = {m: "승인 메시지가 경로로 가리킴" for m in named_maps(root, prompt)}
    boundary = rec.get("boundary", {})
    for m in rec.get("touched", []):
        if now_maps.get(m) is not None and now_maps.get(m) != boundary.get(m):
            targets.setdefault(m, "지난 승인 뒤 이 세션이 쓴 지도")
    prop = rec.get("proposal")
    criteria_texts, hashes = {}, set()
    if prop:
        hashes.add(prop["hash"]); criteria_texts["대화(승인을 물은 답)"] = prop["text"]
    fresh = bool(targets) or bool(prop and prop["hash"] not in prev_hashes)
    if not fresh and rec.get("closed_kind") not in ("new-task", "done"):
        # 새 기록이 없다: 철회 뒤 같은 계획을 다시 승인한 것으로 보고 지난 승인 대상을 다시 묶는다
        targets.update({m: why for m, why in prev_targets.items() if now_maps.get(m) is not None})
        for k, text in prev_criteria.items():
            if k.startswith("대화") and text is not None:
                hashes.add(hashlib.sha256(text.encode()).hexdigest()); criteria_texts[k] = text
    for m in targets:
        if now_maps.get(m) and now_maps[m] != "unreadable":
            hashes.add(now_maps[m])
            criteria_texts[m] = criteria_text(Path(root, m).read_text(encoding="utf-8", errors="replace"))
    if rec.get("approved_at") and fresh and not (set(targets) & set(prev_targets)) and not (hashes & prev_hashes):
        start = rec.get("pending_since")
        rec = rotate(state, rec, now_maps, start if start is not None else current_index(rec), rec.get("name"))
    # 작업 시작 상태는 작업을 만들 때 정했다. 승인 때 덮지 않는다(요청 뒤 승인 전에 바뀐 파일이 diff 에서 사라지지 않게).
    rec.update(approved=True, state="approved", prompt=prompt, approved_at=time.time(), targets=targets,
               hashes=sorted(hashes), criteria=criteria_texts, snapshot=now_maps, boundary=now_maps, touched=[], proposal=None,
               pending_since=None, pending_base=None, conversation_only=not targets, closed_kind=None, closed_by=None, closed_maps=[], verify={},
               plan=answer)  # plan: 승인을 물은 답 전체(대화 기록을 읽지 못했으면 None)
    return rec


def session_arg(args):
    """--session 인자, 없으면 하네스가 셸에 넘긴 세션 id."""
    if "--session" in args and args.index("--session") + 1 < len(args):
        return args[args.index("--session") + 1]
    return next((os.environ[v] for v in SESSION_ENV if os.environ.get(v)), None)


def pick(state, args):
    """(작업 기록 파일, 사유). 세션 id 로 고른다. 세션 id 가 없으면 기록이 하나뿐일 때만 그것을 쓰고, 여럿이면 추측하지 않는다."""
    sid = session_arg(args)
    if sid:
        f = state / f"{hashlib.sha256(str(sid).encode()).hexdigest()[:24]}.approval"
        return (f, "") if f.is_file() else (None, "이 세션의 작업 기록이 없다(관문 훅이 돌지 않았거나 다른 저장소)")
    files = sorted(state.glob("*.approval")) if state.is_dir() else []
    if len(files) == 1:
        return files[0], ""
    return None, (f"작업 후보가 {len(files)}개라 고르지 않았다: --session <세션 id> 로 지정한다" if files else "작업 기록이 없다")


def waiting(rec, ok=None):
    """사용자 답 대기 여부. 일반 검증기와 평가 실행기가 같은 규칙으로 완료를 분류한다."""
    ok = bool(rec.get("approved")) if ok is None else ok
    return not ok and rec.get("closed_kind") != "done"


def task_status(root, state, rec):
    """사람·검증기에게 보여 줄 작업 상태. approval: open(승인 중) / closed(승인 뒤 닫힘) / waiting(아직 승인 없음).
    open 이 아닌 작업은 사용자 답을 기다리는 것이며 완료가 아니다."""
    ok, closed = status(rec, maps(root))
    # waiting: 사용자 답을 기다린다(승인 전이거나 사용자 철회·기준 변경·새 기준으로 닫힘). 에이전트의 완료 선언(done)으로 닫힌 것은 대기가 아니다.
    return {"task": rec.get("id"), "name": rec.get("name"), "approval": "open" if ok else ("closed" if rec.get("approved_at") else "waiting"),
            "waiting": waiting(rec, ok),
            "closed_kind": rec.get("closed_kind") if not ok else None, "closed_maps": closed, "approved_prompt": rec.get("prompt"),
            "targets": rec.get("targets", {}), "conversation_only": rec.get("conversation_only", False),
            "user_messages": rec.get("message_count", 0), "verify": rec.get("verify", {})}


def command(mode, root, state, args):
    """사람·에이전트·검증기가 셸에서 부르는 명령. 승인을 열 수 없다(닫거나 새 작업을 시작하거나 상태를 보여 줄 뿐이다).
    status                      지금 작업의 상태(JSON)
    task begin <작업명>          에이전트가 새 요청을 새 작업으로 판단했을 때: 지금 승인을 닫고 지금 턴의 사용자 원문부터 새 작업을 연다
    task done                   에이전트가 작업을 마쳤을 때: 승인을 닫는다(다음 작업이 이 승인으로 쓰지 못하게)"""
    f, why = pick(state, args)
    if mode == "status":
        print(json.dumps(task_status(root, state, read_json(f, {})) if f else {"task": None, "approval": "waiting", "reason": why},
                         ensure_ascii=False))
        return 0
    sub = args[0] if args else ""
    if sub not in ("begin", "done") or not f:
        print(f"{TAG} " + (why or "사용: approval-gate.py task begin <작업명> | task done [--session <id>]"), file=sys.stderr)
        return 2
    rec, now_maps = read_json(f, {}), maps(root)
    if sub == "begin":
        name = next((a for a in args[1:] if not a.startswith("--") and a != session_arg(args)), None)
        if rec.get("approved"):
            close(rec, "new-task", f"에이전트가 새 작업을 선언함: {name}")
        old = rec.get("id")
        rec = rotate(state, rec, now_maps, current_index(rec), name, rec.get("turn_base"))  # 새 작업의 시작 = 이번 턴 시작 상태
        rec.update(previous_task=old)
    else:
        if rec.get("approved"):
            close(rec, "done", "에이전트가 작업 완료를 선언함")
        rec["state"] = "done"
    f.write_text(json.dumps(rec, ensure_ascii=False))
    print(json.dumps(task_status(root, state, rec), ensure_ascii=False))
    return 0


def main(mode, data):
    try:
        root, state = locate(data.get("cwd"))
    except RuntimeError:
        return  # git 저장소가 아니면 상태를 잴 수 없고 키트 설치 프로젝트도 아니다
    if not (root / ".agents" / "agent-workflow-kit.version").is_file():
        return  # 키트가 설치된 프로젝트에서만 동작한다(키트 원본 저장소·관문 파일만 복사된 곳은 그대로 둔다)
    if mode in ("status", "task"):
        return command(mode, root, state, data.get("args", []))
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
    now_maps = maps(root)
    rec = read_json(approval, {})
    if mode == "prompt":
        state.mkdir(exist_ok=True)
        turn_base = snapshot_files(root, state)  # 이번 턴 시작 때 제품 파일 상태
        rec = rec or new_task(state, now_maps, base=turn_base)  # 세션의 첫 작업: 첫 요청 때 상태가 시작 상태
        prompt = str(data.get("prompt") or "")
        answer = last_answer(data.get("transcript_path"))
        see_answer(rec, answer)  # 대화에 보여 준 기준(에이전트가 내놓은 작업 기록). 앞 턴의 일이므로 앞 턴의 시작 상태를 쓴다
        settle(rec, now_maps)  # 턴 사이에 승인 대상 지도가 바뀌었으면 닫는다
        rec["turn_base"] = turn_base
        if os.environ.get("AWK_GATE_PROMPT_FROM") == "runner":
            # 평가 실행기(evals/run.sh)가 보낸 검증 반환 같은 사용자 아닌 입력: 실행기가 아는 발신 구분을 받아, 글 내용과 관계없이
            # 승인을 열거나 닫지 않고 사용자 원문에도 넣지 않는다. 턴 시작 기록(제품 파일·지도 지문)은 그대로 해서 변경 감시는 계속한다.
            decision = "runner"
        else:
            add_message(state, rec, prompt)
            if is_approval(prompt):
                rec = open_approval(rec, root, state, prompt, now_maps, answer)
                decision = "open"
            elif is_revoke(prompt) or mentions_approval(prompt):
                if rec.get("approved"):
                    close(rec, "user", prompt)  # 철회, 또는 승인 말이 있지만 승인이 아닌 메시지
                decision = "close"
            else:
                decision = "keep"  # 상태 질문·새 요청 등: 뜻을 분류하지 않고 승인 상태를 그대로 둔다
        approval.write_text(json.dumps(rec, ensure_ascii=False))
        turnmaps.write_text(json.dumps(now_maps, ensure_ascii=False))
        start.write_text(json.dumps(product_files(root), ensure_ascii=False))
        blocks.write_text("0")
        (state / f"{key}.laststop").unlink(missing_ok=True)  # 앞 턴의 턴 끝 판단을 새 턴에 다시 쓰지 않는다
        log({"event": "prompt", "decision": decision, "approved": bool(rec.get("approved")), "task": rec.get("id"),
             "targets": sorted(rec.get("targets", {})), "closed_maps": rec.get("closed_maps", []) if not rec.get("approved") else []})
        return
    rec = rec or new_task(state, now_maps) if state.is_dir() else rec
    turn_maps = read_json(turnmaps, {}) if turnmaps.is_file() else None
    if mode == "pre":
        tool, inp = str(data.get("tool_name") or ""), data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        extra = [m for m in (rel_map(root, t) for t in write_targets(inp)) if m] if tool in WRITE_TOOLS else []
        touch(rec, turn_maps, now_maps, extra)
        ok = settle(rec, now_maps)
        if state.is_dir():
            approval.write_text(json.dumps(rec, ensure_ascii=False))
        closed = rec.get("closed_maps", []) if not ok and rec.get("closed_kind") in ("criteria", "new-criteria") else []
        reason = decide(data, root, ok, CHANGED_REASON.format(maps=", ".join(closed)) if closed else REASON)
        log({"event": "pre", "tool": data.get("tool_name"), "approved": ok, "denied": bool(reason), "closed_maps": closed,
             "input": str(inp.get("command") or inp.get("cmd") or inp.get("file_path") or "")[:200]})
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}, ensure_ascii=False))
        return
    # stop
    touch(rec, turn_maps, now_maps)
    ok = settle(rec, now_maps)
    if state.is_dir() and rec:
        approval.write_text(json.dumps(rec, ensure_ascii=False))
    closed = rec.get("closed_maps", []) if not ok and rec.get("closed_kind") in ("criteria", "new-criteria") else []
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
        # status 는 사람·검증기가 직접 실행한다(입력 없이 지금 폴더의 저장소를 본다)
        if mode in ("status", "task"):  # 사람·에이전트·검증기가 셸에서 직접 실행한다(지금 폴더의 저장소)
            sys.exit(main(mode, {"cwd": os.getcwd(), "args": sys.argv[2:]}) or 0)
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
