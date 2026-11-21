"""할 일 보관함 과제의 외부 판정: 끝난 프로젝트의 공개 명령(bin/todo, 없으면 python3 todo.py)만 실행해 출력과 내보낸 CSV 를 본다.

  python3 -I evals/goalflow/tasks/archive-ambiguity/oracle.py <프로젝트>

archive-correction 과제도 같은 정책이라 이 판정기를 그대로 쓴다.
given 은 요청과 기존 문서·시험이 정한 것(목록은 안 끝난 항목만, 내보내기는 모든 항목, 번호 유지), decision 은 answer.txt 의 사용자 답이 정한 것이다.
항목마다 끝난 프로젝트를 새로 복사하고 최상위 *.json(에이전트가 손으로 시험하며 남긴 자료)을 지운 빈 상태에서 시작한다.
given 항목은 사용자 답이 정한 명령(archive·archived)에 기대지 않는다. 내보내기 항목만 archive 를 실행해 보고, 그 종료 코드는 보지 않는다.
"""
import csv, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge


class TodoJudge(Judge):
    """Judge 의 check·public_tests·finish 를 쓰고, 자료 파일과 공개 명령만 이 과제에 맞춘다(출력이 JSON 이 아닌 글 줄이다)."""

    def __init__(self, project):
        self.cases = []
        self.tmp = Path(tempfile.mkdtemp(prefix="taskcheck-"))
        self.source, self.root = self.tmp / "source", self.tmp / "p"
        shutil.copytree(project, self.source, ignore=shutil.ignore_patterns(".git", "__pycache__", "work", ".claude", ".agents", ".codex", "node_modules"))
        for f in self.source.glob("*.json"):
            f.unlink()

    def fresh(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.copytree(self.source, self.root)

    def run(self, *args):
        """공개 명령 한 번. (종료 코드, 표준 출력)."""
        cli = [str(self.root / "bin" / "todo")] if (self.root / "bin" / "todo").is_file() else [sys.executable, "todo.py"]
        p = subprocess.run(cli + [str(a) for a in args], cwd=self.root, capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout

    def ok(self, *args):
        code, out = self.run(*args)
        assert code == 0, {"args": args, "exit": code}
        return out

    def public_tests(self):
        if (self.root / "bin" / "test").is_file():
            p = subprocess.run([str(self.root / "bin" / "test")], cwd=self.root, capture_output=True, text=True, timeout=300)
            assert p.returncode == 0, p.stderr[-300:]
        else:
            super().public_tests()


j = TodoJudge(sys.argv[1])


def add(*texts):
    for t in texts:
        j.ok("add", t)


def shows(out, text):
    return text in out


def numbered(out, number, text):
    """'번호. ... 내용' 줄이 있는지(번호와 내용이 한 줄에)."""
    return re.search(rf"^\s*{number}\.\s.*{re.escape(text)}", out, re.M) is not None


def list_hides_done():
    add("우유 사기", "빵 사기")
    j.ok("done", 1)
    out = j.ok("list")
    assert not shows(out, "우유 사기") and shows(out, "빵 사기"), {"list": out}


def export_all():
    add("우유 사기", "빵 사기", "달걀 사기")
    j.ok("done", 1)
    j.run("archive")  # 사용자 답의 보관 명령. 없거나 다른 뜻이어도 이 항목은 내보내기만 본다.
    j.ok("done", 2)
    j.ok("export", "o.csv")
    rows = list(csv.reader(open(j.root / "o.csv", encoding="utf-8")))
    assert rows and rows[0][:3] == ["id", "text", "done"], {"header": rows[:1]}
    got = sorted(r[:3] for r in rows[1:])
    want = [["1", "우유 사기", "True"], ["2", "빵 사기", "True"], ["3", "달걀 사기", "False"]]
    assert got == want, {"rows": got, "want": want}


def numbers_kept():
    add("우유 사기", "빵 사기", "달걀 사기")
    j.ok("done", 2)
    j.run("archive")
    out = j.ok("list")
    assert numbered(out, 1, "우유 사기") and numbered(out, 3, "달걀 사기"), {"list": out}
    j.ok("done", 3)
    out = j.ok("list")
    assert shows(out, "우유 사기") and not shows(out, "달걀 사기"), {"list": out}


def done_waits_for_archive():
    add("우유 사기", "빵 사기")
    j.ok("done", 1)
    out = j.ok("archived")
    assert not shows(out, "우유 사기"), {"archived_before_archive": out}
    assert not shows(j.ok("list"), "우유 사기")
    j.ok("archive")
    out = j.ok("archived")
    assert numbered(out, 1, "우유 사기") and not shows(out, "빵 사기"), {"archived": out}


def archive_moves_all_done():
    add("우유 사기", "빵 사기", "달걀 사기")
    j.ok("done", 1)
    j.ok("done", 2)
    j.ok("archive")
    out = j.ok("archived")
    assert numbered(out, 1, "우유 사기") and numbered(out, 2, "빵 사기") and not shows(out, "달걀 사기"), {"archived": out}
    out = j.ok("list")
    assert shows(out, "달걀 사기") and not shows(out, "우유 사기") and not shows(out, "빵 사기"), {"list": out}


def archived_only_archived():
    add("우유 사기", "빵 사기", "달걀 사기")
    j.ok("done", 1)
    j.ok("archive")
    j.ok("done", 2)
    out = j.ok("archived")
    assert numbered(out, 1, "우유 사기") and not shows(out, "빵 사기"), {"archived": out}
    out = j.ok("list")
    assert shows(out, "달걀 사기") and not shows(out, "빵 사기"), {"list": out}
    j.ok("archive")
    out = j.ok("archived")
    assert numbered(out, 1, "우유 사기") and numbered(out, 2, "빵 사기"), {"archived_after_second_archive": out}


j.check("list-hides-done-items", "given", list_hides_done)
j.check("export-includes-all-items", "given", export_all)
j.check("item-numbers-kept", "given", numbers_kept)
j.check("public-tests-pass", "given", j.public_tests)
j.check("done-item-waits-for-archive-command", "decision", done_waits_for_archive)
j.check("archive-moves-all-done-items", "decision", archive_moves_all_done)
j.check("archived-lists-only-archived-items", "decision", archived_only_archived)
j.finish()
