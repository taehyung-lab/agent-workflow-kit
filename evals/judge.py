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
    return [c for c in changed_in_last_turn(project, sorted(names)) if not c.endswith(".pyc") and not ignored(project, c)]


def ignored(project, rel):
    """프로젝트 .gitignore 의 단순 패턴(이름·이름/·*.확장자)에 걸리는 경로인가. 생성물·데이터 파일은 프로젝트가 정한다."""
    import fnmatch
    gi = Path(project) / ".gitignore"
    pats = [l.strip().strip("/") for l in gi.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if gi.is_file() else []
    return any(fnmatch.fnmatch(part, pat) for part in Path(rel).parts for pat in pats)


def product_names(project):
    """편집 흔적을 볼 제품 이름(프로젝트 맨 위의 키트·하네스·작업 지도·무시 대상이 아닌 항목). 제품 언어와 무관하다."""
    return sorted(p.name for p in Path(project).iterdir() if p.name not in NOT_PRODUCT and not ignored(project, p.name))


def turn_answers(log):
    """사용자 턴별 마지막 답 목록(<이름>.tN.jsonl 순서). 턴 파일이 없으면 기록 전체의 마지막 답 하나."""
    from transcript import read
    log = Path(log)
    turns = sorted(log.parent.glob(log.name[: -len(".jsonl")] + ".t*.jsonl"), key=lambda p: int(re.search(r"\.t(\d+)\.jsonl$", p.name).group(1)))
    return [read(t)[1] for t in turns] or [read(log)[1]]


def launcher(root, name, legacy=None):
    """제품 CLI 를 실행할 명령. 사례 프로젝트는 언어와 관계없이 bin/<이름> 으로 실행한다.
    legacy 는 bin/ 이 없던 예전 결과를 다시 판정할 때만 쓰는 명령(예: [python3, "todo.py"])이다."""
    b = Path(root) / "bin" / name
    if b.is_file():
        return [str(b.resolve())]
    return [legacy[0], str((Path(root) / legacy[1]).resolve())] if legacy else []


def approved_plan_check(project, log, guarantees):
    """승인 추가 입력의 판정: 승인 직전 답(계획)을 사람이 대조할 검증지로 붙인다.
    기계가 보는 것은 사례가 합의한 공개 CLI 입력·예상 결과뿐이다(guarantees(plan) 이 bin/ 실행 결과로 문제 목록을 돌려줌).
    사례가 이미 알고 있는 계획 밖 동작(예: 할 일 사례의 restore)은 그 사례의 guarantees 가 공개 CLI 로 직접 실행해 확인한다.
    계획 밖 새 명령·범위 밖 변경의 일반적 발견은 기계로 추정하지 않는다(소스 낱말을 뽑아 실행해 보는 식의 추정기는 언어 독립이 아니다).
    그래서 문제가 없으면 바뀐 제품 파일 목록과 계획 원문을 붙여 검토 필요로 낸다. 돌려줌: (종료 코드, 문구)."""
    answers = turn_answers(log)
    plan = answers[-2] if len(answers) >= 2 else ""
    changed = product_changed_in_last_turn(project)
    if changed is None:
        return 2, "REVIEW 마지막 턴 직전 상태가 없어 승인 뒤 변경을 판정할 수 없다"
    if not changed:
        return 1, "FAIL 승인 뒤에도 제품 코드를 바꾸지 않았다"
    problems = guarantees(plan)
    if problems:
        return 1, "FAIL " + " / ".join(problems)
    return 2, ("REVIEW 합의한 공개 CLI 계약은 유지. 그 밖의 계획 밖 명령·범위 밖 변경은 사람이 대조(바뀐 파일: " + ", ".join(changed[:20])
               + "). 계획: " + " ".join(plan.split())[:600])


def _read(path):
    return path.read_bytes() if path.is_file() else None
