import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

TODO = Path(__file__).resolve().parents[1] / "todo.py"


def run(cwd, *args):
    return subprocess.run([sys.executable, str(TODO), *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


class TodoTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = directory.name

    def test_add_and_list(self):
        run(self.dir, "add", "우유 사기")
        self.assertIn("1. [ ] 우유 사기", run(self.dir, "list"))

    def test_done_marks_item(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "done", "1")
        self.assertEqual("", run(self.dir, "list"))
        self.assertEqual("1. [x] 우유 사기\n", run(self.dir, "archive"))
        items = json.loads((Path(self.dir) / "todo.json").read_text(encoding="utf-8"))
        self.assertEqual([{"id": 1, "text": "우유 사기", "done": True}], items)

    def test_list_and_archive_preserve_ids_order_and_records(self):
        for text in ["우유 사기", "책 반납", "산책", "청소"]:
            run(self.dir, "add", text)
        run(self.dir, "done", "4")
        run(self.dir, "done", "2")
        store = Path(self.dir) / "todo.json"
        saved = store.read_bytes()
        for _ in range(2):
            self.assertEqual("1. [ ] 우유 사기\n3. [ ] 산책\n", run(self.dir, "list"))
            self.assertEqual("2. [x] 책 반납\n4. [x] 청소\n", run(self.dir, "archive"))
        self.assertEqual(saved, store.read_bytes())

    def test_empty_list_and_archive(self):
        self.assertEqual("", run(self.dir, "list"))
        self.assertEqual("", run(self.dir, "archive"))
        run(self.dir, "add", "우유 사기")
        self.assertEqual("", run(self.dir, "archive"))

    def test_export_includes_active_and_archived_items(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "add", "책, 반납")
        run(self.dir, "done", "2")
        run(self.dir, "list")
        run(self.dir, "archive")
        target = Path(self.dir) / "todos.csv"
        run(self.dir, "export", str(target))
        with target.open(newline="", encoding="utf-8") as f:
            self.assertEqual([
                ["id", "text", "done"],
                ["1", "우유 사기", "False"],
                ["2", "책, 반납", "True"],
            ], list(csv.reader(f)))


if __name__ == "__main__":
    unittest.main()
