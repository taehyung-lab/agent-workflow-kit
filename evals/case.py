"""사례 판정(check.py)이 공통으로 받는 것. check.py 에는 그 사례의 판정만 남긴다.

check.py 는 `python3 -I check.py <프로젝트 폴더> <세션 기록 .jsonl>` 로 실행되고, PASS / FAIL / REVIEW 로 시작하는
한 줄을 찍은 뒤 0 / 1 / 2 로 끝난다. 이 모듈이 그 약속을 맡는다:

  project         판정할 프로젝트 폴더(절대 경로 Path. 다시 판정(rejudge)은 상대 경로를 넘긴다)
  log             세션 기록 경로(받은 문자열 그대로)
  steps, final    세션 기록의 도구 호출 목록과 마지막 답(transcript.read 의 결과). 처음 가져올 때 한 번 읽는다.
                  기록을 쓰지 않는 판정은 가져오지 않으면 되고, 그러면 기록 파일을 열지 않는다.
  done(msg)       판정 한 줄을 찍고 첫 낱말에 맞는 종료 코드로 끝낸다.
  copy_project()  프로젝트를 임시 폴더에 복사해 그 경로를 돌려준다(제품 명령을 실행해 보는 판정용).

`-I` 실행에서는 check.py 의 폴더도 evals/ 도 모듈 경로에 없으므로, check.py 는 이 모듈을 가져오기 전에
`sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` 한 줄을 둔다.
"""
import shutil, sys, tempfile
from pathlib import Path

from transcript import read

project = Path(sys.argv[1]).resolve()
EXIT = {"PASS": 0, "FAIL": 1, "REVIEW": 2}


def __getattr__(name):
    if name == "log":
        return sys.argv[2]
    if name in ("steps", "final"):
        g = globals()
        g["steps"], g["final"] = read(sys.argv[2])
        return g[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def done(msg):
    code = EXIT[msg.split(" ", 1)[0]]  # 판정 낱말이 아니면 찍지 않고 여기서 오류로 멈춘다
    print(msg)
    sys.exit(code)


def copy_project(*also_ignore):
    """git 기록·하네스 설정(.claude·.codex)·작업 기록(work)을 뺀 프로젝트 사본. 더 뺄 이름·패턴은 인자로 준다."""
    work = Path(tempfile.mkdtemp()) / "p"
    shutil.copytree(project, work, symlinks=True, ignore=shutil.ignore_patterns(".git", ".claude", ".codex", "work", *also_ignore))
    return work
