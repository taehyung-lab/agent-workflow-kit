"""과제 하나를 요청부터 구현·외부 판정까지 한 번에 도는 구성 비교: 키트(kit) / 스킬 설치(skills) / 지침 없음(none).

  python3 -I evals/goalflow/compare.py <kit|skills|none> <claude|codex> <번호> <결과 폴더>
  python3 -I evals/goalflow/table.py <결과 폴더> [-v]

키트의 채택 기준("같은 과제에서 스킬 설치 구성과 같거나 나은가")을 재는 실행기다. 실제 모델 세션을 띄우므로 시간과 비용이 든다.
세션은 사용자 전역 설정과 격리한다: Claude 는 --setting-sources project, Codex 는 임시 HOME·CODEX_HOME(인증·모델 설정만).
턴은 모든 구성이 같다: ① 요청 원문 ② 모의 사용자의 답 ③ 마무리 지시. 스킬 구성만 ①의 앞에 스킬을 쓰라는 한 줄이 붙는다.
끝나면 프로젝트 밖에서 oracle.py 로 실제 저장·반환값을 판정한다.
요약(<이름>.json)과 함께, 일반 결과 표(evals/report.py)가 읽는 <이름>.meta.json 을 쓴다(table.py 의 result_meta).

환경 변수:
  CMP_TASK    과제 이름(기본 goalflow = 회차 신청). tasks/ 아래 폴더 이름을 주면 그 과제를 돈다(orders·rooms).
              과제 폴더에는 fixture/(시작 프로젝트)·request.txt·answer.txt·topics.txt·oracle.py 가 있다. 회차 신청은 이 폴더 자체가 과제 폴더이고 요청은 fixture/request.txt 다.
  CMP_REF     설치할 키트 커밋(기본 HEAD. 커밋하지 않은 수정은 들어가지 않는다)
  CMP_SKILLS  skills 구성에 설치할 스킬 저장소의 skills 폴더(예: mattpocock/skills 를 고정 커밋으로 받은 곳의 skills/). 그 안의 productivity/grilling·engineering/tdd 를 쓴다
  CMP_PREFIX  첫 요청 앞에 붙일 한 줄(기본: skills 구성만 "grilling 스킬로 요구를 확인한 다음 tdd 스킬로 구현해 주세요.")
  MOCK        asked(기본): answer.txt 의 정책 가운데 에이전트가 물은 것만 답한다(물었는지는 asked.py 가 Haiku 로 분류). all: 세 정책을 전부 알려 준다
"""
import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
GOAL = KIT / "evals/goalflow"
TASK_NAME = os.environ.get("CMP_TASK", "goalflow")
TASK = GOAL if TASK_NAME == "goalflow" else GOAL / "tasks" / TASK_NAME
assert (TASK / "oracle.py").is_file(), f"과제 폴더가 없다: {TASK}"
MP = Path(os.environ.get("CMP_SKILLS") or "/nonexistent")
sys.path.insert(0, str(KIT / "evals"))
from session import kit_checkout  # noqa: E402
from transcript import read, commands, replies  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from asked import asked  # noqa: E402
from table import result_meta  # noqa: E402

arm, harness, idx, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]).resolve()
name = f"{arm}-{harness}-{idx}"
out.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="cmp-"))
proj = work / "p"
G = ["git", "-c", "user.name=cmp", "-c", "user.email=cmp@invalid", "-c", "commit.gpgsign=false"]
sh = lambda *c, cwd=None: subprocess.run(c, cwd=cwd, capture_output=True, text=True)

# ---- 프로젝트 ----
shutil.copytree(TASK / "fixture", proj, ignore=shutil.ignore_patterns("__pycache__"))
sh(*G, "init", "-q", cwd=proj); sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "fixture", cwd=proj)
kit_ref = kit_commit = None  # 키트 구성만 값이 있다
if arm == "kit":
    kit_ref = os.environ.get("CMP_REF", "HEAD")
    kit_checkout(kit_ref, work / "kit")
    kit_commit = sh("git", "rev-parse", "HEAD", cwd=work / "kit").stdout.strip()
    r = sh("bash", str(work / "kit/install.sh"), str(proj))
    assert r.returncode == 0, r.stderr
elif arm == "skills":
    assert (MP / "productivity/grilling").is_dir() and (MP / "engineering/tdd").is_dir(), "CMP_SKILLS 에 스킬 저장소의 skills 폴더를 준다"
    for src in (MP / "productivity/grilling", MP / "engineering/tdd"):
        for root in (".claude/skills", ".agents/skills"):
            shutil.copytree(src, proj / root / src.name)
sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "arm: " + arm, "--allow-empty", cwd=proj)
base = sh(*G, "rev-parse", "HEAD", cwd=proj).stdout.strip()
agents_md_bytes = (proj / "AGENTS.md").stat().st_size if (proj / "AGENTS.md").is_file() else 0  # 세션 전, 구성 설치 직후의 상시 지침 크기

request = next(f for f in (TASK / "request.txt", TASK / "fixture/request.txt") if f.is_file()).read_text(encoding="utf-8").strip()
answer = (TASK / "answer.txt").read_text(encoding="utf-8").strip()
topics = (TASK / "topics.txt").read_text(encoding="utf-8").strip()
# 모의 사용자(MOCK=asked): 물은 정책만 답한다. answer.txt 의 세 항목 가운데 에이전트가 물은 것만 주고, 묻지 않은 것은 알려 주지 않는다.
MOCK = os.environ.get("MOCK", "asked")
items = {int(m.group(1)): m.group(0).strip() for m in re.finditer(r"^(\d+)\. .*$", answer, re.M)}
PREFIX = os.environ.get("CMP_PREFIX", "grilling 스킬로 요구를 확인한 다음 tdd 스킬로 구현해 주세요." if arm == "skills" else "")
FIRST = (PREFIX + "\n\n" if PREFIX else "") + request
CLOSE = "더 물을 것이 없으면 그대로 마무리해 주세요. 남은 질문이 있으면 추천안대로 정해 완료하고, 정한 내용과 실제 실행한 명령·결과를 보고해 주세요."
answered = set()


def next_prompt(n, last_reply):
    if n == 1:
        return FIRST
    if MOCK == "all":
        return answer + "\n\n위 답으로 진행해 주세요." if n == 2 else CLOSE
    new = [t for t in asked(last_reply, topics) if t not in answered]
    answered.update(new)
    told = "\n".join(items[t] for t in new)
    if n == 2:
        return (told + "\n\n물으신 것은 위와 같이 해 주세요. 나머지는 추천안대로 진행해 주세요.") if new else "질문이 없으면 그대로 진행해 주세요."
    return (told + "\n\n" if new else "") + CLOSE

# ---- 세션(전역 설정 격리) ----
env = dict(os.environ)
for k in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION"):
    env.pop(k, None)
if harness == "codex":
    home = work / "home"; (home / ".codex").mkdir(parents=True)
    shutil.copy(Path.home() / ".codex/auth.json", home / ".codex")
    cfg = (Path.home() / ".codex/config.toml").read_text(encoding="utf-8") if (Path.home() / ".codex/config.toml").is_file() else ""
    (home / ".codex/config.toml").write_text(re.split(r"^\[", cfg, maxsplit=1, flags=re.M)[0], encoding="utf-8")  # 맨 위 키(모델 등)만, 표 절은 뺀다
    env.update(HOME=str(home), CODEX_HOME=str(home / ".codex"))

sid, rows, started = "", [], time.time()


def launch(n, prompt):
    global sid
    log = out / f"{name}.t{n}.jsonl"
    if harness == "claude":
        cmd = ["claude", "-p", prompt, *(["--resume", sid] if sid else []), "--setting-sources", "project", "--output-format", "stream-json", "--verbose",
               "--dangerously-skip-permissions", "--max-turns", "80"]
    elif not sid:
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(proj), prompt]
    else:
        cmd = ["codex", "exec", "resume", "--json", "--skip-git-repo-check", "-c", 'sandbox_mode="workspace-write"', sid, prompt]
    t0 = time.time()
    with open(log, "wb") as o, open(str(log) + ".err", "wb") as e:
        rc = subprocess.run(["perl", "-e", "alarm shift; exec @ARGV", "1800", *cmd], cwd=proj, stdin=subprocess.DEVNULL, stdout=o, stderr=e, env=env).returncode
    if not sid:
        for line in open(log, encoding="utf-8", errors="replace"):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and (ev.get("session_id") or ev.get("thread_id")):
                sid = str(ev.get("session_id") or ev.get("thread_id")); break
    return rc, log, int(time.time() - t0)


def product_changes():
    """제품 파일의 변경(작업 지도·키트·스킬·캐시·실행 중 생긴 데이터 파일 제외)."""
    lines = sh(*G, "status", "--porcelain", "--untracked-files=all", cwd=proj).stdout.splitlines()
    skip = ("work/", ".claude/", ".agents/", ".codex/", "AGENTS.md", "CLAUDE.md")
    files = [l[3:] for l in lines]
    return [f for f in files if not f.startswith(skip) and "__pycache__" not in f and not f.endswith((".pyc", ".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal", ".db-shm"))]


last = ""
for n in (1, 2, 3):
    before = set(answered)
    prompt = next_prompt(n, last)
    rc, log, secs = launch(n, prompt)
    try:
        final = read(str(log))[1] or ""
    except Exception as e:  # 기록을 읽지 못하면 그 사실을 남긴다
        final = f"(기록 읽기 실패: {e!r})"
    try:
        cmds = commands(str(log))
    except Exception:
        cmds = []
    # 모의 사용자는 이 턴에 에이전트가 쓴 글 전부를 읽는다. 마지막 글만 읽으면, 질문을 앞 글에 쓰고 마지막에 "위 질문에 답해 달라"고만 한 경우
    # 분류기가 내용 없는 글을 보고 물은 것으로 세어 묻지 않은 답까지 준다(2026-11-13 표본 라벨 과제의 스킬 구성 3회가 그랬다).
    last = "\n\n".join(replies(str(log))) or final
    rows.append({"turn": n, "rc": rc, "answered_now": sorted(answered - before), "seconds": secs, "product_changes": product_changes(), "reply_chars": len(final),
                 "question_marks": final.count("?") + final.count("？"), "reply": final[:6000],
                 "record_runs": sum(bool(re.search(r"verify\.py\s+record\b", c["command"])) for c in cmds),
                 "review_runs": sum(bool(re.search(r"verify\.py\s+prepare\b", c["command"])) for c in cmds),
                 "test_runs": sum(bool(re.search(r"unittest|pytest|bin/probe", c["command"])) for c in cmds)})
    if rc != 0 or not sid:
        break

# ---- 판정(프로젝트 밖) ----
oracle = sh(sys.executable, "-I", str(TASK / "oracle.py"), str(proj))
try:
    verdict = json.loads(oracle.stdout)
except ValueError:
    verdict = {"error": (oracle.stdout + oracle.stderr)[-1500:]}
cases = verdict.get("cases") or verdict.get("checks") or []
smoke = sh(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q", cwd=proj)
init = {}
if harness == "claude":
    for line in open(out / f"{name}.t1.jsonl", encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = {"skills": [s for s in ev.get("skills", []) if s in ("grilling", "tdd")], "plugins": len(ev.get("plugins", [])), "n_skills": len(ev.get("skills", []))}
            break
summary = {"name": name, "task": TASK_NAME, "arm": arm, "harness": harness, "run": int(idx) if idx.isdigit() else idx, "kit_ref": kit_ref, "kit_commit": kit_commit, "agents_md_bytes": agents_md_bytes, "base": base, "seconds": int(time.time() - started), "turns": rows,
           "mock": MOCK, "answered": sorted(answered), "map": any((proj / "work").glob("*/work.md")), "final_changes": product_changes(), "init": init,
           "oracle_exit": oracle.returncode, "automated_valid": verdict.get("automated_valid"), "observation_complete": verdict.get("observation_complete"),
           "failed": [c.get("name") for c in cases if c.get("passed") is False], "failed_decision": verdict.get("failed_decision"), "unobserved": [c.get("name") for c in cases if c.get("passed") is None],
           "n_cases": len(cases), "oracle_error": verdict.get("error"), "public_tests_rc": smoke.returncode}
(out / f"{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
(out / f"{name}.oracle.json").write_text(oracle.stdout or oracle.stderr, encoding="utf-8")
shutil.copytree(proj, out / f"{name}.files", ignore=shutil.ignore_patterns(".git", "__pycache__"), dirs_exist_ok=True)
# Codex 의 exec 기록에는 하위 에이전트 생성이 남지 않는다. 임시 홈을 지우기 전에 이 세션의 원본 기록을 남겨, 별도 독자를 실제로 띄웠는지 볼 수 있게 한다.
if harness == "codex" and sid:
    with open(out / f"{name}.rollout.jsonl", "wb") as roll:
        for root_dir, _, files in os.walk(work / "home" / ".codex" / "sessions"):
            for f in files:
                if f.startswith("rollout-") and f.endswith(f"{sid}.jsonl"):
                    roll.write((Path(root_dir) / f).read_bytes())
(out / f"{name}.meta.json").write_text(json.dumps(result_meta(summary), ensure_ascii=False, indent=1), encoding="utf-8")
shutil.rmtree(work, ignore_errors=True)
print(name, "valid=", summary["automated_valid"], "failed=", len(summary["failed"]), "/", summary["n_cases"], "seconds=", summary["seconds"])
