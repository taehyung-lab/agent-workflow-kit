import json
import sys
import inventory
import milling
import storage


def main(args):
    data = storage.load()
    command, *args = args
    if command == "stock" and not args:
        return data["bins"]
    if command == "accounts" and not args:
        return data["accounts"]
    if command == "list" and not args:
        return [milling.view(j) for j in data["jobs"]]
    if command == "show" and len(args) == 1:
        return milling.view(inventory.find(data["jobs"], int(args[0])))
    if command == "new" and len(args) == 3:
        result = milling.new(data, *args)
    elif command == "restock" and len(args) == 2:
        result = inventory.restock(data, *args)
    elif command in ("run", "cancel") and len(args) == 1:
        job = inventory.find(data["jobs"], int(args[0]))
        result = getattr(milling, command)(data, job)
    else:
        raise ValueError("명령 형식 오류")
    storage.save(data)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(sys.argv[1:]), ensure_ascii=False))
    except (ValueError, StopIteration, KeyError, IndexError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
