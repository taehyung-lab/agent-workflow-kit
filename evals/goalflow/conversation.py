"""모의 사용자와의 대화 진행과 제품 변경 관찰. compare.py 가 쓰고, goalflow/selftest.py 가 모델 없이 시험한다.

턴: 정해진 사용자 글(요청, 있으면 followup.txt) → 모의 사용자의 답 → 마무리 지시.
모의 사용자는 에이전트가 **제품 파일을 바꾸지 않은 턴**에 드러낸 주제만 답한다. 그 턴에 제품이 바뀌었으면 드러낸 것이 아니라 구현한 것이다
(글이 "아직 안 했다"인지 "이미 했다"인지를 모델 해석에 맡기면 이미 구현한 주제에도 정책이 새어 나간다: 2026-11-16 독립 검토).
답하기 전까지 쌓인 글(정해진 글 턴들의 답 전부)을 함께 분류한다: 정정 턴의 답이 "위 질문에 답해 주세요"만 가리켜도 앞 턴의 질문을 놓치지 않는다.
제품 변경은 시작 커밋(base)과의 차이로 센다: 에이전트가 커밋해도 잡힌다.
"""
import hashlib, re, subprocess
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
        self.answered, self.pending = set(), []

    def observe(self, reply, product_changed):
        """한 턴이 끝난 뒤: 그 턴의 에이전트 글과 그 턴에 제품이 바뀌었는지."""
        if not product_changed and reply.strip():
            self.pending.append(reply)

    def prompt(self, n):
        """n 번째 턴(1부터)에 보낼 사용자 글."""
        if n <= len(self.static):
            return self.static[n - 1]
        if self.mode == "all":
            return self.answer + "\n\n위 답으로 진행해 주세요." if n == self.answer_turn else CLOSE
        text, self.pending = "\n\n".join(self.pending), []
        new = [t for t in (self.asked(text, self.topics) if text else []) if t in self.items and t not in self.answered]
        self.answered.update(new)
        told = "\n".join(self.items[t] for t in new)
        if n == self.answer_turn:
            return f"{told}\n\n{ANSWERED}" if new else NOTHING
        return (told + "\n\n" if new else "") + CLOSE
