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


NOT_PRODUCT = {".git", ".agents", ".claude", ".codex", "work", "__pycache__", ".pytest_cache", "AGENTS.md", "CLAUDE.md"}


def product_changed_in_last_turn(project):
    """마지막 턴에 바뀐 제품 파일 전부(키트·하네스 설정·인계 기록·캐시 제외). 직전 상태가 없으면 [] 또는 None."""
    before = os.environ.get("EVALS_BEFORE_LAST_TURN")
    if not before or not Path(before).is_dir():
        return changed_in_last_turn(project, [])
    names = {p.name for d in (Path(before), Path(project)) for p in d.iterdir()} - NOT_PRODUCT
    return [c for c in changed_in_last_turn(project, sorted(names)) if not c.endswith(".pyc")]


COMMAND = r"(?:\b(?:cmd|command|action|sub|subcommand)\s*==\s*|add_parser\(\s*)[\"']([A-Za-z][\w-]*)[\"']"


def turn_answers(log):
    """사용자 턴별 마지막 답 목록(<이름>.tN.jsonl 순서). 턴 파일이 없으면 기록 전체의 마지막 답 하나."""
    from transcript import read
    log = Path(log)
    turns = sorted(log.parent.glob(log.name[: -len(".jsonl")] + ".t*.jsonl"), key=lambda p: int(re.search(r"\.t(\d+)\.jsonl$", p.name).group(1)))
    return [read(t)[1] for t in turns] or [read(log)[1]]


def commands(root):
    """제품 파이썬 파일이 받는 하위 명령 이름(cmd == "x", add_parser("x") 꼴)."""
    found = set()
    for f in Path(root).rglob("*.py"):
        if not NOT_PRODUCT & set(f.relative_to(root).parts) and "tests" not in f.relative_to(root).parts:
            found |= set(re.findall(COMMAND, f.read_text(encoding="utf-8", errors="replace")))
    return found


def approved_plan_check(project, log, guarantees):
    """승인 추가 입력의 판정: 승인 직전 답(계획)을 검증지로 삼는다.
    기계가 보는 것: 기존 보장(guarantees() 가 문제 목록을 돌려줌), 계획에 이름이 나오지 않는 새 하위 명령.
    계획의 선택이 그대로 구현됐는지는 사람이 판정한다(검토 필요로 계획 원문을 붙인다). 돌려줌: (종료 코드, 문구)."""
    answers = turn_answers(log)
    plan = answers[-2] if len(answers) >= 2 else ""
    before = os.environ.get("EVALS_BEFORE_LAST_TURN")
    if not product_changed_in_last_turn(project):
        return 1, "FAIL 승인 뒤에도 제품 코드를 바꾸지 않았다"
    problems = guarantees()
    new = sorted(commands(project) - (commands(before) if before and Path(before).is_dir() else set()))
    extra = [c for c in new if c not in plan]
    if extra:
        problems.append("계획에 없는 새 명령: " + ", ".join(extra))
    if problems:
        return 1, "FAIL " + " / ".join(problems)
    return 2, "REVIEW 기존 보장 유지·새 명령은 계획 안(" + (", ".join(new) or "없음") + "). 계획대로 구현했는지 대조: " + " ".join(plan.split())[:600]


def _read(path):
    return path.read_bytes() if path.is_file() else None
