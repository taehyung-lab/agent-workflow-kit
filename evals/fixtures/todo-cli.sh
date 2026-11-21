# 출발 상태: 목록에 완료 항목도 [x] 로 보이는 할 일 CLI. list 와 export 가 같은 함수를 쓰고, 정산 시스템이 export CSV 를 가져간다.
# EVALS_LANG=python(기본)·js 로 같은 동작의 CLI 를 다른 언어로 만든다. 어느 언어든 실행은 bin/todo, 검사는 bin/test 다(판정도 이 둘만 쓴다).
lang=${EVALS_LANG:-python}
mkdir -p bin tests
printf 'todo.json\n__pycache__/\nnode_modules/\n' > .gitignore
case "$lang" in
python)
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
printf '#!/bin/sh\nexec python3 "$(dirname "$0")/../todo.py" "$@"\n' > bin/todo
printf '#!/bin/sh\ncd "$(dirname "$0")/.." && exec python3 -m unittest discover -s tests\n' > bin/test
src="todo.py"
;;
js)
cat > todo.js <<'TODO_EOF'
// 할 일 목록 CLI. 할 일은 todo.json 에 저장한다.
//
// 사용:
//   bin/todo add "<내용>"      할 일 추가
//   bin/todo list              할 일 목록 출력 (번호, [x] 완료 표시, 내용)
//   bin/todo done <번호>       완료로 표시
//   bin/todo export <파일.csv> 모든 할 일을 CSV 로 내보낸다(회계·보고용 정산 시스템이 매주 이 파일을 가져간다)
const fs = require("fs");

const STORE = "todo.json";
const USAGE = fs.readFileSync(__filename, "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n");

function load() {
  return fs.existsSync(STORE) ? JSON.parse(fs.readFileSync(STORE, "utf8")) : [];
}

function save(items) {
  fs.writeFileSync(STORE, JSON.stringify(items, null, 1));
}

// list 가 보여 줄 할 일. export 도 이 함수를 쓴다.
function visible(items) {
  return items;
}

function csvCell(value) {
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function main(argv) {
  const [cmd, ...args] = argv;
  const items = load();
  if (cmd === "add") {
    items.push({ id: items.length + 1, text: args[0], done: false });
    save(items);
  } else if (cmd === "list") {
    for (const it of visible(items)) console.log(`${it.id}. [${it.done ? "x" : " "}] ${it.text}`);
  } else if (cmd === "done") {
    for (const it of items) if (it.id === Number(args[0])) it.done = true;
    save(items);
  } else if (cmd === "export") {
    const rows = [["id", "text", "done"], ...visible(items).map((it) => [it.id, it.text, it.done ? "True" : "False"])];
    fs.writeFileSync(args[0], rows.map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n");
  } else {
    console.log(USAGE);
    return 1;
  }
  return 0;
}

process.exitCode = main(process.argv.slice(2));
TODO_EOF
cat > tests/todo.test.js <<'TEST_EOF'
const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const TODO = path.resolve(__dirname, "..", "bin", "todo");
const run = (cwd, ...args) => execFileSync(TODO, args, { cwd, encoding: "utf8" });
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "todo-"));

test("add and list", () => {
  const dir = tmp();
  run(dir, "add", "우유 사기");
  assert.match(run(dir, "list"), /1\. \[ \] 우유 사기/);
});

test("done marks item", () => {
  const dir = tmp();
  run(dir, "add", "우유 사기");
  run(dir, "done", "1");
  assert.match(run(dir, "list"), /1\. \[x\] 우유 사기/);
});
TEST_EOF
printf '#!/bin/sh\nexec node "$(dirname "$0")/../todo.js" "$@"\n' > bin/todo
printf '#!/bin/sh\ncd "$(dirname "$0")/.." && exec node --test\n' > bin/test
src="todo.js"
;;
*) echo "지원하지 않는 EVALS_LANG: $lang" >&2; exit 1;;
esac
chmod +x bin/todo bin/test
cat > README.md <<README_EOF
# 할 일 CLI

\`bin/todo\` 로 쓰는 작은 할 일 목록(구현: \`$src\`). 시험: \`bin/test\`
README_EOF
