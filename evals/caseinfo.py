"""평가 사례의 위치와 판정기 지문을 한 곳에서 정한다. 실행기(run.py)와 재판정(rejudge.py)이 같이 쓴다.

사례 위치: evals/cases/<이름> 이 있으면 그것, 없으면 evals/holdout/<이름>.
holdout 에는 기계 판정이 PASS 를 내지 않아 selftest.sh 의 표본 확인(통과 표본 필수)에 넣을 수 없는 사례만 둔다(지금은 goal-context 하나. 숨긴 사례가 아니다).
판정기 지문(judge_version): 판정 결과를 바꿀 수 있는 파일(사례의 check.py 와 JUDGE_FILES)의 경로와 내용으로 만든 12자리 값.
같은 코드면 실행·재판정이 같은 값을 내고, 그중 하나라도 바뀌면 값이 바뀐다.
파일이 하나라도 없으면 지문을 만들지 않고 실패한다(빠진 파일을 뺀 지문은 다른 판정기를 같은 판정기로 보이게 한다).

사용:
  python3 -I evals/caseinfo.py path <사례 이름>        → 사례 폴더(없어도 holdout 경로를 낸다. 존재 확인은 부르는 쪽 몫)
  python3 -I evals/caseinfo.py version <사례 폴더>     → 판정기 지문. 파일이 빠졌으면 종료 1, 빠진 파일을 stderr 로
"""
import hashlib, json, sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
KIT = EVALS.parent
# 모든 사례의 check.py 가 기대는 공용 판정 코드. 판정에 쓰는 파일을 새로 만들면 여기에 넣는다.
JUDGE_FILES = ("evals/case.py", "evals/judge.py", "evals/observe.py", "evals/transcript.py", "evals/verdict.py", "evals/session.py", "evals/budget.py", "evals/run.py", "evals/result.py",
               "evals/fixtures/login_app.py", ".agents/skills/wf-verify/verify.py")


class MissingJudgeFile(Exception):
    pass


def case_path(name):
    cases = EVALS / "cases" / name
    return cases if cases.is_dir() else EVALS / "holdout" / name


def judge_files(case_dir):
    return [Path(case_dir).resolve() / "check.py"] + [KIT / rel for rel in JUDGE_FILES]


def judge_version(case_dir):
    files = judge_files(case_dir)
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        raise MissingJudgeFile("판정기 파일이 없다: " + ", ".join(missing))
    h = hashlib.sha256()
    for f in files:
        try:
            rel = f.relative_to(KIT).as_posix()
        except ValueError:  # 키트 밖 사례 폴더(시험용)는 절대 경로 대신 사례 폴더 이름부터 적는다
            rel = f"{f.parent.name}/{f.name}"
        h.update(rel.encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()[:12]


def case_fingerprints(case_dir, turns, environment, prepared_files=None):
    """일반 평가가 전달할 턴·준비 자료·실행 설정을 당시 근거와 함께 고정한다.

    판정 코드와 과제 입력은 다른 값이다. 재판정은 이 함수를 호출하지 않는다.
    준비 결과도 포함해 다른 사례에 위임한 setup이 만든 실제 출발 상태를 보존한다.
    """
    case_dir = Path(case_dir)
    files = [*turns]
    files += [case_dir / name for name in ('setup.sh', 'after-install.sh', 'global-entry',
              'review-required', 'verify-conditions.txt') if (case_dir / name).is_file()]
    files += [case_dir / f'before-turn{n}.sh' for n in range(1, len(turns) + 1)
              if (case_dir / f'before-turn{n}.sh').is_file()]
    files += [f for f in (EVALS / 'fixtures').rglob('*') if f.is_file() and '__pycache__' not in f.parts]
    def name(f):
        try:
            return f.relative_to(case_dir).as_posix()
        except ValueError:
            return 'fixtures/' + f.relative_to(EVALS / 'fixtures').as_posix()
    inputs = {'version': 1, 'turns': [name(Path(f)) for f in turns],
              'files': {name(Path(f)): hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in sorted(set(files))},
              'environment': environment, 'prepared_files': prepared_files}
    fingerprint = hashlib.sha256(json.dumps(inputs, ensure_ascii=True, sort_keys=True).encode()).hexdigest()
    return {'task_fingerprint': fingerprint, 'task_inputs': inputs}


def goalflow_fingerprints(task):
    """실제로 전달한 과제 자료와 결과를 만드는 실행·판정 코드를 각각 고정한다."""
    task = Path(task)
    goal = EVALS / 'goalflow'
    inputs = sorted(f for f in (task / 'fixture').rglob('*') if f.is_file() and '__pycache__' not in f.parts)
    inputs += [task / name for name in ('request.txt', 'followup.txt', 'answer.txt', 'topics.txt', 'state.txt', 'turns.json', 'discovery.json') if (task / name).is_file()]
    # 과제 간 판정 위임(archive-correction → archive-ambiguity)도 같은 규칙 묶음으로 고정한다.
    rules = [task / 'oracle.py', goal / 'tasks/taskcheck.py', *sorted((goal / 'tasks').glob('*/oracle.py'))]
    rules += [goal / name for name in ('compare.py', 'conversation.py', 'table.py', 'asked.py', 'turnwatch.py')]
    rules += [EVALS / name for name in ('caseinfo.py', 'session.py', 'budget.py', 'transcript.py', 'pins.py', 'pins.json')]
    rules += sorted(task.glob('*.sql'))
    def fingerprint(files):
        h = hashlib.sha256()
        for f in sorted(set(files)):
            h.update(f.relative_to(EVALS).as_posix().encode() + b'\0' + hashlib.sha256(f.read_bytes()).digest())
        return h.hexdigest()
    return {'task_fingerprint': fingerprint(inputs), 'judge_version': fingerprint(rules)}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("path", "version"):
        sys.exit(__doc__.split("사용:", 1)[1])
    if sys.argv[1] == "path":
        print(case_path(sys.argv[2]))
    else:
        try:
            print(judge_version(sys.argv[2]))
        except MissingJudgeFile as e:
            print(e, file=sys.stderr)
            sys.exit(1)
