import json, subprocess, sys, unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "loan.py"


def borrow(book, day):
    out = subprocess.run([sys.executable, str(APP), "borrow", book, day], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class LoanTest(unittest.TestCase):
    def test_due_is_fourteen_days_later(self):
        self.assertIn("due", borrow("B-101", "2026-03-01"))


if __name__ == "__main__":
    unittest.main()
