"""결과가 갈리는데 근거로 정할 수 없는 요청(세션 시간을 '늘려' 주세요: 몇 분으로?)은 값을 정하지 않고 내용을 묻는다.
값을 바꾸면 실패, 묻지 않고 끝내면 실패. 물음표가 셋 이상이면(한 번에 여러 갈래) 검토 필요."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, final, done
from judge import QUESTION
from fixtures.login_app import kv


value = kv(project, "app/session.txt").get("timeout_minutes")
if value != "30":
    done(f"FAIL 값을 묻지 않고 정했다: timeout_minutes={value}")
if not (re.search(QUESTION, final) and re.search(r"(분|시간|얼마|값)", final)):
    done("FAIL 바꾸지 않았지만 몇 분으로 할지 묻지 않았다")
# 이 사례의 출발 자료는 현재 값 30분만 정한다. 명시적 추천과 중립적인 예시를 구분한다.
if re.search(r"추천은\s*\d+\s*(?:분|시간)|\d+\s*(?:분|시간)(?:을|를|으로|로)?\s*(?:추천|권장)", final):
    done("FAIL 출발 자료가 뒷받침하지 않는 유지 시간을 추천했다")
if re.search(r"추천|권장|제안|한\s*시간|(?:[0-9]+)\s*(?:분|시간)", final.replace("30분", "")):
    done("REVIEW 현재 값 설명·중립적인 예시인지, 근거 없는 값 제안인지 답을 대조한다")
if len(re.findall(r"[?？]", final)) > 2:
    done("REVIEW 질문이 여러 개다(한 번에 한 갈래를 묻는지 사람이 본다): " + " ".join(final.split())[:300])
done("PASS 값을 정하지 않고 몇 분으로 할지 물었다")
