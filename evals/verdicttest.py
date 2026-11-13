"""검토 도구의 결과를 세션 기록에서 읽는 규칙(verdict.run_result) 시험. 모델을 부르지 않는다.

  python3 -I evals/verdicttest.py

같은 명령 줄에 이어 붙인 꼬리 출력(`; echo exit=$?`, `git status --short`)이 있어도 이번 실행의 결과로 읽고,
결과 앞에 다른 글이 섞였거나 종료 코드가 결과와 다르면 이번 실행의 판정으로 쓰지 않는지 본다.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verdict  # noqa: E402

OK = json.dumps({"round": 1, "state": "ok", "reason": "", "direct_check": "PASS", "completion": "verified"})
HEAD = "[verify] 검토 통과: 독립 검토가 모든 조건 충족을 냈다.\n"


def clean(output, rc):
    obj, doubt = verdict.run_result(output, rc)
    return obj is not None and doubt == ""


def doubted(output, rc, word):
    obj, doubt = verdict.run_result(output, rc)
    return obj is not None and word in doubt


checks = [
    ("꼬리 출력이 없으면 이번 실행의 결과로 읽는다", clean(HEAD + OK, 0)),
    ("`; echo exit=$?` 와 `git status --short` 꼬리가 붙어도 이번 실행의 결과로 읽는다", clean(HEAD + OK + "\nexit=0\n M tests/test_todo.py\n M todo.py\n?? notes.txt", 0)),
    ("결과 앞에 다른 글이 섞이면 이번 실행의 판정으로 쓰지 않는다", doubted("저장해 둔 결과:\n" + OK + "\nexit=0", 0, "섞여")),
    ("이어 붙인 echo 가 알려 준 종료 코드가 결과와 다르면 쓰지 않는다", doubted(HEAD + OK + "\nexit=3", 0, "맞지 않는다")),
    ("꼬리처럼 보이지 않는 글이 뒤에 붙으면 쓰지 않는다", doubted(HEAD + OK + "\n검토를 통과했습니다", 0, "섞여")),
    ("결과가 없으면 None", verdict.run_result("exit=0\n M todo.py", 0)[0] is None),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
