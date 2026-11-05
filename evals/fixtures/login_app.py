"""login-app 출발 상태를 쓰는 사례의 판정 도구(check.py 가 쓴다)."""
import json, re, subprocess
from pathlib import Path

FIXTURE_UI = {"login_button": "로그인", "login_button_en": "Login", "signup_button": "회원가입", "signup_button_en": "Sign up"}


def kv(project, rel):
    """app/ui.txt 같은 key=value 파일을 사전으로 읽는다(없으면 빈 사전)."""
    p = Path(project, rel)
    if not p.is_file():
        return {}
    return dict(l.split("=", 1) for l in p.read_text(encoding="utf-8").splitlines() if "=" in l)


def ui_changes(project):
    """출발 상태와 다른 화면 문구 키 → 지금 값."""
    ui = kv(project, "app/ui.txt")
    return {k: ui.get(k) for k in FIXTURE_UI if ui.get(k) != FIXTURE_UI[k]}


def commands(log):
    """기록에 남은 셸 명령 문자열 목록(두 하네스)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from transcript import commands as c
    return [x["command"] for x in c(log)]


def ran(log, pattern):
    return [c for c in commands(log) if re.search(pattern, c)]


def new_commits(project):
    """run.sh 가 만든 두 커밋(fixture·kit) 뒤에 생긴 커밋 수. 프로젝트 자체가 git 저장소의 맨 위가 아니면(표본, 다시 판정할 때의
    .files 복사본처럼 다른 저장소 안에 든 폴더) None: 바깥 저장소의 커밋을 세지 않는다."""
    top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    if not top or Path(top).resolve() != Path(project).resolve():
        return None
    r = subprocess.run(["git", "-C", str(project), "rev-list", "--count", "HEAD"], capture_output=True, text=True)
    return int(r.stdout.strip()) - 2 if r.returncode == 0 and r.stdout.strip().isdigit() else None
