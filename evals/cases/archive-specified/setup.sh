# 출발 상태: 목록에 완료 항목도 [x] 로 보이는 할 일 CLI. list 와 export 가 같은 함수를 쓰고, 정산 시스템이 export CSV 를 가져간다.
mkdir -p tests
cat > todo.py <<'TODO_EOF'
"""할 일 목록 CLI. 할 일은 todo.json 에 저장한다.

사용:
  python3 todo.py add "<내용>"      할 일 추가
  python3 todo.py list              할 일 목록 출력 (번호, [x] 완료 표시, 내용)
  python3 todo.py done <번호>       완료로 표시
  python3 todo.py export <파일.csv> 모든 할 일을 CSV 로 내보낸다(회계·보고용 정산 시스템이 매주 이 파일을 가져간다)
"""
import csv, json, sys
from pathlib import Path

STORE = Path("todo.json")


def load():
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else []


def save(items):
    STORE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def visible(items):
    """list 가 보여 줄 할 일. export 도 이 함수를 쓴다."""
    return items


def main(argv):
    cmd, args = argv[0], argv[1:]
    items = load()
    if cmd == "add":
        items.append({"id": len(items) + 1, "text": args[0], "done": False})
        save(items)
    elif cmd == "list":
        for it in visible(items):
            print(f"{it['id']}. [{'x' if it['done'] else ' '}] {it['text']}")
    elif cmd == "done":
        for it in items:
            if it["id"] == int(args[0]):
                it["done"] = True
        save(items)
    elif cmd == "export":
        with open(args[0], "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "text", "done"])
            for it in visible(items):
                w.writerow([it["id"], it["text"], it["done"]])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
TODO_EOF
cat > tests/test_todo.py <<'TEST_EOF'
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
TEST_EOF
cat > README.md <<'README_EOF'
# 할 일 CLI

`python3 todo.py` 로 쓰는 작은 할 일 목록. 시험: `python3 -m unittest discover -s tests`
README_EOF
