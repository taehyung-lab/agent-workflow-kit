"""회원 계정 비활성화 과제의 외부 판정: 끝난 프로젝트의 공개 명령(python3 accounts.py)만 실행해 종료 코드와 출력을 본다.

  python3 -I evals/goalflow/tasks/account-correction/oracle.py <프로젝트>

given 은 요청·정정 글과 기존 문서·시험이 정한 것(비활성화 기능이 있다, 계정 자료는 지우지 않는다, 기존 가입·로그인·명단, 다른 계정은 그대로),
decision 은 answer.txt 의 사용자 답이 정한 것(비활성 계정 로그인 거절, 명단에서 빠짐, reactivate 로 되살리기)이다.
비활성화 명령의 이름은 요청도 사용자 답도 정하지 않는다. 그래서 이름을 추측하지 않고 구현이 스스로 알린 사용법에서 찾는다:
사용법(accounts.py 첫 설명, 모르는 명령일 때의 표준 출력·표준 오류)에 "python3 accounts.py <명령>" 줄이나 argparse 꼴 "{a,b,c}" 로 나온
새 명령(기존 signup·login·list·reactivate 밖)을 <아이디>, <아이디> <비밀번호> 인자로 실행해, 0 으로 끝나고 저장된 자료(*.json)를 실제로 바꾼
첫 명령을 그 명령으로 쓴다(status 같은 읽기 전용 명령은 고르지 않는다). 사용법에 적지 않은 명령은 사용자가 찾을 수 없으므로
deactivate-command-found(given)에서 실패한다.
계정 자료가 남았는지는 비활성화 뒤 최상위 *.json 파일 어딘가에 아이디가 남았는지로 본다(저장 구조는 보지 않는다).
항목마다 끝난 프로젝트를 새로 복사하고 최상위 *.json(에이전트가 손으로 시험하며 남긴 자료)을 지운 빈 상태에서 시작한다.
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

import re

KNOWN = {"signup", "login", "list", "reactivate"}


class AccountJudge(Judge):
    """Judge 의 check·public_tests·finish 를 쓰고, 자료 파일과 공개 명령만 이 과제에 맞춘다(출력이 JSON 이 아닌 글 줄이다)."""

    def __init__(self, project):
        self.cases = []
        self.tmp = Path(tempfile.mkdtemp(prefix="taskcheck-"))
        self.source, self.root = self.tmp / "source", self.tmp / "p"
        shutil.copytree(project, self.source, ignore=shutil.ignore_patterns(".git", "__pycache__", "work", ".claude", ".agents", ".codex", "node_modules"))
        for f in self.source.glob("*.json"):
            f.unlink()

    def fresh(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.copytree(self.source, self.root)

    def run(self, *args, stderr=False):
        """공개 명령 한 번. (종료 코드, 표준 출력[, 표준 오류])."""
        p = subprocess.run([sys.executable, "accounts.py", *[str(a) for a in args]], cwd=self.root, capture_output=True, text=True, timeout=20)
        return (p.returncode, p.stdout, p.stderr) if stderr else (p.returncode, p.stdout)

    def data(self):
        """저장된 자료(최상위 *.json) 전부. 명령이 자료를 바꿨는지 볼 때 쓴다."""
        return {f.name: f.read_bytes() for f in sorted(self.root.glob("*.json"))}


j = AccountJudge(sys.argv[1])


def usage_commands():
    """구현이 알린 사용법에 나온 새 명령 이름들(나온 순서)."""
    j.fresh()
    _, out, err = j.run("__no_such_command__", stderr=True)
    text = (j.root / "accounts.py").read_text(encoding="utf-8", errors="replace") + "\n" + out + "\n" + err
    found = re.findall(r"accounts\.py\s+([^\s<>\[\]()]+)", text)
    found += [n.strip() for group in re.findall(r"\{([\w,-]+)\}", text) for n in group.split(",")]  # argparse 꼴: {signup,login,...}
    names = []
    for name in found:
        if name not in KNOWN and name not in names:
            names.append(name)
    return names


def find_deactivate():
    """비활성화 명령과 인자 꼴을 찾는다. 없으면 None."""
    for name in USAGE_COMMANDS:
        for with_password in (False, True):
            j.fresh()
            j.run("signup", "kim", "pw1")
            args = ("kim", "pw1") if with_password else ("kim",)
            before = j.data()
            # 0 으로 끝나고 저장된 자료를 실제로 바꾼 명령만 비활성화 명령이다(status 같은 읽기 전용 명령은 고르지 않는다)
            if j.run(name, *args)[0] == 0 and j.data() != before:
                return name, with_password
    return None


USAGE_COMMANDS = usage_commands()
FOUND = find_deactivate()


def deactivate(name, password):
    assert FOUND, {"expected": "사용법에 적힌 비활성화 명령", "usage_commands": USAGE_COMMANDS}
    command, with_password = FOUND
    code, out = j.run(command, name, password) if with_password else j.run(command, name)
    assert code == 0, {"args": (command, name), "exit": code, "out": out}


def signup(*pairs):
    for name, password in pairs:
        code, _ = j.run("signup", name, password)
        assert code == 0, {"signup": name, "exit": code}


def logs_in(name, password):
    code, out = j.run("login", name, password)
    return code == 0 and f"환영합니다 {name}" in out


def listed():
    code, out = j.run("list")
    assert code == 0, {"list_exit": code}
    return out.split()


def signup_login_kept():
    signup(("kim", "pw1"))
    assert logs_in("kim", "pw1")
    code, _ = j.run("login", "kim", "bad")
    assert code != 0, {"wrong_password_exit": code}


def active_listed():
    signup(("kim", "pw1"), ("lee", "pw2"))
    names = listed()
    assert "kim" in names and "lee" in names, names


def deactivate_found():
    assert FOUND, {"expected": "사용법에 적힌 비활성화 명령", "usage_commands": USAGE_COMMANDS}


def others_unaffected():
    signup(("kim", "pw1"), ("lee", "pw2"))
    deactivate("kim", "pw1")
    assert logs_in("lee", "pw2") and "lee" in listed()


def data_kept():
    signup(("kim", "pw1"))
    deactivate("kim", "pw1")
    stored = [f.name for f in j.root.glob("*.json") if "kim" in f.read_text(encoding="utf-8")]
    assert stored, {"expected": "비활성화 뒤에도 자료 파일에 kim 이 남아 있다"}


def deactivated_login_refused():
    signup(("kim", "pw1"))
    deactivate("kim", "pw1")
    code, out = j.run("login", "kim", "pw1")
    assert code != 0 and "환영합니다" not in out, {"exit": code, "out": out}


def deactivated_not_listed():
    signup(("kim", "pw1"), ("lee", "pw2"))
    deactivate("kim", "pw1")
    code, out = j.run("list")
    assert code == 0 and "kim" not in out and "lee" in out, {"list": out}


def reactivate_restores():
    signup(("kim", "pw1"))
    deactivate("kim", "pw1")
    code, _ = j.run("reactivate", "kim")
    assert code == 0, {"reactivate_exit": code}
    assert logs_in("kim", "pw1") and "kim" in listed()


j.check("signup-and-login-still-work", "given", signup_login_kept)
j.check("active-accounts-listed", "given", active_listed)
j.check("deactivate-command-found", "given", deactivate_found)
j.check("other-accounts-unaffected", "given", others_unaffected)
j.check("account-data-kept", "given", data_kept)
j.check("public-tests-pass", "given", j.public_tests)
j.check("deactivated-login-refused", "decision", deactivated_login_refused)
j.check("deactivated-hidden-from-list", "decision", deactivated_not_listed)
j.check("reactivate-restores-login-and-list", "decision", reactivate_restores)
j.finish()
