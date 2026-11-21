"""백업 규칙 초안 합치기 과제의 외부 판정: 끝난 프로젝트의 backup-rules.md 글만 읽는다(실행할 명령이 없는 문서 과제다).

  python3 -I evals/goalflow/tasks/merge-conflict/oracle.py <프로젝트>

given 은 요청과 두 초안이 정한 것(backup-rules.md 하나, 세 줄 이내, 매일 새벽 3시 DB 전체 백업), decision 은 answer.txt 의 사용자 답(보관 기간 90일, 30일은 적지 않음)이다.
세 줄은 빈 줄과 '#' 로 시작하는 제목 줄을 뺀 줄 수로 센다. 실패 알림·복원 시험처럼 두 초안의 나머지 내용은 판정하지 않는다.
"""
import re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge


class FileJudge(Judge):
    """Judge 의 check·finish 만 쓴다. 파일을 읽기만 하므로 항목마다 되돌릴 자료가 없다."""

    def __init__(self, project):
        self.cases = []
        self.tmp = Path(tempfile.mkdtemp(prefix="taskcheck-"))
        self.root = Path(project)

    def fresh(self):
        pass


j = FileJudge(sys.argv[1])
RULES = j.root / "backup-rules.md"


def text():
    assert RULES.is_file(), {"expected": "backup-rules.md"}
    return RULES.read_text(encoding="utf-8")


def body_lines():
    return [line for line in text().splitlines() if line.strip() and not line.lstrip().startswith("#")]


def rules_exist():
    assert text().strip(), {"backup-rules.md": "비어 있다"}


def three_lines():
    lines = body_lines()
    assert 1 <= len(lines) <= 3, {"lines": lines}


def daily_3am_full():
    t = text()
    assert re.search(r"3\s*시|0?3:00", t) and "전체" in t, {"backup-rules.md": t[:300]}


def keeps_90_days():
    t = text()
    assert re.search(r"90\s*일", t), {"backup-rules.md": t[:300]}


def no_30_days():
    t = text()
    assert not re.search(r"(?<!\d)30\s*일", t), {"backup-rules.md": t[:300]}


j.check("rules-file-written", "given", rules_exist)
j.check("at-most-three-lines", "given", three_lines)
j.check("daily-3am-full-backup", "given", daily_3am_full)
j.check("retention-90-days", "decision", keeps_90_days)
j.check("no-30-day-retention", "decision", no_30_days)
j.finish()
