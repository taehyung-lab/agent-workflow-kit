"""도서 대출 CLI.

사용:
  python3 loan.py borrow <도서번호> <대출일 YYYY-MM-DD>   대출 기록을 JSON 한 줄로 출력한다
"""
import json, sys
from datetime import date, timedelta

LOAN_DAYS = 14


def main(argv):
    if len(argv) != 3 or argv[0] != "borrow":
        print(__doc__)
        return 1
    book, start = argv[1], date.fromisoformat(argv[2])
    due = start + timedelta(days=LOAN_DAYS)
    print(json.dumps({"book": book, "due": due.isoformat()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
