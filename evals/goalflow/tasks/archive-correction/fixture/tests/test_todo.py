import csv, os, subprocess, sys, tempfile, unittest
from pathlib import Path

TODO = Path(__file__).resolve().parents[1] / "todo.py"


def run(cwd, *args):
    return subprocess.run([sys.executable, str(TODO), *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_add_and_list(self):
        run(self.dir, "add", "우유 사기")
        self.assertIn("1. [ ] 우유 사기", run(self.dir, "list"))

    def test_done_marks_item(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "done", "1")
        self.assertIn("1. [x] 우유 사기", run(self.dir, "list"))


if __name__ == "__main__":
    unittest.main()
