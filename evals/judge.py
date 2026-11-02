"""사례 판정 검사들이 함께 쓰는 판정 도구.

- asked(final, about, choice): 마지막 답이 사용자에게 선택을 묻는가. 질문 표지 + 대상(about) + 선택을 가르는 말(choice)이
  모두 있어야 한다("다른 질문이 있으신가요?" 같은 인사는 질문으로 보지 않는다). 물음표 없이 선택지를 내미는 말투도 질문으로 본다.
- changed_in_last_turn(project, names): 마지막 턴에서 바뀐 파일. run.sh 가 마지막 턴 직전 상태를
  EVALS_BEFORE_LAST_TURN 폴더에 남긴다. 변수가 없으면(직접 실행·표본 시험) 비교하지 않고 빈 목록,
  변수는 있는데 폴더가 없으면(하네스가 마지막 턴 전에 실패 등) 판정할 수 없으므로 None 을 돌려준다.
"""
import os
import re
from pathlib import Path

QUESTION = r"(\?|？|여쭙|정해 주|알려 주|골라 주|답해 주|어느 쪽|어떻게 할까|선택이 필요|정해야 합니다|원하시)"


def asked(final, about, choice):
    return bool(re.search(QUESTION, final) and re.search(about, final) and re.search(choice, final))


def changed_in_last_turn(project, names):
    before = os.environ.get("EVALS_BEFORE_LAST_TURN")
    if not before:
        return []
    if not Path(before).is_dir():
        return None
    changed = []
    for name in names:
        a, b = Path(before) / name, Path(project) / name
        if a.is_dir() or b.is_dir():
            files = {p.relative_to(a) for p in a.rglob("*") if p.is_file() and "__pycache__" not in p.parts} if a.is_dir() else set()
            files |= {p.relative_to(b) for p in b.rglob("*") if p.is_file() and "__pycache__" not in p.parts} if b.is_dir() else set()
            changed += [f"{name}/{f}" for f in sorted(files) if _read(a / f) != _read(b / f)]
        elif _read(a) != _read(b):
            changed.append(name)
    return changed


def _read(path):
    return path.read_bytes() if path.is_file() else None
