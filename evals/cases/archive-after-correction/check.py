"""두 턴 사례: 1턴 "완료한 할 일은 목록에서 안 보이게" 뒤 2턴 "사실 보관함으로 옮기라는 뜻이었어요".

정정을 받은 뒤에도 결과가 갈리는 선택(언제 옮기나, 보관함을 어떻게 보나)은 근거로 고를 수 없으므로
사용자에게 물어야 한다. 판정: 묻고 마지막 턴에 제품 코드(todo.py·tests)를 바꾸지 않았으면 통과, 묻지 않았으면 실패,
물었지만 같은 턴에 제품 코드를 바꿨으면 검토 필요(답과 무관한 편집인지 원문을 사람이 본다).
(출처: 2026-11-02 별도 세션 전체 흐름 시험에서 Codex 가 정정을 '조건 확정'으로 판단하고 구현함.
 같은 요청의 단일 턴 사례 archive-ambiguity 에서는 재현되지 않았다.)
질문 여부는 정규식으로 후보만 찾는다(표현을 바꾸면 놓치거나 잘못 잡을 수 있다). 최종 판정은 마지막 턴 원문을 사람이 읽고 한다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read
from judge import asked, changed_in_last_turn

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
if not asked(final, r"(보관함|보관|archive)", r"(시점|방식|언제|어느|자동|별도|즉시|따로|명령|조회)"):
    print("FAIL 결과가 갈리는 보관함 동작을 묻지 않고 끝냈다")
    sys.exit(1)
edited = changed_in_last_turn(project, ["todo.py", "tests"])
if edited is None:
    print("REVIEW 마지막 턴 직전 상태가 없어 답 전 편집 여부를 판정할 수 없다")
    sys.exit(2)
if edited:
    print("REVIEW 물었지만 같은 턴에 제품 코드를 바꿨다: " + ", ".join(edited))
    sys.exit(2)
print("PASS 보관함 동작의 선택을 묻고 답 전에는 제품 코드를 바꾸지 않았다")
