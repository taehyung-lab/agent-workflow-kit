import csv, json, os, subprocess, sys, tempfile, unittest
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

    def test_done_moves_item_to_archive(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "done", "1")
        self.assertEqual("", run(self.dir, "list"))
        self.assertEqual("1. [x] 우유 사기\n", run(self.dir, "archive"))
        items = json.loads((Path(self.dir) / "todo.json").read_text(encoding="utf-8"))
        self.assertEqual([{"id": 1, "text": "우유 사기", "done": True}], items)

    def test_mixed_items_and_add_after_completion(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "add", "책 읽기")
        run(self.dir, "done", "1")
        run(self.dir, "add", "산책")
        self.assertEqual("2. [ ] 책 읽기\n3. [ ] 산책\n", run(self.dir, "list"))
        self.assertEqual("1. [x] 우유 사기\n", run(self.dir, "archive"))

    def test_empty_lists(self):
        self.assertEqual("", run(self.dir, "list"))
        self.assertEqual("", run(self.dir, "archive"))
        run(self.dir, "add", "우유 사기")
        self.assertEqual("", run(self.dir, "archive"))

    def test_existing_completed_items_appear_in_archive(self):
        store = Path(self.dir) / "todo.json"
        store.write_text(json.dumps([
            {"id": 1, "text": "우유 사기", "done": True},
            {"id": 2, "text": "책 읽기", "done": False},
        ], ensure_ascii=False), encoding="utf-8")
        original = store.read_bytes()
        self.assertEqual("2. [ ] 책 읽기\n", run(self.dir, "list"))
        self.assertEqual("1. [x] 우유 사기\n", run(self.dir, "archive"))
        self.assertEqual(original, store.read_bytes())

    def test_export_includes_active_and_archived_items(self):
        run(self.dir, "add", "우유 사기")
        run(self.dir, "add", "책 읽기")
        run(self.dir, "done", "1")
        output = Path(self.dir) / "report.csv"
        run(self.dir, "export", str(output))
        with output.open(newline="", encoding="utf-8") as f:
            self.assertEqual([
                ["id", "text", "done"],
                ["1", "우유 사기", "True"],
                ["2", "책 읽기", "False"],
            ], list(csv.reader(f)))


if __name__ == "__main__":
    unittest.main()
