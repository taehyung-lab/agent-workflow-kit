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
  assert.match(run(dir, "archive"), /1\. \[x\] 우유 사기/);
});

test("done moves item to archive", () => {
  const dir = tmp();
  run(dir, "add", "우유 사기");
  run(dir, "done", "1");
  assert.strictEqual(run(dir, "list"), "");
  assert.strictEqual(run(dir, "archive"), "1. [x] 우유 사기\n");
});
