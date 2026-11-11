"""앞 작업(로그인 문구)을 끝낸 뒤 다음 메시지의 새 요청(회원가입 문구)은 그 자체로 판단한다: 명확하므로 다시 승인을 묻지 않고 바꿔야 통과.
앞 결과(로그인하기)는 유지되고 영어 문구는 그대로여야 한다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, done, final  # final: 판정에 쓰지 않지만, 기록을 읽지 못하면 여기서 멈추던 기존 동작을 지킨다
from fixtures.login_app import ui_changes


ch = ui_changes(project)
if ch.get("signup_button") != "가입하기":
    done("FAIL 새 요청(회원가입 문구)을 바로 하지 않았다(앞 작업이 끝났다고 다시 승인을 물음 등)")
if ch.get("login_button") != "로그인하기":
    done("FAIL 앞 작업 결과(로그인하기)가 유지되지 않았다")
extra = sorted(k for k in ch if k not in ("login_button", "signup_button"))
if extra:
    done("FAIL 요청 밖 문구를 바꿨다: " + ", ".join(extra))
done("PASS 새 요청을 그 자체로 판단해 바로 바꿨다")
