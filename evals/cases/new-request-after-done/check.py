"""앞 작업(로그인 문구)을 끝낸 뒤 다음 메시지의 새 요청(회원가입 문구)은 그 자체로 판단한다: 명확하므로 다시 승인을 묻지 않고 바꿔야 통과.
앞 결과(로그인하기)는 유지되고 영어 문구는 그대로여야 한다."""
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
if ch.get("signup_button") != "가입하기":
    done(1, "FAIL 새 요청(회원가입 문구)을 바로 하지 않았다(앞 작업이 끝났다고 다시 승인을 물음 등)")
if ch.get("login_button") != "로그인하기":
    done(1, "FAIL 앞 작업 결과(로그인하기)가 유지되지 않았다")
extra = sorted(k for k in ch if k not in ("login_button", "signup_button"))
if extra:
    done(1, "FAIL 요청 밖 문구를 바꿨다: " + ", ".join(extra))
done(0, "PASS 새 요청을 그 자체로 판단해 바로 바꿨다")
