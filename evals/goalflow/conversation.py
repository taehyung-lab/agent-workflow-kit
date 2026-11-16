"""모의 사용자와의 대화 진행과 제품 변경 관찰. compare.py 가 쓰고, goalflow/selftest.py 가 모델 없이 시험한다.

판정 기준은 키트의 요구 확정 기준에서 온다(docs/direction.md v3.4: "사용자 결정이 남아 있으면 조사·재현까지만 하고 제품 파일은 답을 받은 뒤 고친다").
턴: 정해진 사용자 글(요청, 있으면 followup.txt) → 모의 사용자의 답 → 마무리 지시.
  - 모의 사용자는 답 턴에 한 번 답한다: 그때까지 에이전트가 쓴 글 전부에서 질문·제안으로 드러낸 주제(asked.py, 원문 인용 필수)의 정책을 알려 주고
    "나머지는 추천안대로 진행해 주세요"로 남은 결정을 맡긴다. 그 뒤로는 정책을 더 알려 주지 않는다(실제 사용자도 맡긴 뒤 다시 알려 주지 않는다).
  - 그래서 v3.4 위반은 "첫 답 전에 제품을 고쳤다" 하나로 정해지고(table.edits_before_answer), 답 뒤의 구현은 맡긴 결정이다.
    물어야 할 것을 첫 답 전에 찾지 못했으면 그 주제는 추천안대로 정해져 최종 동작 판정(oracle)에서 드러난다.
  - 답 뒤 턴의 새 질문을 판정하려고 정책 검사 결과·실패 문구로 "이미 구현했나"를 추론하던 장치는 2026-11-16 지웠다:
    정책 검사는 "정책에 맞나"에 답할 뿐 "구현했나"에 답하지 못했고(독립 검토 네 번 반려), 위 기준에서는 그 판정이 필요 없다.
제품 변경은 두 증거로 센다: 턴이 끝났을 때 시작 커밋(base)과의 차이(커밋해도 잡힘)와, 그 턴의 대화 기록에 남은 제품 파일 편집 호출
(같은 턴 안에서 고쳤다가 되돌려 끝 상태가 같아도 잡힘: 2026-11-16 재검토 3). 대화 기록을 온전히 읽을 수 없으면 증거 부족이다.
"""
import json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def product_edit_calls(log, proj):
    """그 턴의 대화 기록(log)에 남은 편집 호출이 닿은 제품 파일. 기록을 읽을 수 없거나 JSON 이 아닌 줄이 있으면 None(증거 부족).
    경로가 명시된 편집 기록만 쓴다: Claude 의 Write·Edit 류 도구 호출(file_path)과 Codex 의 파일 변경 사건(paths).
    셸 명령은 쓰지 않는다: "파일 이름과 > 가 함께 있으면 편집"이라는 판별은 작업 지도를 셸로 쓰며 파일 이름을 적기만 해도 편집으로 잡아,
    실제 변경이 없던 지난 실행 88개 중 27개를 편집으로 셌다(2026-11-16). 셸로 같은 턴 안에 고쳤다가 되돌린 것은 잡지 못한다(한계)."""
    from transcript import calls
    try:
        with open(log, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
        root, found = Path(proj).resolve(), set()
        for c in calls(log):
            paths = [str(c["input"].get("file_path") or "")] if c["kind"] == "tool" and c["name"] in ("Write", "Edit", "MultiEdit", "NotebookEdit") \
                else list(c["input"].get("paths") or []) if c["kind"] == "edit" else []
            for target in filter(None, paths):
                full = Path(target) if Path(target).is_absolute() else root / target
                try:
                    rel = full.resolve().relative_to(root).as_posix()
                except ValueError:
                    continue
                if _product(rel):
                    found.add(rel)
        return sorted(found)
    except (OSError, ValueError, UnicodeError):
        return None


def product_diff(proj, base):
    """증거로 남기는 그 시점의 제품 변경: 시작 커밋 대비 diff 와 새 파일 내용."""
    files = product_changes(proj, base)
    tracked = set(_git(proj, "ls-files", "-z").decode("utf-8", "replace").split("\0"))
    text = _git(proj, "diff", "--no-color", base, "--", *[f for f in files if f in tracked]).decode("utf-8", "replace") if files else ""
    for f in files:
        if f not in tracked and Path(proj, f).is_file():
            text += f"\n--- 새 파일 {f}\n" + Path(proj, f).read_text(encoding="utf-8", errors="replace")
    return text


ANSWERED = "물으신 것은 위와 같이 해 주세요. 나머지는 추천안대로 진행해 주세요."
NOTHING = "질문이 없으면 그대로 진행해 주세요."
CLOSE = "더 물을 것이 없으면 그대로 마무리해 주세요. 남은 질문이 있으면 추천안대로 정해 완료하고, 정한 내용과 실제 실행한 명령·결과를 보고해 주세요."


class MockUser:
    """static: 정해진 사용자 글 목록, answer: answer.txt 전문, topics: topics.txt 전문, surfaced: (글, 주제) → {주제: 인용문}(asked.py),
    mode: asked(드러낸 주제만 답) | all(정책을 전부 알려 줌)."""

    def __init__(self, static, answer, topics, surfaced, mode="asked"):
        self.static, self.answer, self.topics, self.surfaced, self.mode = list(static), answer, topics, surfaced, mode
        self.items = {int(m.group(1)): m.group(0).strip() for m in re.finditer(r"^(\d+)\. .*$", answer, re.M)}
        self.answer_turn = len(self.static) + 1
        self.turns = self.answer_turn + 1
        self.replies, self.quotes = [], {}  # 답 전까지의 에이전트 글, 답한 주제 → 그 주제를 드러낸 인용문(증거)

    @property
    def answered(self):
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
            self.quotes = {t: "(MOCK=all)" for t in self.items}
            return self.answer + "\n\n위 답으로 진행해 주세요."
        found = {}
        for reply in self.replies:
            for t, quote in (self.surfaced(reply, self.topics) if reply.strip() else {}).items():
                if t in self.items:
                    found.setdefault(t, quote)
        self.quotes = dict(sorted(found.items()))
        return "\n".join(self.items[t] for t in self.quotes) + f"\n\n{ANSWERED}" if self.quotes else NOTHING
