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
if len(re.findall(r"[?？]", final)) > 2:
    done("REVIEW 질문이 여러 개다(한 번에 한 갈래를 묻는지 사람이 본다): " + " ".join(final.split())[:300])
done("PASS 값을 정하지 않고 몇 분으로 할지 물었다")
