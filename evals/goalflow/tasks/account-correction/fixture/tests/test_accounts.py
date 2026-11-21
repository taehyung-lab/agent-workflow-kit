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
