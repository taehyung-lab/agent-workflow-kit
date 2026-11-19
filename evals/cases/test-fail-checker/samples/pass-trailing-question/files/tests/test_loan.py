import json, subprocess, sys, unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "loan.py"


def borrow(book, day):
    out = subprocess.run([sys.executable, str(APP), "borrow", book, day], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def due_of(book, day):
    """대출 결과에서 반납 기한만 꺼낸다."""
    return borrow(book, day)["due"]


class LoanTest(unittest.TestCase):
    def test_due_is_fourteen_days_later(self):
        self.assertEqual(due_of("B-101", "2026-03-01"), "2026-03-15")


if __name__ == "__main__":
    unittest.main()
