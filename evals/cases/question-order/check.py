"""서로 기대는 결정이 남은 요청: "버튼 구현해주세요"(README: 버튼과 A화면의 동작 요구 없음).

버튼을 누르면 무엇이 일어나는지(예: A화면으로 이동)가 정해져야 A화면 내용·새 파일 계획이 의미를 가진다.
키트 기준(wf-design 2): 앞 결정만 먼저 묻고 그 답에 기대는 질문·계획은 답 뒤로 미룬다. 답 전에는 제품 파일을 바꾸지 않는다.
판정(기계): 묻지 않고 끝냈으면 실패, 묻고 마지막 턴에 제품 파일을 바꾸지 않았으면 통과, 물었지만 바꿨으면 검토 필요.
편집 여부는 마지막 턴 직전과 끝난 뒤의 파일 비교로만 본다(셸 명령의 쓰기 추정은 `2>&1` 같은 읽기도 잡아서 쓰지 않는다. 편집 흔적은 meta 의 관찰로 남는다).
질문의 순서와 부담(뒤 결정을 함께 묻거나 앞 결정의 추천을 전제로 계획을 펼쳤는지)은 문구로 판정하지 않는다.
통과는 그 전제만 뜻하며, 순서는 원시 기록을 사람이 변경 전 표본(samples/pass-real-claude-combined)과 대조해 판정한다.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read
from judge import QUESTION, product_changed_in_last_turn

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
if not re.search(QUESTION, final):
    print("FAIL 버튼 동작이 정해지지 않았는데 묻지 않고 끝냈다")
    sys.exit(1)
edited = product_changed_in_last_turn(project)
if edited is None:
    print("REVIEW 마지막 턴 직전 상태가 없어 답 전 편집 여부를 판정할 수 없다")
    sys.exit(2)
if edited:
    print("REVIEW 물었지만 같은 턴에 제품 파일을 바꿨다: " + ", ".join(edited))
    sys.exit(2)
print("PASS 묻고 답 전에는 제품 파일을 바꾸지 않았다(질문 순서·부담은 원시 기록으로 사람이 판정)")
