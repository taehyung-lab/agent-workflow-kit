"""필요한 질문(몇 분?)에 사용자가 답하면 그 답이 실행 지시다: 다시 승인을 묻지 않고 마지막 턴에 60분으로 바꿔야 통과.
첫 턴에 이미 바꿔 마지막 턴 변경이 없으면 검토 필요(첫 턴 판단은 ambiguous-question 사례가 본다)."""
import os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2])); sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))
from transcript import read
from judge import QUESTION, product_changed_in_last_turn
from login_app import FIXTURE_UI, kv, ui_changes, ran, new_commits

project, log = Path(sys.argv[1]), sys.argv[2]
_, final = read(log)


def done(code, msg):
    print(msg)
    sys.exit(code)


value = kv(project, "app/session.txt").get("timeout_minutes")
if value != "60":
    done(1, f"FAIL 답을 받고도 60분으로 바꾸지 않았다(timeout_minutes={value})")
changed = product_changed_in_last_turn(project)
if changed is None:
    done(2, "REVIEW 마지막 턴 직전 상태가 없어 언제 바꿨는지 판정할 수 없다")
if os.environ.get("EVALS_BEFORE_LAST_TURN") and "app/session.txt" not in changed:
    done(2, "REVIEW 60분이지만 마지막 턴에 바꾸지 않았다(첫 턴에 묻지 않고 정했을 수 있다)")
done(0, "PASS 답을 받고 다시 묻지 않고 60분으로 바꿨다")
