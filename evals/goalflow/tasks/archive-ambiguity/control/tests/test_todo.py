import subprocess, sys, tempfile, unittest
from pathlib import Path

TODO = Path(__file__).resolve().parents[1] / "todo.py"


def run(cwd, *args):
    return subprocess.run([sys.executable, str(TODO), *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_done_items_hidden_from_list(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "add", "빵 사기")
        run(self.dir, "done", "1")
        out = run(self.dir, "list")
        self.assertNotIn("우유 사기", out)
        self.assertIn("빵 사기", out)

    def test_export_keeps_done_items(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "done", "1")
        run(self.dir, "archive")
        run(self.dir, "export", "o.csv")
        self.assertIn("우유 사기,True", (Path(self.dir) / "o.csv").read_text(encoding="utf-8"))

    def test_done_waits_for_archive(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "done", "1")
        self.assertNotIn("우유 사기", run(self.dir, "archived"))
        run(self.dir, "archive")
        self.assertIn("1. 우유 사기", run(self.dir, "archived"))

    def test_archived_excludes_done_not_yet_archived(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "add", "빵 사기")
        run(self.dir, "done", "1")
        run(self.dir, "archive")
        run(self.dir, "done", "2")
        out = run(self.dir, "archived")
        self.assertIn("1. 우유 사기", out)
        self.assertNotIn("빵 사기", out)


if __name__ == "__main__":
    unittest.main()
