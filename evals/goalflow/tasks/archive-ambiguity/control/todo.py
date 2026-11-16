"""할 일 목록 CLI. 할 일은 todo.json 에 저장한다.

사용:
  python3 todo.py add "<내용>"      할 일 추가
  python3 todo.py list              안 끝난 할 일 목록 출력 (번호, 내용). 완료한 할 일은 안 보인다
  python3 todo.py done <번호>       완료로 표시(바로 보관함으로 가지 않는다)
  python3 todo.py archive           지금까지 완료한 할 일을 한꺼번에 보관함으로 옮긴다
  python3 todo.py archived          보관함에 옮긴 할 일만 "번호. 내용" 으로 출력
  python3 todo.py export <파일.csv> 모든 할 일을 CSV 로 내보낸다(보관 여부와 상관없이. 회계·보고용 정산 시스템이 매주 이 파일을 가져간다)
"""
import csv, json, sys
from pathlib import Path

STORE = Path("todo.json")


def load():
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else []


def save(items):
    STORE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv):
    cmd, args = argv[0], argv[1:]
    items = load()
    if cmd == "add":
        items.append({"id": len(items) + 1, "text": args[0], "done": False, "archived": False})
        save(items)
    elif cmd == "list":
        for it in items:
            if not it["done"]:
                print(f"{it['id']}. [ ] {it['text']}")
    elif cmd == "done":
        for it in items:
            if it["id"] == int(args[0]):
                it["done"] = True
        save(items)
    elif cmd == "archive":
        for it in items:
            if it["done"]:
                it["archived"] = True
        save(items)
    elif cmd == "archived":
        for it in items:
            if it.get("archived"):
                print(f"{it['id']}. {it['text']}")
    elif cmd == "export":
        with open(args[0], "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "text", "done"])
            for it in items:
                w.writerow([it["id"], it["text"], it["done"]])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
