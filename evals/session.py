"""키트 커밋을 설치한 새 프로젝트를 만들고, 그 안에서 하네스 세션을 띄우고 이어 가는 일을 한 곳에서 맡는다.

평가 실행기(run.py)·goalflow·설치 흐름 시험이 같이 쓴다. Claude 와 Codex 의 차이(명령줄, 임시 홈,
훅·프로젝트 신뢰, 네트워크 옵션, 제한 시간, 세션 id 읽기)는 두 어댑터(Claude·Codex) 안에만 둔다. 부르는 쪽은 하네스 이름으로 가르지 않는다.

프로젝트:
  kit_checkout(ref, dest)   지정한 커밋의 키트를 깨끗한 checkout 으로 만든다(설치기가 미커밋 키트를 거절하므로)
  worktree_kit(dest)        지금 작업 트리의 키트를 커밋으로 만든다(미커밋 변경을 시험할 때)
  build_project(project, kit, prepare, settings, after_install, author, messages)
                            git init → prepare(출발 상태) → 커밋 → install.sh → 설정 합치기 → 커밋 → after_install
  case_fixture(setup)       평가 사례의 출발 상태(README 한 줄과 사례의 setup.sh)를 만드는 prepare
세션(HARNESSES[이름](프로젝트)):
  start(prompt, out)        새 세션의 첫 턴                      ┐ 기록은 <out>.jsonl·<out>.err 에 쓰고
  resume(prompt, out)       같은 세션(session_id)을 이어 가는 턴 ┘ Turn(exit_code, log, err, session_id) 를 돌려준다
  review(directory, prompt, log)  검토자 세션 한 번(구현자와 다른 새 세션). 종료 코드, 하네스가 없으면 None
  version()                 하네스 버전 한 줄
  close(rollout)            임시 홈 정리. Codex 는 그 전에 세션 원본 기록을 rollout 에 남긴다
"""
import fnmatch, json, os, re, shutil, subprocess, sys, tempfile
from collections import namedtuple
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
LIMIT = 1200  # 한 턴의 제한 시간(초)
Turn = namedtuple("Turn", "exit_code log err session_id")


class ProjectError(Exception):
    """프로젝트 준비 실패. step 은 실패한 단계(checkout·prepare·install·settings·after-install)다."""

    def __init__(self, step, detail=""):
        super().__init__(f"{step}: {detail}" if detail else step)
        self.step, self.detail = step, detail


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd).returncode == 0


def _commit(project, message, author):
    name, email = author
    return _git("add", "-A", cwd=project) and _git("-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgsign=false",
                                                   "commit", "-qm", message, cwd=project)


def kit_checkout(ref, dest, source=KIT):
    if not (_git("clone", "-q", str(source), str(dest), cwd=None) and _git("checkout", "-q", ref, cwd=dest)):
        raise ProjectError("checkout", ref)


def worktree_kit(dest):
    """설치에 필요한 키트 파일만 지금 작업 트리에서 복사해 커밋한다(설치기는 커밋된 키트만 설치한다)."""
    dest = Path(dest)
    for rel in ("install.sh", "AGENTS.md", "CLAUDE.md"):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(KIT / rel, dest / rel)
    shutil.copytree(KIT / ".agents" / "skills", dest / ".agents" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    if not (_git("init", "-q", cwd=dest) and _commit(dest, "kit", ("evals", "evals@invalid"))):
        raise ProjectError("checkout", "작업 트리 키트를 커밋하지 못했다")


def case_fixture(setup=None):
    """평가 사례의 출발 상태: README 한 줄, 그리고 사례의 setup.sh(있으면, EVALS_LANG 을 넘긴다)."""
    def prepare(project):
        (project / "README.md").write_text("# 샘플\n", encoding="utf-8")
        if setup:
            subprocess.run(["bash", str(setup)], cwd=project, check=True, env={**os.environ, "EVALS_LANG": os.environ.get("EVALS_LANG", "")})
    return prepare


def merge_settings(path, add):
    """프로젝트 .claude/settings.json 에 add 를 합친다(맨 위 키 단위, enabledPlugins 는 항목 단위)."""
    path = Path(path)
    cur = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    for k, v in add.items():
        cur[k] = {**cur.get(k, {}), **v} if k == "enabledPlugins" and isinstance(v, dict) else v
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def build_project(project, kit, prepare=None, settings=None, after_install=None, author=("evals", "evals@invalid"), messages=("fixture", "kit")):
    """새 프로젝트에 kit(커밋된 키트 checkout)을 설치한다. prepare·after_install 은 프로젝트 폴더를 받는 함수다.
    after_install 은 설치 커밋 뒤에 실행하므로 그 변경은 세션이 보는 작업 트리에만 남는다. 실패하면 ProjectError(단계)."""
    project, kit = Path(project), Path(kit)
    try:
        project.mkdir(parents=True, exist_ok=True)
        ok = _git("init", "-q", cwd=project)
        if ok and prepare:
            prepare(project)
        ok = ok and _commit(project, messages[0], author)
    except (OSError, subprocess.CalledProcessError) as e:
        raise ProjectError("prepare", str(e))
    if not ok:
        raise ProjectError("prepare")
    r = subprocess.run(["bash", str(kit / "install.sh"), str(project)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ProjectError("install", r.stderr)
    if settings is not None:
        try:
            merge_settings(project / ".claude/settings.json", settings)
        except (OSError, ValueError, AttributeError, TypeError) as e:
            raise ProjectError("settings", str(e))
    _commit(project, messages[1], author)
    if after_install:
        try:
            after_install(project)
        except (OSError, subprocess.CalledProcessError) as e:
            raise ProjectError("after-install", str(e))


def _run(cmd, out, limit, cwd=None, env=None, stdin=None):
    """한 턴을 제한 시간 안에서 실행하고 기록을 <out>.jsonl·<out>.err 에 쓴다. 신호로 끝나면 셸처럼 128+신호 번호를 종료 코드로 한다."""
    with open(f"{out}.jsonl", "wb") as o, open(f"{out}.err", "wb") as e:
        rc = subprocess.run(["perl", "-e", "alarm shift; exec @ARGV", str(limit), *cmd], cwd=cwd, stdin=stdin, stdout=o, stderr=e,
                            env={**os.environ, **(env or {})}).returncode
    return rc if rc >= 0 else 128 - rc


def _review(cmd, directory, log, env=None):
    """검토자 세션: 구현자 세션의 표지(세션 id·발신 구분)를 물려주지 않는다. 제한 시간(AWK_VERIFY_TIMEOUT, 기본 900초)을 넘기면 124."""
    keep = {k: v for k, v in os.environ.items() if k not in ("AWK_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    with open(log, "wb") as out, open(str(log) + ".err", "ab") as err:
        try:
            return subprocess.run(cmd, cwd=directory, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env={**keep, **(env or {})},
                                  timeout=int(os.environ.get("AWK_VERIFY_TIMEOUT", "900"))).returncode
        except subprocess.TimeoutExpired:
            return 124


class Harness:
    """한 프로젝트에서 도는 구현자 세션 하나. project 없이 만들면 검토자 세션(review)과 version 만 쓴다."""
    name = ""

    def __init__(self, project=None):
        self.project = project
        self.session_id = ""
        self.project_trusted = False  # 임시 홈에 이 프로젝트 신뢰를 더했는가(Codex 만)

    def version(self):
        try:
            out = subprocess.run([self.name, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
        except OSError:
            return ""
        return out.split("\n")[0]

    def _turn(self, cmd, out, limit=LIMIT, **how):
        rc = _run(cmd, out, limit, **how)
        # 다음 턴이 이어 갈 세션 id: Claude 는 session_id, Codex 는 thread_id 를 기록에서 읽는다(찾을 때까지 턴마다).
        if not self.session_id:
            with open(f"{out}.jsonl", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(e, dict):
                        break
                    if e.get("session_id") or e.get("thread_id"):
                        self.session_id = str(e.get("session_id") or e.get("thread_id"))
                        break
        return Turn(rc, f"{out}.jsonl", f"{out}.err", self.session_id)

    def close(self, rollout=None):
        pass


class Claude(Harness):
    """Claude Code. 사용자 홈(~/.claude)을 그대로 쓴다(전역 지침·플러그인·훅이 함께 돈다)."""
    name = "claude"
    FLAGS = ["--output-format", "stream-json", "--verbose", "--dangerously-skip-permissions", "--max-turns", "30"]

    def start(self, prompt, out):
        return self._turn(["claude", "-p", prompt, *self.FLAGS], out, cwd=self.project)

    def resume(self, prompt, out, from_runner=False):
        """from_runner: 사용자 턴이 아닌 실행기의 반환 턴(제한 시간이 짧다)."""
        return self._turn(["claude", "-p", prompt, "--resume", self.session_id, *self.FLAGS], out, limit=900 if from_runner else LIMIT,
                          cwd=self.project)

    def review(self, directory, prompt, log):
        exe = shutil.which("claude")
        return exe and _review([exe, "-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", "Read,Grep,Glob,Bash", "--max-turns", "30"],
                               directory, log)


def _codex_home():
    """Codex 는 전역 지침을 CODEX_HOME 에서 읽는다. 실제 설정(인증·config·AGENTS.md)만 복사한 임시 홈을 쓴다(사용자 전역 설정은 건드리지 않는다)."""
    home = tempfile.mkdtemp()
    for f in ("auth.json", "config.toml", "AGENTS.md"):
        src = Path.home() / ".codex" / f
        if src.is_file():
            shutil.copy(src, home)
    return home


class Codex(Harness):
    """Codex. 임시 홈을 세션이 끝날 때(close)까지 두어 같은 세션을 이어 간다."""
    name = "codex"

    def __init__(self, project=None):
        super().__init__(project)
        self.home, self.flags = None, []
        if project is None:
            return
        self.home = _codex_home()
        # EVALS_CODEX_NETWORK=1 이면 작업 공간에 네트워크를 허용한다(세션 안에서 다른 세션을 띄우는 후보를 시험할 때).
        if os.environ.get("EVALS_CODEX_NETWORK") == "1":
            self.flags += ["-c", "sandbox_workspace_write.network_access=true"]
        # Codex 는 프로젝트 훅을 사용자가 한 번 신뢰해야 실행한다. 프로젝트에 .codex/hooks.json 이 있을 때만(정보 훅이 있던 v3.2~v3.4 커밋)
        # 그 신뢰를 대신한다.
        hooks = Path(project) / ".codex/hooks.json"
        if hooks.is_file():
            self.flags.append("--dangerously-bypass-hook-trust")
        # v3.2~v3.4 의 세션 시작 정보 훅(wf-context)은 Codex 가 프로젝트를 신뢰해야(trust_level) 읽힌다. 프로젝트를 신뢰한 사용자를 재현하려고
        # 임시 홈의 config.toml 에만 이 프로젝트 신뢰를 더한다.
        if hooks.is_file() and re.search(r"wf-context/context.py", hooks.read_text(encoding="utf-8", errors="replace")):
            config = Path(self.home) / "config.toml"
            for pdir in (str(project), os.path.realpath(project)):
                entry = f'[projects."{pdir}"]'
                if not (config.is_file() and entry.encode() in config.read_bytes()):
                    with open(config, "ab") as f:
                        f.write(f'\n{entry}\ntrust_level = "trusted"\n'.encode())
            self.project_trusted = True

    def start(self, prompt, out):
        return self._turn(["codex", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", *self.flags, "-C", str(self.project), prompt],
                          out, env={"CODEX_HOME": self.home}, stdin=subprocess.DEVNULL)

    def resume(self, prompt, out, from_runner=False):
        """from_runner: 사용자 턴이 아닌 실행기의 반환 턴(네트워크·훅 신뢰 옵션은 주지 않는다)."""
        return self._turn(["codex", "exec", "resume", "--json", "--skip-git-repo-check", "-c", 'sandbox_mode="workspace-write"',
                           *([] if from_runner else self.flags), self.session_id, prompt], out, cwd=self.project, stdin=subprocess.DEVNULL,
                          env={"CODEX_HOME": self.home})

    def review(self, directory, prompt, log):
        exe = shutil.which("codex")
        if not exe:
            return None
        home = _codex_home()  # 검토자는 구현자와 홈을 나눠 쓰지 않는다
        try:
            return _review([exe, "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(directory), prompt],
                           directory, log, {"CODEX_HOME": home})
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def close(self, rollout=None):
        """exec 기록(--json)에는 하위 에이전트 생성(spawn_agent)이 남지 않는다. 관찰용으로 이 세션의 원본 기록을 rollout 에 남기고 임시 홈을 지운다."""
        if rollout and self.session_id:
            with open(rollout, "wb") as out:
                for root, _, files in os.walk(Path(self.home) / "sessions"):
                    for f in files:
                        if fnmatch.fnmatchcase(f, f"rollout-*{self.session_id}.jsonl"):
                            out.write((Path(root) / f).read_bytes())
        if self.home:
            shutil.rmtree(self.home, ignore_errors=True)


HARNESSES = {"claude": Claude, "codex": Codex}
