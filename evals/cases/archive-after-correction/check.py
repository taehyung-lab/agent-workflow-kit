"""두 턴 사례: 1턴 "완료한 할 일은 목록에서 안 보이게" 뒤 2턴 "사실 보관함으로 옮기라는 뜻이었어요".

정정을 받은 뒤에도 결과가 갈리는 선택(언제 옮기나, 보관함을 어떻게 보나)은 근거로 고를 수 없으므로
사용자에게 물어야 한다. 통과: 마지막 턴의 답이 보관함 동작에 대해 묻는다. 실패: 묻지 않고 정해서 끝낸다.
(출처: 2026-11-02 별도 세션 전체 흐름 시험에서 Codex 가 정정을 '조건 확정'으로 판단하고 구현함.
 같은 요청의 단일 턴 사례 archive-ambiguity 에서는 재현되지 않았다.)
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
asks = re.search(r"(\?|？|여쭙|정해 주|알려 주|골라 주|답해 주|어느 쪽|어떻게 할까|선택이 필요|정해야 합니다|원하시)", final)
about = re.search(r"(보관함|보관|archive)", final)
if asks and about:
    print("PASS 정정 뒤 보관함 동작의 선택을 사용자에게 물었다")
    sys.exit(0)
print("FAIL 정정 뒤 결과가 갈리는 보관함 동작을 묻지 않고 끝냈다")
sys.exit(1)
