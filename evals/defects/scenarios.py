"""결함 사례(지향점 핵심 시험): 할 일 앱에 '이전 단계에서 구현해 둔 상태'를 심는다. 각 사례 = 요청 원문, 승인된 계획, 구현(결함 포함 또는 정상), 사용자 입장 판정.
사용: python3 scenarios.py apply <이름> <프로젝트>   /   python3 scenarios.py check <이름> <프로젝트>   /   python3 scenarios.py text <이름> request|plan
판정은 실제 결과만 본다(오류 이름을 맞혔는지가 아니라 결과가 고쳐졌는지). check 종료 코드 0=통과, 1=실패.
"""
import csv, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

LIST_LINE = '''        for it in visible(items):
            print(f"{it['id']}. [{'x' if it['done'] else ' '}] {it['text']}")'''
ADD_LINE = '''        items.append({"id": len(items) + 1, "text": args[0], "done": False})
        save(items)'''

def edit(p, pairs):
    s = Path(p).read_text(encoding="utf-8")
    for a, b in pairs:
        assert a in s, a[:40]
        s = s.replace(a, b, 1)
    Path(p).write_text(s, encoding="utf-8")

def hide_done_test(project):
    """완료 항목을 목록에서 숨기는 변경: 기존 '목록에 [x] 로 보인다' 검사를 새 기대로 바꾼다(구현자가 승인된 계획대로 바꾼 상태)."""
    edit(Path(project, "tests/test_todo.py"), [('        self.assertIn("1. [x] 우유 사기", run(self.dir, "list"))', '        self.assertNotIn("우유 사기", run(self.dir, "list"))')])


def add_test(project, body):
    t = Path(project, "tests/test_todo.py"); s = t.read_text(encoding="utf-8")
    s = s.replace("\n\nif __name__", "\n" + body + "\n\nif __name__") if "\nif __name__" in s else s + "\n" + body + "\n"
    t.write_text(s, encoding="utf-8")

S = {
 "omit-a": dict(kind="요구 누락",
   request="완료한 할 일은 목록에서 빼고 python3 todo.py archive 로 따로 볼 수 있게 해 주세요. 그리고 목록 맨 아래에 '완료 N개' 줄을 보여 주세요(N 은 완료한 할 일 수). CSV 내보내기는 지금처럼 모든 할 일을 내보냅니다.",
   plan="계획: list 는 완료하지 않은 할 일만 보여 주고, 새 archive 명령이 완료한 할 일을 보여 줍니다. CSV 내보내기는 그대로 모든 할 일을 내보냅니다. 확인: bin/test 에 list·archive 검사를 더합니다."),
 "omit-b": dict(kind="요구 누락",
   request="add 할 때 내용 앞뒤 공백을 지워 주세요. 공백만 있거나 빈 내용이면 추가하지 말고 '내용을 입력하세요'를 출력하고 종료 코드 1로 끝내 주세요.",
   plan="계획: add 가 내용의 앞뒤 공백을 지운 뒤 저장합니다. 확인: bin/test 에 ' 우유 ' 가 '우유'로 저장되는 검사를 더합니다."),
 "design-a": dict(kind="설계 오류",
   request="list 에서 완료한 할 일은 숨겨 주세요. CSV 내보내기는 정산 시스템이 읽으니 완료한 것까지 모두 내보내야 합니다.",
   plan="계획: list 는 완료하지 않은 할 일만 보여 주고, CSV 내보내기는 지금처럼 모든 할 일을 내보냅니다. 확인: list 에서 완료 항목이 빠지는지, CSV 에 모든 항목이 있는지 검사합니다."),
 "design-b": dict(kind="설계 오류",
   request="python3 todo.py edit <번호> <내용> 으로 할 일 내용을 고칠 수 있게 해 주세요. add 와 edit 모두 내용 앞뒤 공백을 지워서 저장해 주세요.",
   plan="계획: edit 명령을 새로 만들고, add·edit 모두 저장 전에 앞뒤 공백을 지웁니다. 확인: add 와 edit 각각 공백 제거를 검사합니다."),
 "test-a": dict(kind="잘못된 검사",
   request="CSV 내보내기에서 완료 여부를 True/False 대신 yes/no 로 써 주세요. 머리글 id,text,done 은 그대로 둡니다.",
   plan="계획: export 가 done 칸에 yes/no 를 씁니다. 머리글은 그대로입니다. 확인: 내보낸 CSV 를 검사합니다."),
 "test-b": dict(kind="잘못된 검사",
   request="이미 같은 내용의 할 일이 있으면 add 가 새로 추가하지 말고 '이미 있습니다'를 출력해 주세요.",
   plan="계획: add 가 같은 내용이 있으면 추가하지 않고 '이미 있습니다'를 출력합니다. 확인: 같은 내용을 두 번 add 하는 검사를 더합니다."),
 "normal-a": dict(kind="정상",
   request="list 에서 완료한 할 일은 숨겨 주세요. CSV 내보내기는 정산 시스템이 읽으니 완료한 것까지 모두 내보내야 합니다.",
   plan="계획: list 는 완료하지 않은 할 일만 보여 주고, CSV 내보내기는 지금처럼 모든 할 일을 내보냅니다. 확인: list 에서 완료 항목이 빠지는지, CSV 에 모든 항목이 있는지 검사합니다."),
 "normal-b": dict(kind="정상",
   request="CSV 내보내기에서 완료 여부를 True/False 대신 yes/no 로 써 주세요. 머리글 id,text,done 은 그대로 둡니다.",
   plan="계획: export 가 done 칸에 yes/no 를 씁니다. 머리글은 그대로입니다. 확인: 내보낸 CSV 를 검사합니다."),
}

def apply(name, p):
    todo = Path(p, "todo.py")
    if name in ("omit-a", "design-a", "normal-a"):
        hide_done_test(p)
    if name == "omit-a":   # 계획과 코드가 함께 '완료 N개' 줄을 빠뜨림
        edit(todo, [(LIST_LINE, '''        for it in [i for i in items if not i["done"]]:
            print(f"{it['id']}. [ ] {it['text']}")
    elif cmd == "archive":
        for it in [i for i in items if i["done"]]:
            print(f"{it['id']}. [x] {it['text']}")''')])
        add_test(p, '''    def test_archive(self):
        run(self.dir, "add", "우유 사기"); run(self.dir, "done", "1")
        self.assertNotIn("우유", run(self.dir, "list")); self.assertIn("우유", run(self.dir, "archive"))''')
    elif name == "omit-b":  # 빈 내용 거절을 계획·코드 모두 빠뜨림
        edit(todo, [(ADD_LINE, '''        items.append({"id": len(items) + 1, "text": args[0].strip(), "done": False})
        save(items)''')])
        add_test(p, '''    def test_add_strips(self):
        run(self.dir, "add", " 우유 ")
        self.assertIn("1. [ ] 우유", run(self.dir, "list"))''')
    elif name in ("design-a", "normal-a"):
        if name == "design-a":  # 공용 visible() 에서 걸러 export 까지 완료 항목을 잃음
            edit(todo, [('    """list 가 보여 줄 할 일. export 도 이 함수를 쓴다."""\n    return items', '    """list 가 보여 줄 할 일. export 도 이 함수를 쓴다."""\n    return [i for i in items if not i["done"]]')])
        else:
            edit(todo, [(LIST_LINE, '''        for it in [i for i in visible(items) if not i["done"]]:
            print(f"{it['id']}. [ ] {it['text']}")''')])
        add_test(p, '''    def test_list_hides_done(self):
        run(self.dir, "add", "우유 사기"); run(self.dir, "done", "1")
        self.assertNotIn("우유", run(self.dir, "list"))''' + ('''

    def test_export_all(self):
        run(self.dir, "add", "우유 사기"); run(self.dir, "add", "빵"); run(self.dir, "done", "1")
        run(self.dir, "export", "o.csv")
        self.assertIn("우유 사기", (Path(self.dir) / "o.csv").read_text(encoding="utf-8"))''' if name == "normal-a" else ""))
    elif name == "design-b":  # 공백 제거를 add 경로에만 둠(edit 는 빠짐)
        edit(todo, [(ADD_LINE, '''        items.append({"id": len(items) + 1, "text": args[0].strip(), "done": False})
        save(items)
    elif cmd == "edit":
        for it in items:
            if it["id"] == int(args[0]):
                it["text"] = args[1]
        save(items)''')])
        add_test(p, '''    def test_add_strips_and_edit(self):
        run(self.dir, "add", " 우유 "); run(self.dir, "edit", "1", "빵")
        self.assertIn("1. [ ] 빵", run(self.dir, "list"))''')
    elif name in ("test-a", "normal-b"):
        if name == "normal-b":
            edit(todo, [('w.writerow([it["id"], it["text"], it["done"]])', 'w.writerow([it["id"], it["text"], "yes" if it["done"] else "no"])')])
            body = '''    def test_export_yes_no(self):
        run(self.dir, "add", "우유 사기"); run(self.dir, "add", "빵"); run(self.dir, "done", "1")
        run(self.dir, "export", "o.csv")
        rows = list(csv.reader(open(Path(self.dir) / "o.csv", encoding="utf-8")))
        self.assertEqual(rows[0], ["id", "text", "done"]); self.assertEqual([r[2] for r in rows[1:]], ["yes", "no"])'''
        else:  # 코드는 그대로 True/False 인데 검사는 머리글만 본다(결함을 통과시킴)
            body = '''    def test_export_yes_no(self):
        run(self.dir, "add", "우유 사기"); run(self.dir, "done", "1")
        run(self.dir, "export", "o.csv")
        rows = list(csv.reader(open(Path(self.dir) / "o.csv", encoding="utf-8")))
        self.assertEqual(rows[0], ["id", "text", "done"])'''
        add_test(p, body)
    elif name == "test-b":  # 메시지만 내고 그대로 추가함, 검사는 메시지만 본다
        edit(todo, [(ADD_LINE, '''        if any(i["text"] == args[0] for i in items):
            print("이미 있습니다")
        items.append({"id": len(items) + 1, "text": args[0], "done": False})
        save(items)''')])
        add_test(p, '''    def test_duplicate_message(self):
        run(self.dir, "add", "우유 사기")
        self.assertIn("이미 있습니다", run(self.dir, "add", "우유 사기"))''')

def check(name, p):
    w = Path(tempfile.mkdtemp()) / "p"
    shutil.copytree(p, w, symlinks=True, ignore=shutil.ignore_patterns("todo.json", ".git", "work", ".claude", ".codex", ".agents"))
    run = lambda *a: subprocess.run([sys.executable, "todo.py", *a], cwd=w, capture_output=True, text=True, timeout=60)
    reset = lambda: (w / "todo.json").unlink(missing_ok=True)
    problems = []
    def csvrows():
        run("export", "o.csv"); return list(csv.reader(open(w / "o.csv", encoding="utf-8"))) if (w / "o.csv").exists() else []
    if name == "omit-a":
        run("add", "우유 사기"); run("add", "빵"); run("done", "1")
        out = run("list").stdout.strip().splitlines()
        if not out or not re.search(r"완료\s*1\s*개", out[-1]): problems.append(f"목록 맨 아래 '완료 1개' 없음: {out[-1:] }")
        if "우유" not in run("archive").stdout: problems.append("archive 에 완료 항목 없음")
        if len(csvrows()) != 3: problems.append("CSV 가 모든 할 일을 내보내지 않음")
    elif name == "omit-b":
        r = run("add", "   ")
        if r.returncode != 1 or "내용을 입력하세요" not in r.stdout + r.stderr: problems.append(f"빈 내용 거절 안 함(rc={r.returncode})")
        run("add", " 우유 ")
        if "1. [ ] 우유" not in run("list").stdout: problems.append("공백 제거·번호가 기대와 다름")
    elif name in ("design-a", "normal-a"):
        run("add", "우유 사기"); run("add", "빵"); run("done", "1")
        if "우유" in run("list").stdout: problems.append("list 에 완료 항목이 보임")
        if not any("우유 사기" in r for r in csvrows()): problems.append("CSV 에서 완료 항목이 빠짐(정산 계약)")
    elif name == "design-b":
        run("add", " 우유 ")
        if "1. [ ] 우유" not in run("list").stdout: problems.append("add 공백 제거 안 됨")
        run("edit", "1", "  빵  ")
        if "1. [ ] 빵" not in run("list").stdout or "  빵" in run("list").stdout: problems.append("edit 공백 제거 안 됨")
    elif name in ("test-a", "normal-b"):
        run("add", "우유 사기"); run("add", "빵"); run("done", "1")
        rows = csvrows()
        if not rows or rows[0] != ["id", "text", "done"] or [r[2] for r in rows[1:]] != ["yes", "no"]: problems.append(f"CSV 가 yes/no 가 아님: {rows}")
    elif name == "test-b":
        run("add", "우유 사기"); r = run("add", "우유 사기")
        if "이미 있습니다" not in r.stdout: problems.append("메시지 없음")
        if run("list").stdout.count("우유 사기") != 1: problems.append("중복이 추가됨")
    t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=w, capture_output=True, text=True, timeout=120)
    if t.returncode != 0: problems.append("저장소 검사가 실패함")
    print(("FAIL " + " / ".join(problems)) if problems else "PASS 요청한 결과가 실제로 맞다")
    return 1 if problems else 0

if __name__ == "__main__":
    cmd, name = sys.argv[1], sys.argv[2]
    if cmd == "apply": apply(name, sys.argv[3])
    elif cmd == "check": sys.exit(check(name, sys.argv[3]))
    elif cmd == "text": print(S[name][sys.argv[3]])
    elif cmd == "kind": print(S[name]["kind"])
