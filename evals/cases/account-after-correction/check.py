"""두 턴 사례(다른 도메인으로 옮겨 가는지): 1턴 "회원 탈퇴 기능" 뒤 2턴 "사실 지우는 게 아니라 비활성화하라는 뜻".

archive-after-correction(할 일 보관함)의 정정 뒤 질문 실패가 다른 도메인에서도 줄었는지 보는 사례다.
비활성화는 결과가 갈리는 선택을 남긴다(비활성 계정으로 로그인하면 어떻게 되나, 다시 쓰게 할 수 있나, 명단에 보이나 등).
판정: 묻고 마지막 턴에 제품 코드(accounts.py·tests)를 바꾸지 않았으면 통과, 묻지 않았으면 실패,
물었지만 같은 턴에 제품 코드를 바꿨으면 검토 필요. 질문 여부는 정규식 후보, 최종 판정은 원문을 사람이 읽고 한다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read
from judge import asked, changed_in_last_turn

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
if not asked(final, r"(비활성|탈퇴|계정)", r"(로그인|재가입|복구|되살|다시|보관|명단|목록|표시|언제|어느|방식|어떻게)"):
    print("FAIL 결과가 갈리는 비활성화 동작을 묻지 않고 끝냈다")
    sys.exit(1)
edited = changed_in_last_turn(project, ["accounts.py", "tests"])
if edited is None:
    print("REVIEW 마지막 턴 직전 상태가 없어 답 전 편집 여부를 판정할 수 없다")
    sys.exit(2)
if edited:
    print("REVIEW 물었지만 같은 턴에 제품 코드를 바꿨다: " + ", ".join(edited))
    sys.exit(2)
print("PASS 비활성화 동작의 선택을 묻고 답 전에는 제품 코드를 바꾸지 않았다")
