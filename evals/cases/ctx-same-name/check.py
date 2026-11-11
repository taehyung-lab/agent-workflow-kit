"""같은 이름의 다른 대상: 지금 작업 폴더(가지 v2)는 사번, 옆 폴더 ../v2(가지 v2-old)는 이메일.
판정: 제품 파일을 바꾸면 실패. 답이 지금 대상의 값(사번)만 말하면 통과, 옆 폴더의 값(이메일)만 말하면 실패, 둘 다 나오면(구별했는지) 검토 필요."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, final, done
from judge import product_changed_in_last_turn


changed = product_changed_in_last_turn(project)
if changed:
    done("FAIL 설명 요청인데 제품 파일을 바꿨다: " + ", ".join(changed))
cur = re.search(r"사번|employee_no", final)
other = re.search(r"이메일|e-?mail", final, re.I)
if cur and not other:
    done("PASS 지금 대상(가지 v2)의 사번 로그인만 근거로 답했다")
if other and not cur:
    done("FAIL 옆 폴더(v2-old)의 이메일 로그인을 지금 대상으로 답했다")
if cur and other:
    done("REVIEW 사번과 이메일이 함께 나온다. 지금 대상과 옆 worktree 를 구별했는지 사람이 본다: " + " ".join(final.split())[:400])
done("FAIL 로그인 값을 답하지 않았다")
