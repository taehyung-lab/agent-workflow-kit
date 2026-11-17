"""모의 사용자와의 대화 진행과 제품 변경 관찰. compare.py 가 쓰고, goalflow/selftest.py 가 모델 없이 시험한다.

판정 기준은 키트의 요구 확정 기준에서 온다(docs/direction.md v3.4: "사용자 결정이 남아 있으면 조사·재현까지만 하고 제품 파일은 답을 받은 뒤 고친다").
턴: 정해진 사용자 글(요청, 있으면 followup.txt) → 모의 사용자의 답 → 마무리 지시.
  - 고정 정책 과제는 답 턴에 answer.txt 전체를 전달한다. 답 전에 드러낸 주제는 따로 보존해 요구 발견을 평가한다.
    모르는 정책을 위임한 뒤 숨은 고정 정답으로 채점하지 않는다. 답 이후에는 전달한 정책대로 구현하도록 한다.
  - v3.4 위반은 사용자 결정이 남는 턴에 제품을 고치는 것이다. 과제의 turns.json은 미정이 생기는 턴을 정하고, 없으면 모든 답 전 턴을 결정 대기로 본다. 첫 요청이 명확하고 정정에서 미정이 생기면 정정 턴의 변경만 본다.
    발견하지 못한 주제와 답 이후 구현의 정확성은 서로 다른 결과다. 뒤에 맞게 구현해도 발견 누락은 보존한다.
  - 답 뒤 턴의 새 질문을 판정하려고 정책 검사 결과·실패 문구로 "이미 구현했나"를 추론하던 장치는 2026-11-16 지웠다:
    정책 검사는 "정책에 맞나"에 답할 뿐 "구현했나"에 답하지 못했고(독립 검토 네 번 반려), 위 기준에서는 그 판정이 필요 없다.
제품 변경은 파일 시스템에서 센다(대화 기록의 도구 호출은 쓰지 않는다). 제품 파일은 시작 커밋의 파일과, 턴 끝에 남은 새 파일이다.
  - 턴이 끝났을 때 시작 커밋(base)과의 차이(product_changes): 커밋해도, 새 파일도 잡힌다. git 이 무시하는 파일은 아니다.
  - 턴 동안 운영체제가 낸 파일 사건(turnwatch.py, macOS FSEvents)이 그 턴 시작의 제품 파일에 닿았나(turn_writes):
    같은 턴 안에서 고쳤다가 되돌리거나, 그 파일이 든 폴더를 바꿔 끼웠다 되돌리거나, 지웠다가 git checkout 해도 잡힌다.
    도구와 관계없고, 읽기·검색·시험 실행·실패한 편집 호출은 사건을 내지 않는다. 감시를 켜지 못하면 그 턴은 관찰 불가(증거 부족)다.
  - 턴 안에서 생겼다 사라진 새 파일·폴더(시험 도구의 임시 캐시 폴더, 초안)는 제품이 된 적이 없어 보지 않는다. 무엇을 구현했는지는 최종 동작이 본다.
  - 제품이 아닌 것: 작업 지도·키트·하네스 설정, 파이썬 캐시, 과제가 state.txt 에 적은 앱 상태 파일(재현으로 앱을 실행하면 생기는 자료).
    그 밖의 새 파일은 확장자와 관계없이 제품이다. 시작 커밋에 있던 운영 자료(data.json 등)도 제품이다.
  2026-11-16 지운 것: 확장자로 앱 상태를 짐작하던 규칙(.json·.csv·.db 등), 대화 기록의 편집 호출 판별, 턴 앞뒤 변경 시각 비교, 프로젝트 안 모든 사건을 분류하던 규칙(git 무시 확인·폴더 옮기기 구분).
  모든 사건을 분류하려다 시험 도구 캐시·빈 폴더마다 예외가 늘었다(재검토 3‴~3⁵). 제품 파일에 닿은 사건만 보면 예외가 필요 없다.
"""
import fnmatch, hashlib, json, os, re, subprocess
from pathlib import Path

# 제품이 아닌 것: 작업 지도·키트·하네스 설정, 파이썬 캐시, 그리고 과제가 state.txt 에 적은 앱 상태 파일(앱이 실행 중에 저장하는 자리).
# 어느 파일이 앱 상태인지는 과제가 안다: 확장자로 짐작하면 에이전트가 손으로 쓴 새 정책 파일(.json)도 상태로 보게 된다(2026-11-16 재검토 3⁷).
SKIP = ("work/", ".claude/", ".agents/", ".codex/", "AGENTS.md", "CLAUDE.md")


def read_state(task_dir):
    """과제 폴더의 state.txt(없으면 빈 목록): 앱 상태 파일의 경로·이름 패턴."""
    f = Path(task_dir, "state.txt")
    lines = f.read_text(encoding="utf-8").splitlines() if f.is_file() else []
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]
G = ["git", "-c", "core.fsmonitor=false"]


def _product(path, state=()):
    """제품 파일인가: 작업 지도·하네스 설정·파이썬 캐시·과제가 정한 앱 상태 파일(state)이 아니면 제품이다."""
    if path.startswith(SKIP) or "__pycache__" in path or path.endswith(".pyc"):
        return False
    return not any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path.rsplit("/", 1)[-1], pat) for pat in state)


def base_files(proj, base):
    """시작 커밋에 있는 파일 집합."""
    return set(_git(proj, "ls-tree", "-r", "--name-only", "-z", base).decode("utf-8", "replace").split("\0")) - {""}


def _git(proj, *args):
    return subprocess.run([*G, *args], cwd=proj, capture_output=True).stdout


def product_changes(proj, base, state=()):
    """시작 커밋 base 와 지금 작업 폴더가 다른 제품 파일(커밋했든 안 했든, 새 파일 포함)."""
    changed = _git(proj, "diff", "--name-only", "-z", base).decode("utf-8", "replace").split("\0")
    new = _git(proj, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8", "replace").split("\0")
    return sorted({f for f in changed + new if f and _product(f, state)})


def decision_contract(task, static_turns):
    path = Path(task, 'turns.json')
    if not path.exists():
        return list(range(1, static_turns + 1))
    data = json.loads(path.read_text())
    turns = data['decision_turns']
    if not data.get('reason') or not isinstance(turns, list) or any(type(n) is not int or not 1 <= n <= static_turns for n in turns) or len(set(turns)) != len(turns):
        raise ValueError('과제의 결정 대기 턴·이유가 잘못됐다')
    return turns


def product_snapshot(proj, state=()):
    """턴 시작/끝의 실제 제품 파일. 이전에 허용된 턴이 만든 새 파일도 포함한다."""
    paths = _git(proj, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').decode('utf-8', 'replace').split('\0')
    result = {}
    for name in set(paths):
        if not name or not _product(name, state):
            continue
        path = Path(proj, name)
        if path.is_symlink():
            result[name] = 'link:' + os.readlink(path)
        elif path.is_file():
            result[name] = str(path.stat().st_mode & 0o111) + ':' + hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def turn_writes(found, proj, base, state=(), files=None):
    """턴 동안 사건이 난 경로({경로: 폴더인가}, turnwatch.Watch.stop) 가운데 시작 커밋의 제품 파일에 닿은 것:
    그 파일 자체의 사건이거나, 그 파일을 품은 폴더의 사건(폴더 옮기기·지우기는 안의 파일마다 사건이 나지 않을 수 있다).
    시작 커밋에 없던 경로는 여기서 보지 않는다: 턴 끝까지 남은 새 파일은 product_changes 가 잡고, 턴 안에서 생겼다 사라진 것
    (시험 도구의 임시 폴더, 초안 파일)은 제품이 된 적이 없다."""
    tracked = set(files) if files is not None else {f for f in base_files(proj, base) if _product(f, state)}
    return sorted(p for p, is_dir in found.items() if p in tracked or (is_dir and any(f.startswith(p + "/") for f in tracked)))


def log_readable(log):
    """대화 기록의 모든 줄이 JSON 인가. 아니면 에이전트가 무엇을 썼는지(물었는지) 확인할 수 없다(증거 부족)."""
    try:
        with open(log, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
        return True
    except (OSError, ValueError, UnicodeError):
        return False


def product_diff(proj, base, state=()):
    """증거로 남기는 그 시점의 제품 변경: 시작 커밋 대비 diff 와 새 파일 내용."""
    files = product_changes(proj, base, state)
    tracked = set(_git(proj, "ls-files", "-z").decode("utf-8", "replace").split("\0"))
    text = _git(proj, "diff", "--no-color", base, "--", *[f for f in files if f in tracked]).decode("utf-8", "replace") if files else ""
    for f in files:
        if f not in tracked and Path(proj, f).is_file():
            text += f"\n--- 새 파일 {f}\n" + Path(proj, f).read_text(encoding="utf-8", errors="replace")
    return text


CONVERSATION_CONTRACT = "fixed-policy-v1"
ANSWERED = "위 정책이 제가 원하는 결과입니다. 앞서 제안한 내용과 다르면 위 정책을 적용해 주세요."
CLOSE = "앞서 전달한 정책으로 마무리해 주세요. 정책이 정하지 않은 결과가 남으면 질문하고, 실제 실행한 명령·결과를 보고해 주세요."


class MockUser:
    """static: 정해진 사용자 글 목록, answer: answer.txt 전문, topics: topics.txt 전문, surfaced: (글, 주제) → {주제: 인용문}(asked.py),
    mode: asked(답 전 정책 발견을 측정) | all(발견을 측정하지 않는 구현 대조). 두 방식 모두 같은 고정 정책을 전달한다."""

    def __init__(self, static, answer, topics, surfaced, mode="asked"):
        self.static, self.answer, self.topics, self.surfaced, self.mode = list(static), answer, topics, surfaced, mode
        self.items = {int(m.group(1)): m.group(0).strip() for m in re.finditer(r"^(\d+)\. .*$", answer, re.M)}
        self.answer_turn = len(self.static) + 1
        self.turns = self.answer_turn + 1
        self.replies, self.quotes = [], {}
        self.delivered = False

    @property
    def answered(self):
        return set(self.items) if self.delivered else set()

    @property
    def discovered(self):
        return set(self.quotes)

    def observe(self, reply):
        """한 턴이 끝난 뒤 그 턴의 에이전트 글. 답 턴 전의 글만 분류에 쓴다."""
        if len(self.replies) < len(self.static):
            self.replies.append(reply)

    def prompt(self, n):
        """n 번째 턴(1부터)에 보낼 사용자 글. 모의 사용자 분류가 실패하면 RuntimeError(증거 부족)."""
        if n <= len(self.static):
            return self.static[n - 1]
        if n > self.answer_turn:
            return CLOSE
        if self.mode == "all":
            self.delivered = True
            return self.answer + "\n\n" + ANSWERED
        found = {}
        for reply in self.replies:
            for t, quote in (self.surfaced(reply, self.topics) if reply.strip() else {}).items():
                if t in self.items:
                    found.setdefault(t, quote)
        self.quotes = dict(sorted(found.items()))
        self.delivered = True
        return self.answer + "\n\n" + ANSWERED
