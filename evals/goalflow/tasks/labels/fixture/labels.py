"""박물관 표본 라벨 CLI. 사용법은 README.md."""
import json
import sys
import storage
import catalog
import sheets


def main(args):
    data = storage.load()
    command, *args = args
    if command == "catalog":
        result = data["specimens"]
    elif command == "specimen":
        result = catalog.find(data, args[0])
    elif command == "rename":
        result = catalog.rename(data, args[0], args[1])
        storage.save(data)
    elif command == "list":
        result = [sheets.view(data, s) for s in data["sheets"]]
    elif command == "show":
        result = sheets.view(data, sheets.find(data, int(args[0])))
    else:
        if command == "new":
            sheet = sheets.new(data)
        elif command in ("add", "remove"):
            sheet = sheets.find(data, int(args[0]))
            sheets.edit(data, sheet, command, args[1], int(args[2]))
        elif command == "seal":
            sheet = sheets.find(data, int(args[0]))
            sheets.seal(data, sheet)
        else:
            raise ValueError("알 수 없는 명령")
        result = sheets.view(data, sheet)
        storage.save(data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, IndexError, KeyError) as error:
        print("명령을 처리할 수 없습니다: " + str(error), file=sys.stderr)
        sys.exit(1)
