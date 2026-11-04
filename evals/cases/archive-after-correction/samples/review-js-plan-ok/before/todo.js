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
