"""회원 계정 CLI. 계정은 users.json 에 저장한다.

사용:
  python3 accounts.py signup <아이디> <비밀번호>   회원 가입
  python3 accounts.py login <아이디> <비밀번호>    로그인(성공하면 "환영합니다 <아이디>", 실패하면 "로그인 실패" 와 종료 코드 1. 비활성 계정도 실패)
  python3 accounts.py list                          회원 명단 출력(비활성 계정은 빠진다)
  python3 accounts.py deactivate <아이디>           회원 탈퇴: 계정을 지우지 않고 비활성으로 바꾼다
  python3 accounts.py reactivate <아이디>           비활성 계정을 되살린다
"""
import hashlib, json, sys
from pathlib import Path

STORE = Path("users.json")


def load():
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


def save(users):
    STORE.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")


def digest(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def set_active(users, name, active):
    if name not in users:
        print("없는 아이디")
        return 1
    users[name]["active"] = active
    save(users)
    return 0


def main(argv):
    cmd, args = argv[0], argv[1:]
    users = load()
    if cmd == "signup":
        if args[0] in users:
            print("이미 있는 아이디")
            return 1
        users[args[0]] = {"pw": digest(args[1]), "active": True}
        save(users)
    elif cmd == "login":
        u = users.get(args[0])
        if not u or u["pw"] != digest(args[1]) or not u.get("active", True):
            print("로그인 실패")
            return 1
        print(f"환영합니다 {args[0]}")
    elif cmd == "list":
        for name in sorted(users):
            if users[name].get("active", True):
                print(name)
    elif cmd == "deactivate":
        return set_active(users, args[0], False)
    elif cmd == "reactivate":
        return set_active(users, args[0], True)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
