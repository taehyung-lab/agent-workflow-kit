"""평가 사례의 위치와 판정기 지문을 한 곳에서 정한다. 실행기(run.sh)와 재판정(rejudge.py)이 같이 쓴다.

사례 위치: evals/cases/<이름> 이 있으면 그것, 없으면 evals/holdout/<이름>(숨겨 둔 평가 사례).
판정기 지문(judge_version): 판정 결과를 바꿀 수 있는 파일(사례의 check.py 와 JUDGE_FILES)의 경로와 내용으로 만든 12자리 값.
같은 코드면 실행·재판정이 같은 값을 내고, 그중 하나라도 바뀌면 값이 바뀐다.
파일이 하나라도 없으면 지문을 만들지 않고 실패한다(빠진 파일을 뺀 지문은 다른 판정기를 같은 판정기로 보이게 한다).

사용:
  python3 -I evals/caseinfo.py path <사례 이름>        → 사례 폴더(없어도 holdout 경로를 낸다. 존재 확인은 부르는 쪽 몫)
  python3 -I evals/caseinfo.py version <사례 폴더>     → 판정기 지문. 파일이 빠졌으면 종료 1, 빠진 파일을 stderr 로
"""
import hashlib, sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
KIT = EVALS.parent
# 모든 사례의 check.py 가 기대는 공용 판정 코드. 판정에 쓰는 파일을 새로 만들면 여기에 넣는다.
JUDGE_FILES = ("evals/judge.py", "evals/observe.py", "evals/transcript.py", "evals/verdict.py", "evals/result.py",
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
