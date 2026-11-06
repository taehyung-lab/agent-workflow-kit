import argparse
import json

import client
import service


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["confirm", "status", "submit", "recover"])
    p.add_argument("--db", required=True)
    p.add_argument("--request", required=True)
    p.add_argument("--member", required=True)
    p.add_argument("--workshop", default="morning")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--lose-response", action="store_true")
    a = p.parse_args()
    service.init(a.db)
    if a.action == "confirm":
        result = service.confirm(a.db, a.request, a.member, a.workshop)
    elif a.action == "status":
        result = service.status(a.db, a.request, a.member)
    elif a.action == "recover":
        result = client.recover(a.db, a.request, a.member)
    else:
        result = client.submit(a.db, a.request, a.member, a.workshop, online=not a.offline, lose_response=a.lose_response)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
