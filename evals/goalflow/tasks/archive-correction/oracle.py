"""할 일 보관함(정정 뒤) 과제의 외부 판정. 정책과 판정 항목이 archive-ambiguity 와 같아 그 판정기를 그대로 실행한다.

  python3 -I evals/goalflow/tasks/archive-correction/oracle.py <프로젝트>

다른 점은 시작 프로젝트와 대화뿐이다: 시작 목록은 완료 항목도 [x] 로 보이고, 첫 요청("완료한 할 일은 목록에서 안 보이게")이
목록에 안 끝난 항목만 보이도록 정한다(given). 두 번째 사용자 글(followup.txt)이 보관함으로 옮기라는 뜻이었다고 정정한다.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "archive-ambiguity" / "oracle.py"), run_name="__main__")
