# 출발 상태: 회원 가입·로그인·명단 출력이 있는 계정 CLI(탈퇴 기능 없음). 명단은 users.json 에 저장한다.
mkdir -p tests
cat > accounts.py <<'PY_EOF'
"""회원 계정 CLI. 계정은 users.json 에 저장한다.

사용:
  python3 accounts.py signup <아이디> <비밀번호>   회원 가입
  python3 accounts.py login <아이디> <비밀번호>    로그인(성공하면 "환영합니다 <아이디>", 실패하면 "로그인 실패" 와 종료 코드 1)
  python3 accounts.py list                          회원 명단 출력
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


def main(argv):
    cmd, args = argv[0], argv[1:]
    users = load()
    if cmd == "signup":
        if args[0] in users:
            print("이미 있는 아이디")
            return 1
        users[args[0]] = {"pw": digest(args[1])}
        save(users)
    elif cmd == "login":
        u = users.get(args[0])
        if not u or u["pw"] != digest(args[1]):
            print("로그인 실패")
            return 1
        print(f"환영합니다 {args[0]}")
    elif cmd == "list":
        for name in sorted(users):
            print(name)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY_EOF
cat > tests/test_accounts.py <<'TEST_EOF'
import subprocess, sys, tempfile, unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "accounts.py"


def run(cwd, *args):
    return subprocess.run([sys.executable, str(APP), *args], cwd=cwd, capture_output=True, text=True)


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_signup_and_login(self):
        run(self.dir, "signup", "kim", "pw1")
        self.assertIn("환영합니다 kim", run(self.dir, "login", "kim", "pw1").stdout)

    def test_wrong_password(self):
        run(self.dir, "signup", "kim", "pw1")
        self.assertEqual(run(self.dir, "login", "kim", "bad").returncode, 1)


if __name__ == "__main__":
    unittest.main()
TEST_EOF
printf '# 계정 CLI\n\n`python3 accounts.py` 로 쓰는 회원 가입·로그인. 시험: `python3 -m unittest discover -s tests`\n' > README.md
