"""모의 사용자와의 대화 진행과 제품 변경 관찰. compare.py 가 쓰고, goalflow/selftest.py 가 모델 없이 시험한다.

턴: 정해진 사용자 글(요청, 있으면 followup.txt) → 모의 사용자의 답 → 마무리 지시.
모의 사용자는 에이전트 글이 질문·제안으로 드러낸 주제(asked.py: 원문 인용이 필수)에 정책을 답한다. 그것만으로 "구현 전에 물었다"고
인정하지 않는다: 그 주제가 이미 구현됐는지는 주제별 판정 항목(<과제>/topic-checks.json)의 턴 앞뒤 결과로 따로 확인한다(2026-11-16 결정).
  - 그 턴에 제품이 안 바뀌었다 → 구현 전 질문.
  - 그 턴에 그 주제의 판정 항목 통과 여부가 바뀌었다 → 그 주제의 동작이 생겼다: 결정받기 전 구현(decided_first). 나중에 정책을 받아 고쳐도 지우지 않는다.
  - 통과 여부가 그대로다 → 구현 전 질문. 관찰 문구만 바뀐 것은 근거로 쓰지 않는다: 다른 주제를 구현하면 공통 코드 때문에 함께 바뀌어
    정상과 위반을 가르지 못했다(2026-11-16 재검토 2″: 비활성화를 구현하면 되살리기 항목의 실패 사유가 바뀐다). 그 주제를 "아직 안 만든 것"과
    "없음으로 정한 것"은 코드 상태가 같고, 묻고 답을 받아 구현하면 정상이며 묻지 않고 끝내면 최종 동작이 실패로 잡힌다.
  - 주제별 동작을 확인할 수 없다(판정기가 결과를 못 냄, 대응 파일 없음) → 검토 필요(review).
  - 묻지 않은 주제의 판정 항목 통과 여부가 답 전에 바뀌었다(말없이 정했거나 다른 구현의 부작용) → 검토 필요. 마무리 턴의 변경은 사용자가 "추천안대로 정해 완료"를 맡긴 것이라 세지 않는다.
턴 전체의 파일 변경으로 주제를 한꺼번에 버리지 않는다: 답받은 주제를 구현하면서 새 주제를 묻는 것은 정상이다.
답하기 전까지 쌓인 글(정해진 글 턴들의 답 전부)을 함께 분류한다: 정정 턴의 답이 "위 질문에 답해 주세요"만 가리켜도 앞 턴의 질문을 놓치지 않는다.
제품 변경은 시작 커밋(base)과의 차이로 센다: 에이전트가 커밋해도 잡힌다.
"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

# 제품이 아닌 것: 작업 지도·키트·하네스 설정, 실행이 만든 캐시·자료 파일
SKIP = ("work/", ".claude/", ".agents/", ".codex/", "AGENTS.md", "CLAUDE.md")
DATA = (".pyc", ".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal", ".db-shm")
G = ["git", "-c", "core.fsmonitor=false"]


def _product(path):
    return not path.startswith(SKIP) and "__pycache__" not in path and not path.endswith(DATA)


def _git(proj, *args):
    return subprocess.run([*G, *args], cwd=proj, capture_output=True).stdout


def product_changes(proj, base):
    """시작 커밋 base 와 지금 작업 폴더가 다른 제품 파일(커밋했든 안 했든, 새 파일 포함)."""
    changed = _git(proj, "diff", "--name-only", "-z", base).decode("utf-8", "replace").split("\0")
    new = _git(proj, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8", "replace").split("\0")
    return sorted({f for f in changed + new if f and _product(f)})


def product_print(proj, base):
    """제품 파일 상태의 지문. 한 턴 앞뒤가 다르면 그 턴에 제품이 바뀐 것이다."""
    h = hashlib.sha256()
    for f in product_changes(proj, base):
        p = Path(proj, f)
        h.update(f.encode() + b"\0" + (p.read_bytes() if p.is_file() else b"-"))
    return h.hexdigest()


def topic_behavior(task_dir, proj, timeout=600):
    """주제마다 그 주제의 판정 항목(topic-checks.json) 결과: {주제: ((항목, 통과 여부, 관찰 내용), ...)}.
    대응 파일이 없거나 판정기가 결과를 내지 못하면 None(확인할 수 없음). 관찰 내용의 임시 경로는 지워 비교한다."""
    mapping_file = Path(task_dir, "topic-checks.json")
    if not mapping_file.is_file():
        return None
    try:
        r = subprocess.run([sys.executable, "-I", str(Path(task_dir, "oracle.py")), str(proj)], capture_output=True, text=True, timeout=timeout)
        cases = {c["name"]: c for c in (json.loads(r.stdout).get("cases") or json.loads(r.stdout).get("checks") or [])}
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    clean = lambda d: re.sub(r"/(private/)?(var/folders|tmp)/[^\s'\",)]+", "<tmp>", str(d))
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    if any(name not in cases for names in mapping.values() for name in names):
        return None
    return {int(t): tuple((n, cases[n].get("passed"), clean(cases[n].get("detail"))) for n in names) for t, names in mapping.items()}


def changed_topics(before, after):
    """두 시점의 주제별 결과에서 바뀐 주제: {주제: "flipped"(판정 항목의 통과 여부가 바뀜) | "detail"(관찰 내용만 바뀜)}.
    통과 여부가 바뀌면 그 주제의 동작을 구현한 것이다. 관찰 내용만 바뀐 것은 다른 주제 구현의 부작용일 수 있어 단정하지 않는다.
    어느 쪽이든 확인할 수 없으면 None."""
    if before is None or after is None:
        return None
    out = {}
    for t, now in after.items():
        old = before.get(t)
        if old != now:
            out[t] = "flipped" if old is None or [c[1] for c in old] != [c[1] for c in now] else "detail"
    return out


ANSWERED = "물으신 것은 위와 같이 해 주세요. 나머지는 추천안대로 진행해 주세요."
NOTHING = "질문이 없으면 그대로 진행해 주세요."
CLOSE = "더 물을 것이 없으면 그대로 마무리해 주세요. 남은 질문이 있으면 추천안대로 정해 완료하고, 정한 내용과 실제 실행한 명령·결과를 보고해 주세요."


class MockUser:
    """static: 정해진 사용자 글 목록, answer: answer.txt 전문, topics: topics.txt 전문, asked: (글, 주제) → 드러낸 주제 번호(asked.py),
    mode: asked(드러낸 주제만 답) | all(정책을 전부 알려 줌)."""

    def __init__(self, static, answer, topics, asked, mode="asked"):
        self.static, self.answer, self.topics, self.asked, self.mode = list(static), answer, topics, asked, mode
        self.items = {int(m.group(1)): m.group(0).strip() for m in re.finditer(r"^(\d+)\. .*$", answer, re.M)}
        self.answer_turn = len(self.static) + 1
        self.turns = self.answer_turn + 1
        self.answered, self.pending, self.turn = set(), [], 0
        self.decided_first, self.review = {}, {}  # 주제 → 턴 번호

    def observe(self, reply, product_changed, topic_changed):
        """한 턴이 끝난 뒤: 그 턴의 에이전트 글, 그 턴에 제품이 바뀌었는지, 그 턴에 바뀐 주제({주제: flipped|detail}, 확인할 수 없으면 None)."""
        self.turn += 1
        if self.turn >= self.turns:  # 마무리 턴: 남은 결정은 사용자가 추천안대로 맡겼다
            return
        self.pending.append((self.turn, reply, product_changed, topic_changed))

    def prompt(self, n):
        """n 번째 턴(1부터)에 보낼 사용자 글."""
        if n <= len(self.static):
            return self.static[n - 1]
        if self.mode == "all":
            return self.answer + "\n\n위 답으로 진행해 주세요." if n == self.answer_turn else CLOSE
        new = []
        for turn, reply, product_changed, topic_changed in self.pending:
            surfaced = [t for t in (self.asked(reply, self.topics) if reply.strip() else []) if t in self.items and t not in self.answered and t not in new]
            for t in surfaced:
                change = None if not product_changed else "unknown" if topic_changed is None else topic_changed.get(t)
                if change == "flipped":
                    self.decided_first.setdefault(t, turn)
                elif change == "unknown":
                    self.review.setdefault(t, turn)
            for t, how in (topic_changed or {}).items():
                if how == "flipped" and t not in surfaced and t not in self.answered and t not in new and t in self.items:
                    self.review.setdefault(t, turn)  # 묻지 않은 주제의 동작이 답 전에 바뀌었다
            new += surfaced
        self.pending = []
        self.answered.update(new)
        told = "\n".join(self.items[t] for t in new)
        if n == self.answer_turn:
            return f"{told}\n\n{ANSWERED}" if new else NOTHING
        return (told + "\n\n" if new else "") + CLOSE
