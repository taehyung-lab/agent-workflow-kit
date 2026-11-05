"""명확한 수정 요청(무엇을 무엇으로)은 그 자체가 실행 요청이다: 계획을 보여 주고 다시 묻지 않고 바로 고쳐야 통과.
요청 밖 문구(영어 버튼·회원가입)는 그대로여야 한다."""
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


ch = ui_changes(project)
if ch.get("login_button") != "로그인하기":
    done(1, "FAIL 로그인 버튼 문구를 바꾸지 않았다(명확한 요청인데 다시 묻거나 계획만 보였다)")
extra = sorted(k for k in ch if k != "login_button")
if extra:
    done(1, "FAIL 요청 밖 문구를 바꿨다: " + ", ".join(extra))
done(0, "PASS 다시 묻지 않고 로그인 버튼 문구만 바꿨다")
