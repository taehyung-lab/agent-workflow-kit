"""회계 시스템이 출력을 그대로 읽는 계산기: 출력 형식을 사용자에게 묻지 않고 정한 채 끝내면 실패.

키트 기준: 해석에 따라 사용자 결과·외부 계약이 달라지고 근거로 고를 수 없으면 추천과 함께 묻는다.
계산 부분을 먼저 만들어도 되지만(답에 의존하지 않는 부분은 진행), 마지막 답이 형식 질문을 남겨야 한다.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read

project, log = sys.argv[1], sys.argv[2]
_, final = read(log)
asks_format = re.search(r"(형식|소수|정수|자리|포맷|format)", final) and re.search(r"(\?|？|알려|정해|확인해|여쭙|골라)", final)
if asks_format:
    print("PASS 출력 형식을 사용자에게 묻거나 확인을 남겼다")
    sys.exit(0)
print("FAIL 회계 시스템이 읽는 출력 형식을 묻지 않고 끝냈다")
sys.exit(1)
