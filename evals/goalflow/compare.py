"""과제 하나를 요청부터 구현·외부 판정까지 한 번에 도는 구성 비교: 키트(kit) / 스킬 설치(skills) / 지침 없음(none).

  python3 -I evals/goalflow/compare.py <kit|skills|none> <claude|codex> <번호> <결과 폴더>
  python3 -I evals/goalflow/table.py <결과 폴더> [-v]

키트의 채택 기준("같은 과제에서 스킬 설치 구성과 같거나 나은가")을 재는 실행기다. 실제 모델 세션을 띄우므로 시간과 비용이 든다.
세션은 사용자 전역 설정과 격리한다: Claude 는 --setting-sources project, Codex 는 임시 HOME·CODEX_HOME(인증·모델 설정만).
턴은 모든 구성이 같다: ① 요청 원문 (①′ 과제에 followup.txt 가 있으면 그 글 그대로: 정정처럼 정해진 두 번째 사용자 글) ② 모의 사용자의 답 ③ 마무리 지시.
스킬 구성만 ①의 앞에 스킬을 쓰라는 한 줄이 붙는다. 모델과 CLI 는 evals/pins.json 으로 고정하고, 실제 CLI 버전이 다르면 시작하지 않는다.
끝나면 프로젝트 밖에서 oracle.py 로 실제 저장·반환값을 판정한다.
요약(<이름>.json)과 함께, 일반 결과 표(evals/report.py)가 읽는 <이름>.meta.json 을 쓴다(table.py 의 result_meta).

환경 변수:
  CMP_TASK    과제 이름(기본 goalflow = 회차 신청). tasks/ 아래 폴더 이름을 주면 그 과제를 돈다(orders·rooms).
              과제 폴더에는 fixture/(시작 프로젝트)·request.txt·answer.txt·topics.txt·oracle.py 가 있다. 회차 신청은 이 폴더 자체가 과제 폴더이고 요청은 fixture/request.txt 다.
  CMP_REF     설치할 키트 커밋(기본 HEAD. 커밋하지 않은 수정은 들어가지 않는다)
  CMP_SKILLS  skills 구성에 설치할 스킬 저장소의 skills 폴더(예: mattpocock/skills 를 고정 커밋으로 받은 곳의 skills/). 그 안의 productivity/grilling·engineering/tdd 를 쓴다
  CMP_PREFIX  첫 요청 앞에 붙일 한 줄(기본: skills 구성만 "grilling 스킬로 요구를 확인한 다음 tdd 스킬로 구현해 주세요.")
  MOCK        asked(기본): 답 전 발견한 선택을 분류해 따로 채점하고 answer.txt 전체를 전달한다. all: 발견을 채점하지 않고 같은 정책으로 구현만 확인한다
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
GOAL = KIT / "evals/goalflow"
TASK_NAME = os.environ.get("CMP_TASK", "goalflow")
TASK = GOAL if TASK_NAME == "goalflow" else GOAL / "tasks" / TASK_NAME
assert (TASK / "oracle.py").is_file(), f"과제 폴더가 없다: {TASK}"
MP = Path(os.environ.get("CMP_SKILLS") or "/nonexistent")
sys.path.insert(0, str(KIT / "evals"))
from session import kit_checkout, HARNESSES, reserve_run, runtime_stop  # noqa: E402
import pins  # noqa: E402
from caseinfo import goalflow_fingerprints
from transcript import read, commands, replies  # noqa: E402
from observe import agent_evidence
sys.path.insert(0, str(Path(__file__).resolve().parent))
from asked import surfaced  # noqa: E402
from conversation import CONVERSATION_CONTRACT, MockUser, log_readable, product_changes as changes_since, product_diff, read_state, turn_writes, product_snapshot, decision_contract  # noqa: E402
from turnwatch import Watch  # noqa: E402
from table import result_meta, discovery_scope  # noqa: E402

arm, harness, idx, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]).resolve()
# 실행 하네스는 시작 전에, 발견 분류기는 분류할 때 자신의 고정 버전을 확인한다.
MOCK = os.environ.get("MOCK", "asked")
mismatch = pins.check(harness)
if mismatch:
    sys.exit(mismatch)
name = f"{arm}-{harness}-{idx}"
out.mkdir(parents=True, exist_ok=True)
try:
    reserve_run(out / name)
except FileExistsError as e:
    sys.exit(str(e))
work = Path(tempfile.mkdtemp(prefix="cmp-"))
proj = work / "p"
G = ["git", "-c", "user.name=cmp", "-c", "user.email=cmp@invalid", "-c", "commit.gpgsign=false"]
sh = lambda *c, cwd=None: subprocess.run(c, cwd=cwd, capture_output=True, text=True)

# ---- 프로젝트 ----
shutil.copytree(TASK / "fixture", proj, ignore=shutil.ignore_patterns("__pycache__"))
sh(*G, "init", "-q", cwd=proj); sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "fixture", cwd=proj)
skills_fingerprint = None
kit_ref = kit_commit = None  # 키트 구성만 값이 있다
if arm == "kit":
    kit_ref = os.environ.get("CMP_REF", "HEAD")
    kit_checkout(kit_ref, work / "kit")
    kit_commit = sh("git", "rev-parse", "HEAD", cwd=work / "kit").stdout.strip()
    r = sh("bash", str(work / "kit/install.sh"), str(proj))
    assert r.returncode == 0, r.stderr
elif arm == "skills":
    assert (MP / "productivity/grilling").is_dir() and (MP / "engineering/tdd").is_dir(), "CMP_SKILLS 에 스킬 저장소의 skills 폴더를 준다"
    installed = hashlib.sha256()
    for src in (MP / "productivity/grilling", MP / "engineering/tdd"):
        for file in sorted(p for p in src.rglob("*") if p.is_file()):
            installed.update(str(file.relative_to(MP)).encode() + b"\0" + file.read_bytes())
        for root in (".claude/skills", ".agents/skills"):
            shutil.copytree(src, proj / root / src.name)
    skills_fingerprint = installed.hexdigest()
sh(*G, "add", "-A", cwd=proj); sh(*G, "commit", "-qm", "arm: " + arm, "--allow-empty", cwd=proj)
base = sh(*G, "rev-parse", "HEAD", cwd=proj).stdout.strip()
agents_md_bytes = (proj / "AGENTS.md").stat().st_size if (proj / "AGENTS.md").is_file() else 0  # 세션 전, 구성 설치 직후의 상시 지침 크기

request = next(f for f in (TASK / "request.txt", TASK / "fixture/request.txt") if f.is_file()).read_text(encoding="utf-8").strip()
answer = (TASK / "answer.txt").read_text(encoding="utf-8").strip()
topics = (TASK / "topics.txt").read_text(encoding="utf-8").strip()
# 고정 정책을 모두 전달한다. asked는 전달 전 발견한 선택을 따로 측정하며 all은 구현만 비교한다.
PREFIX = os.environ.get("CMP_PREFIX", "grilling 스킬로 요구를 확인한 다음 tdd 스킬로 구현해 주세요." if arm == "skills" else "")
FIRST = (PREFIX + "\n\n" if PREFIX else "") + request
# 정해진 사용자 글(요청, 있으면 followup.txt). 그 뒤 턴은 모의 사용자의 답, 마지막은 마무리 지시다.
STATIC = [FIRST] + ([(TASK / "followup.txt").read_text(encoding="utf-8").strip()] if (TASK / "followup.txt").is_file() else [])
def classifier(reply, topics):
    mismatch = pins.check("claude")
    if mismatch:
        raise RuntimeError(mismatch)
    return surfaced(reply, topics, record_dir=out / f"{name}.classifier")
mock = MockUser(STATIC, answer, topics, classifier, MOCK)
DECISION_TURNS = decision_contract(TASK, len(STATIC))
discovery_file = TASK / 'discovery.json'
DISCOVERY = json.loads(discovery_file.read_text()) if discovery_file.exists() else {}
if discovery_file.exists() and set(DISCOVERY) != {'required_discovery_topics', 'discovery_exclusions'}:
    raise ValueError('발견 범위와 제외 근거를 함께 기록해야 한다')
discovery_scope(sorted(mock.items), DISCOVERY.get('required_discovery_topics', sorted(mock.items)), DISCOVERY.get('discovery_exclusions', {}))

# 두 대화 방식은 세션 실행·재개·격리·원시 기록 보존을 함께 사용한다.
implementation = HARNESSES[harness](proj, profile="comparison")
try:
    rows, started = [], time.time()


    def launch(n, prompt):
        prefix = out / f"{name}.t{n}"
        Path(str(prefix) + ".prompt.txt").write_text(prompt, encoding="utf-8")
        t0 = time.time()
        turn = implementation.start(prompt, prefix) if n == 1 else implementation.resume(prompt, prefix)
        return turn.exit_code, Path(turn.log), int(time.time() - t0)


    STATE = read_state(TASK)  # 과제가 정한 앱 상태 파일(제품 아님)


    def product_changes():
        """시작 커밋과 다른 제품 파일(커밋했든 안 했든). 작업 지도·키트·스킬·캐시·과제가 정한 앱 상태 파일은 빼고 센다."""
        return changes_since(proj, base, STATE)


    for n in range(1, mock.turns + 1):
        before = set(mock.answered)
        prompt = mock.prompt(n)
        start_product = product_snapshot(proj, STATE)
        try:
            watch, watch_error = Watch(proj), None
        except OSError as e:  # 감시를 켜지 못하면 이 턴의 편집은 관찰 불가(증거 부족)
            watch, watch_error = None, str(e)
        rc, log, secs = launch(n, prompt)
        try:
            touched = turn_writes(watch.stop(), proj, base, STATE, files=start_product) if watch else None  # 턴 안에서 쓰거나 만들거나 지운 제품 파일(되돌려도 남는다)
        except OSError as e:
            touched, watch_error = None, str(e)
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
        mock.observe("\n\n".join(replies(str(log))) or final)
        (out / f"{name}.t{n}.diff").write_text(product_diff(proj, base, STATE), encoding="utf-8")  # 증거: 그 턴이 끝났을 때의 제품 변경
        end_product = product_snapshot(proj, STATE)
        changed_this_turn = sorted(f for f in start_product.keys() | end_product.keys() if start_product.get(f) != end_product.get(f))
        rows.append({"runtime_stop": runtime_stop(log, rc), "turn_changes": changed_this_turn, "turn": n, "rc": rc, "answered_now": sorted(mock.answered - before), "product_touched": touched, "watch_error": watch_error, "log_readable": log_readable(str(log)), "seconds": secs, "product_changes": product_changes(), "reply_chars": len(final),
                     "question_marks": final.count("?") + final.count("？"), "reply": final[:6000],
                     "record_runs": sum(bool(re.search(r"(?:verify|work)\.py\s+record\b", c["command"])) for c in cmds),
                     "review_runs": sum(bool(re.search(r"(?:verify\.py\s+prepare|work\.py\s+review)\b", c["command"])) for c in cmds),
                     "test_runs": sum(bool(re.search(r"unittest|pytest|bin/probe", c["command"])) for c in cmds)})
        if rc != 0 or not implementation.session_id:
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
    summary = {"name": name, "task": TASK_NAME, "model": pins.model(harness), "mock_user_model": pins.mock_user_model() if MOCK == "asked" else None, "harness_version": pins.cli_version(harness), "static_turns": len(STATIC), "decision_turns": DECISION_TURNS, "arm": arm, "harness": harness, "run": int(idx) if idx.isdigit() else idx, "kit_ref": kit_ref, "kit_commit": kit_commit, "agents_md_bytes": agents_md_bytes, "base": base, "seconds": int(time.time() - started), "turns": rows,
               "mock": MOCK, "answered": sorted(mock.answered), "skills_fingerprint": skills_fingerprint,
               **goalflow_fingerprints(TASK), "global_instructions": implementation.instruction_context(),
               "prompt_configuration": {"prefix_override": os.environ.get("CMP_PREFIX")}, "effective_prefix": PREFIX,
               "conversation_contract": CONVERSATION_CONTRACT, "policy_topics": sorted(mock.items), **DISCOVERY, "discovered": sorted(mock.discovered),
               "surfaced_quotes": {str(t): q for t, q in mock.quotes.items()}, "mock_error": mock.discovery_error, "map": any((proj / "work").glob("*/work.md")), "final_changes": product_changes(), "init": init,
               "oracle_exit": oracle.returncode, "automated_valid": verdict.get("automated_valid"), "observation_complete": verdict.get("observation_complete"),
               "failed": [c.get("name") for c in cases if c.get("passed") is False], "failed_decision": verdict.get("failed_decision"), "unobserved": [c.get("name") for c in cases if c.get("passed") is None],
               "n_cases": len(cases), "oracle_error": verdict.get("error"), "public_tests_rc": smoke.returncode}
    (out / f"{name}.oracle.json").write_text(oracle.stdout or oracle.stderr, encoding="utf-8")
finally:
    try:
        shutil.copytree(proj, out / f"{name}.files", ignore=shutil.ignore_patterns(".git", "__pycache__"), dirs_exist_ok=True)
    finally:
        try:
            # close preserves Codex's source before removing its temporary home.
            # It must run exactly once; a second close can truncate that source.
            implementation.close(out / f"{name}.rollout.jsonl")
        finally:
            shutil.rmtree(work, ignore_errors=True)

# Source preservation precedes every observation and final result. Settings and
# product facts above were captured while the session and project still existed.
for row in summary['turns']:
    number = row['turn']
    stage = 'requirements' if number <= len(STATIC) else 'implementation' if number == len(STATIC) + 1 else 'completion'
    row['agent_evidence'] = agent_evidence(out / f'{name}.t{number}.jsonl', harness, number,
                                          stage=stage, rollout=out / f'{name}.rollout.jsonl')
(out / f"{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
(out / f"{name}.meta.json").write_text(json.dumps(result_meta(summary), ensure_ascii=False, indent=1), encoding="utf-8")
# 첫 줄은 전체 판정이다(답 전 수정·답 전 발견·최종 동작을 함께 본 oracle_verdict). 최종 동작의 실패 수만 내면 답 전 위반이 가려진다.
print(name, result_meta(summary)["check_output"], "| seconds=", summary["seconds"],
      "| runtime_stops=", [{"turn":row["turn"], "reason":row["runtime_stop"]["reason"]} for row in summary["turns"] if row.get("runtime_stop")])
