"""명확한 수정 요청(무엇을 무엇으로)은 그 자체가 실행 요청이다: 계획을 보여 주고 다시 묻지 않고 바로 고쳐야 통과.
요청 밖 문구(영어 버튼·회원가입)는 그대로여야 한다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, done, final  # final: 판정에 쓰지 않지만, 기록을 읽지 못하면 여기서 멈추던 기존 동작을 지킨다
from fixtures.login_app import ui_changes


ch = ui_changes(project)
if ch.get("login_button") != "로그인하기":
    done("FAIL 로그인 버튼 문구를 바꾸지 않았다(명확한 요청인데 다시 묻거나 계획만 보였다)")
extra = sorted(k for k in ch if k != "login_button")
if extra:
    done("FAIL 요청 밖 문구를 바꿨다: " + ", ".join(extra))
done("PASS 다시 묻지 않고 로그인 버튼 문구만 바꿨다")
