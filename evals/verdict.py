"""평가 결과의 판정과 검토 출력 해석. 모델을 실행하지 않는다.

완료 규칙은 설치 검토 도구의 함수를 그대로 사용한다. 검토 세션 실행은
session.py review가 같은 공개 prepare/finish 명령으로 담당한다.
"""
import importlib.util, json, re
from pathlib import Path

_spec = importlib.util.spec_from_file_location("awk_verify", Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify/verify.py")
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)
last_json, judge, completion, ids, EXIT = _verify.last_json, _verify.judge, _verify.completion, _verify.ids, _verify.EXIT
REVIEW_OFF = "recorded"  # record(요구 기록 검사)의 형식 통과 상태. 검토 결과가 아니다


TAIL = re.compile(r"^\s*(exit(=| code:? ?)\d+|[ MADRCU?!]{1,2} \S.*)\s*$")  # 종료 코드 echo 줄, git status --short 줄


def run_result(output, exit_code=None):
    """세션이 실행한 명령의 출력에서 검토 도구가 찍는 결과를 찾는다. 도구의 출력은 표준 오류의 `[verify] ` 줄과, 맨 끝 한 줄의 결과 JSON
    (state 가 판정 상태이고 completion 이 있음)뿐이고, 종료 코드는 도구의 exit_code(결과) 값이다: state 가 주는 0 이 아닌 코드,
    아니면 completion 이 verified 일 때만 0 이고 그 밖은 6. 종료 코드가 state 만 따르던 때(v3.6 이하)의 기록은 그때의 값(ok 는 completion 과 무관하게 0)도 받는다.
    저장된 result.json도 같은 형식이므로, 실제 명령 실행인지의 구분은 호출 기록을 가진 평가 관찰(observe.py)이 맡는다.
    돌려줌: (결과 객체 또는 None, 이번 실행의 결과로 볼 수 없는 사유 또는 ""). 다른 글이 섞였거나(예: 스크립트와 저장해 둔 출력을 함께 cat)
    종료 코드가 결과의 state 와 맞지 않으면 그 결과를 이번 실행의 판정으로 쓰지 않는다."""
    lines = [l for l in str(output or "").splitlines() if l.strip()]
    # 같은 명령 줄에 이어 붙인 확인 출력은 도구의 출력이 아니지만 이번 실행의 꼬리다: `; echo exit=$?` 의 종료 코드 줄과 `git status --short` 의 줄.
    # 이것 때문에 통과한 검토가 "알 수 없음"이 되어 사람이 원시 기록을 읽어야 했다(2026-11-12~13, 세 번). 결과 JSON 앞의 줄은 여전히 `[verify] ` 뿐이어야 한다.
    while lines and TAIL.match(lines[-1]):
        m = re.match(r"^exit(?:=| code:? ?)(\d+)$", lines[-1].strip())
        if m and exit_code in (None, 0):
            exit_code = int(m.group(1))  # 이어 붙인 echo 가 알려 준 도구의 종료 코드(명령 줄 전체의 종료 코드는 마지막 명령의 것이다)
        lines.pop()
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("state") in EXIT and "completion" in obj:
            if i != len(lines) - 1 or not all(l.startswith("[verify] ") for l in lines[:i]):
                return obj, "실행기 결과 JSON 이 다른 출력과 섞여 있어 이번 실행의 결과인지 저장된 결과를 읽은 것인지 가를 수 없다"
            if exit_code is not None and exit_code not in (_verify.exit_code(obj), EXIT[obj["state"]]):
                return obj, f"결과 state {obj['state']} 와 종료 코드 {exit_code} 가 맞지 않는다"
            return obj, ""
    return None, ""
