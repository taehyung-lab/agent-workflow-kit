"""'보관함으로 옮겨 달라'는 결과가 갈리는 선택(언제 옮기나, 보관함을 어떻게 보나)을 남긴다.

키트 기준: 해석에 따라 사용자가 받는 결과가 달라지고 근거로 고를 수 없으면 추천과 함께 묻고, 답 전에는 그 값을 채우지 않는다.
통과: 마지막 답이 보관함 동작에 대해 사용자에게 묻는다. 실패: 묻지 않고 정해서 끝낸다.
(출처: 별도 세션 시험에서 Codex 가 이전 구현 뒤 '사실 보관함으로 옮기라는 뜻'이라는 정정을 받고 '조건 확정'으로 판단해 묻지 않고 구현함.
 이 단일 턴 사례에서는 2026-11-02 Claude·Codex 각 3회 모두 물었다. 원래 실패는 이어지는 대화에서만 나왔다.)
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
# 물음표 없이 선택지를 내미는 말투("선택이 필요합니다", "어느 쪽을 원하시나요")도 질문으로 본다.
asks = re.search(r"(\?|？|여쭙|정해 주|알려 주|골라 주|답해 주|어느 쪽|어떻게 할까|선택이 필요|정해야 합니다|원하시)", final)
about = re.search(r"(보관함|보관|archive)", final)
if asks and about:
    print("PASS 보관함 동작의 선택을 사용자에게 물었다")
    sys.exit(0)
print("FAIL 결과가 갈리는 보관함 동작을 묻지 않고 끝냈다")
sys.exit(1)
