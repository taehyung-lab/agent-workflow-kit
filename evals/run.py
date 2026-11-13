"""키트 문장의 행동 효과를 새 세션으로 잰다(run.sh 가 부르는 실행기 본체).

사례 하나를, 지정한 키트 커밋을 설치한 격리 프로젝트에서 Claude·Codex 새 세션에 주고
원시 기록·메타데이터·판정을 evals/results/ 아래에 남긴다. 답이나 예상 결과는 세션에 주지 않는다.
프로젝트 만들기와 하네스 세션(두 하네스의 차이)은 session.py 가, 결과 기록(meta.json)은 result.py 가, 판정 낱말과 그 종료 코드는 judge.py 가 맡는다.

사용: bash evals/run.sh <사례> <키트 커밋·태그> <claude|codex> [반복 수]
  예: bash evals/run.sh weight-accounting v1.0.0 claude 2
      bash evals/run.sh recommend-from-context v3.7.0..HEAD codex 2   (두 커밋 비교, 끝에 report.py --compare)
      bash evals/run.sh weight-accounting HEAD codex
여러 턴 사례는 prompt2.txt … 를 두면 같은 세션을 이어 가며 차례로 보낸다.
결과 요약: python3 -I evals/report.py evals/results
EVALS_VERIFY=1 이면 모든 턴 뒤에 실행기가 별도 검증 세션(같은 하네스의 새 세션)을 판정 대상의 복사본에서 띄운다.
검증 라운드는 설치되는 검토 도구(.agents/skills/wf-verify/verify.py)를 사용자와 같은 옵션(--request·--map·--base·--conditions·--rounds)으로 부른다.
검증자는 사용자 원문 그대로(모든 사용자 턴)·작업 지도 `## 기준`·필수 조건·대상 버전·작업 시작부터의 변경(diff)·실행 방법만 받는다.
구현자의 답·지도의 증거(자기평가)는 넘기지 않는다. 판정은 정해진 결과 형식(JSON)으로만 읽는다:
  ok → 완료, returned → 구현자에게 돌려보내고 새 버전을 다시 판정(EVALS_VERIFY_ROUNDS 번까지, 기본 2), 그 밖(빈 답·형식 오류·
  조건 누락·OK 인데 미충족)·검증자 하네스 오류·검증자가 추적 파일을 바꿈 → 미확인. 한도에 닿으면 미완료. 미확인·미완료는 완료가 아니다.
  이 루프는 지금 도구의 옵션을 쓴다. v3.5 이하 커밋의 검토 비교는 그 태그를 꺼내 그 태그의 evals 로 돌린다.
EVALS_LANG=<언어> 는 사례의 setup.sh 에 넘겨 같은 사례를 다른 제품 언어로 만든다(사례가 지원할 때). meta 의 lang 에 남는다.
EVALS_CLAUDE_SETTINGS=<JSON 파일> 은 설치 뒤 프로젝트 .claude/settings.json 에 그 내용을 합친다(맨 위 키 단위, enabledPlugins 는 항목 단위).
  실제 사용 조합 재현용 예: evals/profiles/real-plugins.json(superpowers 를 프로젝트에서 끄고, 사용자 설정의 나머지 플러그인은 그대로).
  Claude 는 늘 사용자 홈(~/.claude)의 전역 지침·플러그인·훅을 함께 읽는다. 실제로 켜진 플러그인 목록의 지문은 meta 의 global_instructions.plugins 에 남는다.
그 밖의 옵션: EVALS_RESULTS(결과 폴더), EVALS_APPROVE=1(approve.txt 를 마지막 턴으로), EVALS_CODEX_NETWORK=1(session.py), EVALS_RUN_OFFSET(비교 실행이 쓰는 번호 이어 받기).
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(HERE))
import observe, result, session, transcript, verdict
from caseinfo import MissingJudgeFile, case_path, judge_version
from judge import FAIL, REVIEW, UNVERIFIED

# 하네스가 모델 용량·요청 한도 같은 외부 장애로 끝났는지: 기록의 오류 사건(transcript.error_lines)과 표준 오류에서만 찾는다(일반 답 속 낱말은 보지 않는다).
EXTERNAL = re.compile(rb'at capacity|rate.?limit|usage.?limit|hit your [0-9a-z -]*limit|api_error_status"?: ?429|too many requests|overloaded|HTTP 429|stream disconnected|service unavailable', re.I)
# 전역 스킬은 폴더 전체의 SKILL.md 내용으로 지문을 만든다(스킬이 하나 바뀌어도 지문이 달라진다).
# 정렬 순서·경로 표기까지 예전 결과의 지문과 같아야 비교할 수 있으므로 셸 명령을 그대로 쓴다.
SKILLS_FINGERPRINT = 'find -L "$HOME/.agents/skills" "$HOME/.claude/skills" -name SKILL.md 2>/dev/null | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-12'


def fail(message):
    print(f"evals: {message}", file=sys.stderr)
    sys.exit(2)


def last_line(text):
    return (text[:-1] if text.endswith("\n") else text).split("\n")[-1]


def read_turn(path):
    """턴 파일의 글(끝 줄바꿈 제외). 바이트를 그대로 하네스 인자로 넘길 수 있게 읽는다."""
    return Path(path).read_text(encoding="utf-8", errors="surrogateescape").rstrip("\n")


def append(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def append_file(dst, src):
    with open(dst, "ab") as f:
        f.write(Path(src).read_bytes())


def copy_files(project, dest):
    """프로젝트의 작업 파일(설치된 키트·git 제외)을 dest 로 복사한다."""
    # judge.NOT_PRODUCT 보다 덜 뺀다: 이 사본으로 다시 판정하므로 사례 판정이 읽는 work/·AGENTS.md·하네스 설정까지 남긴다.
    pack = subprocess.Popen(["tar", "cf", "-", "--exclude=./.git", "--exclude=./.agents", "."], cwd=project, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    subprocess.run(["tar", "xf", "-", "-C", str(dest)], stdin=pack.stdout)
    pack.stdout.close()
    pack.wait()


def fingerprint(path):
    """비교가 같은 조건인지 판단할 수 있게, 세션에 함께 들어오는 전역 지침의 지문을 남긴다(내용은 남기지 않는다)."""
    path = Path(path).expanduser()
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.is_file() else "none"


def plugins_fingerprint(project):
    """Claude 에서 실제로 켜지는 플러그인 목록(사용자 설정 위에 프로젝트 설정을 덮은 enabledPlugins 중 true)의 지문. 플러그인 조합이 다른 실행끼리 비교하지 않게 한다."""
    on = {}
    try:
        for f in (Path.home() / ".claude/settings.json", project / ".claude/settings.json", project / ".claude/settings.local.json"):
            if f.is_file():
                on.update(json.loads(f.read_text(encoding="utf-8")).get("enabledPlugins") or {})
        return hashlib.sha256(json.dumps(sorted(k for k, v in on.items() if v)).encode()).hexdigest()[:12]
    except Exception:
        return "none"


def verify_loop(harness, project, out, turns, base_sha, case_dir, tool, t):
    """독립 검증 루프. 검증 입력 묶기·결과 판정·재검증 한도는 설치된 검토 도구가 맡고, 검토자 세션을 띄우는 일만 verdict.py session 이 한다.
    도구는 사용자와 같은 옵션으로 부른다: 사용자 턴 전부(--request), 작업 시작 커밋(--base), 사례의 필수 조건(--conditions), 지도가 하나면 그 지도(--map, session 이 고른다).
    돌려줌: 검증 사실(state·reason·rounds·verifier_exit_code·review·baseline_changed)과, 교정 턴에서 구현자 하네스가 실패했으면 그 종료 코드(아니면 0)."""
    max_rounds = os.environ.get("EVALS_VERIFY_ROUNDS") or "2"
    args = [a for turn in turns for a in ("--request", str(turn))] + ["--base", base_sha]
    if (case_dir / "verify-conditions.txt").is_file():
        args += ["--conditions", str(case_dir / "verify-conditions.txt")]
    had_work = (project / "work").exists()
    # 도구가 지금 옵션을 모르거나(v3.5 이하 커밋) 작업 시작 상태를 남기지 못했으면 검토를 돌리지 않는다(다른 기준으로 조용히 대신하지 않는다).
    try:
        source = Path(tool).read_text(encoding="utf-8", errors="replace")
    except OSError:
        source = ""
    block = "" if re.search(r"^def record", source, re.M) else "이 커밋의 검토 도구는 지금 옵션을 쓰지 않는다. 그 태그의 evals 로 돌린다"
    if not base_sha:
        block = "작업 시작 상태를 커밋으로 남기지 못했다"
    v = {"state": "off", "reason": "", "rounds": 0, "verifier_exit_code": None, "review": {}, "baseline_changed": False}
    rc = 0

    def get(key):  # 결과 JSON 의 값을 글로(없으면 빈 글, 참·거짓은 true·false)
        x = v["review"].get(key)
        return "" if x is None else str(x).lower() if isinstance(x, bool) else str(x).rstrip("\n")

    while True:
        if block:
            v.update(state="unverified", reason=block)
            break
        # 도구의 회차 기록은 구현자도 쓰는 프로젝트 안에 있어 시도가 새로 시작될 수 있다. 실행기도 한도를 따로 센다.
        if v["rounds"] >= int(max_rounds):
            v.update(state="incomplete", reason=f"재검증 한도({max_rounds})에 닿았다")
            break
        v["rounds"] += 1
        vlog = f"{out}.verify{v['rounds']}.jsonl"
        with open(f"{out}.err", "ab") as err:
            printed = subprocess.run([sys.executable, "-I", str(HERE / "verdict.py"), "session", "--tool", str(tool), "--harness", harness.name,
                                      "--rounds", max_rounds, "--log", vlog, *args], cwd=project, stdout=subprocess.PIPE, stderr=err, text=True).stdout
        if os.path.isfile(vlog):
            shutil.copy(vlog, f"{out}.verify.jsonl")  # 마지막 판정 기록(이전 판정은 .verifyN.jsonl 로 남는다)
        try:
            review = json.loads(last_line(printed))
        except ValueError:
            review = {}
        v["review"] = review if isinstance(review, dict) else {}  # 객체가 아니면 결과가 아니다
        state, v["reason"] = get("state"), get("reason")
        if get("criteria_changed") == "true":
            v["baseline_changed"] = True
        if get("verifier_exit_code") not in ("", "0"):
            v["verifier_exit_code"] = int(get("verifier_exit_code"))
        if not state:
            v.update(state="unverified", reason="검증 실행기가 결과를 내지 못했다", review={})
            break
        if state in ("ok", "unverified", "incomplete"):
            v["state"] = state
            break
        # 돌려보냄: 구현자 세션에 반환 턴을 보낸다. 반환 턴은 사용자 턴이 아니므로 before-last 를 덮지 않는다.
        t += 1
        prompt = ("별도 검증자가 다음 사유로 돌려보냈습니다. 검증자의 판단을 그대로 따르지 말고, 사용자 원문과 작업 기준에 비추어 판단해 다시 답하세요.\n\n" + get("final")).rstrip("\n")
        turn = harness.resume(prompt, f"{out}.t{t}", from_runner=True)
        append_file(f"{out}.jsonl", turn.log)
        append_file(f"{out}.err", turn.err)
        if turn.exit_code != 0:
            rc = turn.exit_code
            v.update(state="incomplete", reason=f"교정 턴의 구현자 하네스 종료 코드 {rc}")
            break
    # 회차 증거(판정 대상 복사본 포함)는 결과 폴더로 옮긴다: 프로젝트에 남으면 사례 판정이 검토 흔적을 구현자의 산출물로 읽는다.
    rounds = Path(f"{out}.rounds")
    shutil.rmtree(rounds, ignore_errors=True)
    rounds.mkdir(parents=True)
    for ev in [project / "work/review", *sorted(p for p in project.glob("work/*/verify") if not p.parent.name.startswith("."))]:
        if ev.is_dir():
            shutil.move(str(ev), str(rounds / f"{ev.parent.name}-{ev.name}"))
    for empty in [rounds] + ([] if had_work else [project / "work"]):
        try:
            empty.rmdir()
        except OSError:
            pass
    return v, rc


def judge(case_dir, project, work, out, rc, observed, input_kind):
    """사례 판정. 돌려줌: (판정 낱말, 판정 문구). 판정 검사는 0=통과, 1=실패, 2=검토 필요를 돌려주고, 미확인은 실행기가 정한다:
    하네스가 외부 장애로 끝났으면 판정하지 않고 통과율 분모에서 뺀다(시도·사유는 남긴다)."""
    lines = transcript.error_lines(f"{out}.jsonl") + Path(f"{out}.err").read_bytes().split(b"\n")
    external = next((m.group().decode(errors="replace") for m in map(EXTERNAL.search, lines) if m), "")
    if rc != 0 and external:
        # 장애 전에 제품 파일을 바꿨으면(최종 파일 차이, 또는 바꿨다가 되돌린 편집 기록) 위반일 수 있으므로
        # 지우지 않고 사람이 원시 기록으로 판정한다.
        edited = ""
        # 사례 판정의 judge.NOT_PRODUCT 와 같은 물음이지만 목록과 방식이 다르다: 여기는 AGENTS.md·CLAUDE.md·.pytest_cache 를 빼지 않고(바뀌면 검토 필요),
        # 이름이 같으면 깊이와 관계없이 빼며, .gitignore 를 보지 않는다. 합치면 외부 장애 실행의 판정(검토 필요 ↔ 미확인)이 달라진다.
        if (work / "before-last").is_dir():
            diff = subprocess.run(["diff", "-rq", "--exclude=.git", "--exclude=.agents", "--exclude=.claude", "--exclude=.codex", "--exclude=work",
                                   "--exclude=__pycache__", str(work / "before-last"), "."], cwd=project, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  encoding="utf-8", errors="replace").stdout
            edited = diff.split("\n")[0]
        if not edited and observed.get("last_turn_edits"):
            edited = "편집 기록: " + ", ".join(observed["last_turn_edits"])
        if edited:
            return REVIEW, f"{REVIEW} 외부 장애({external})로 끝났지만 그 전에 제품 파일이 바뀌었다: {edited}"
        return UNVERIFIED, f"{UNVERIFIED} 하네스가 외부 장애({external})로 종료 코드 {rc} 로 끝나 판정하지 않았다"
    if rc != 0:
        return FAIL, f"{FAIL} 하네스가 종료 코드 {rc} 로 끝나 판정하지 않았다"
    r = subprocess.run([sys.executable, "-I", str(case_dir / "check.py"), str(project), f"{out}.jsonl"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, "EVALS_INPUT": input_kind, "EVALS_BEFORE_LAST_TURN": str(work / "before-last")})
    text = r.stdout.rstrip("\n")
    word = result.check_word(r.returncode, text)
    # 판정 검사 자체가 오류로 끝나면(예외 등) 실패가 아니라 미확인이다.
    if word == UNVERIFIED:
        text = f"{UNVERIFIED} 판정 검사 오류(종료 코드 {r.returncode}): {text.split(chr(10))[-1]}"
    return word, text


def current_judge_version(case_dir, where=""):
    """판정기 지문은 재판정(rejudge.py)과 같은 함수로 만든다. 판정 파일이 빠졌으면 빈 지문으로 기록하지 않고 멈춘다."""
    try:
        return judge_version(case_dir)
    except MissingJudgeFile as e:
        print(e, file=sys.stderr)
        fail("판정기 지문을 만들 수 없다(위 파일 누락)" + where)


def run_once(case_name, case_dir, ref, commit, harness_name, i, out_root, state):
    """한 번 실행해 결과 파일을 남긴다. 돌려줌: 하네스 종료 코드."""
    lang = os.environ.get("EVALS_LANG", "")
    settings_file = os.environ.get("EVALS_CLAUDE_SETTINGS", "")
    work = Path(tempfile.mkdtemp())
    project, kit = work / "project", work / "kit"
    settings = None
    if settings_file:
        try:
            settings = json.loads(Path(settings_file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fail(f"EVALS_CLAUDE_SETTINGS 를 합치지 못했다: {settings_file}")
    setup, after = case_dir / "setup.sh", case_dir / "after-install.sh"
    # 설치 뒤 준비(선택): 설치된 상태를 바꿔야 하는 사례(예: 키트 본문을 읽을 수 없게, 다른 저장소를 옆에 두기)가 쓴다. EVALS_KIT 는 설치에 쓴 키트 checkout 이다.
    after_install = (lambda p: subprocess.run(["bash", str(after)], cwd=p, check=True, env={**os.environ, "EVALS_KIT": str(kit)})) if after.is_file() else None
    try:
        session.kit_checkout(commit, kit)
        session.build_project(project, kit, prepare=session.case_fixture(setup if setup.is_file() else None), settings=settings, after_install=after_install)
    except session.ProjectError as e:
        fail({"checkout": f"키트 checkout 실패: {commit}", "prepare": "사례 준비 실패", "install": f"키트 설치 실패: {commit}",
              "settings": f"EVALS_CLAUDE_SETTINGS 를 합치지 못했다: {settings_file}", "after-install": f"설치 뒤 준비 실패: {after}"}[e.step])

    name = f"{case_name}{'-' + lang if lang else ''}-{commit[:7]}-{harness_name}-{i}"
    out = f"{out_root}/{name}"
    # 사례의 턴: prompt.txt 가 첫 턴, prompt2.txt·prompt3.txt … 가 같은 세션을 이어 가는 다음 턴이다.
    # 턴마다 원시 기록을 .tN.jsonl 로 남기고, 판정용 .jsonl 은 모든 턴을 순서대로 이은 것이다(마지막 답 = 마지막 턴의 답).
    turns = [case_dir / "prompt.txt"] + [case_dir / f"prompt{n}.txt" for n in range(2, 10) if (case_dir / f"prompt{n}.txt").is_file()]
    # EVALS_APPROVE=1 이면 사례의 approve.txt(사용자 승인 턴)를 마지막 턴으로 더한다. 원래 입력과 승인 추가 입력은 meta 의 input 으로 구분된다.
    input_kind = "original"
    if os.environ.get("EVALS_APPROVE") == "1" and (case_dir / "approve.txt").is_file():
        turns.append(case_dir / "approve.txt")
        input_kind = "with-approval"
    start, rc = int(time.time()), 0
    Path(f"{out}.jsonl").write_bytes(b"")
    Path(f"{out}.err").write_bytes(b"")
    # 사례 폴더에 global-entry 가 있으면(전역 진입 문장의 약속을 재는 사례) 그 키트 커밋의 entry.md 문단을 이 세션의 전역 지침으로 넣는다.
    # 실행한 사람의 개인 전역 지침은 이 세션에서만 빠진다. 그 커밋에 entry.md 가 없으면 개인 지침 그대로 돌리고 meta 에 남긴다.
    entry = session.entry_text(kit) if (case_dir / "global-entry").is_file() else None
    global_entry = "kit:entry.md" if entry else ("missing" if (case_dir / "global-entry").is_file() else "personal")
    harness = session.HARNESSES[harness_name](str(project), entry=entry)
    t = sent = 0
    # 작업 시작 상태(첫 턴 직전)를 커밋 하나로 남긴다(가지·index 는 그대로). 검증자는 마지막 턴만이 아니라 작업 시작부터의 변경 전체를 받는다.
    try:
        base_sha = verdict.snapshot(str(project))
    except Exception:
        base_sha = ""
        append(f"{out}.err", traceback.format_exc().rstrip("\n"))
    for turn_file in turns:
        t += 1
        sent += 1
        tout = f"{out}.t{t}"
        # 턴 사이 준비(선택): before-turnN.sh 가 있으면 N 번째 턴을 보내기 전에 프로젝트 폴더에서 실행한다(예: 재개 전에 다른 사람이 파일을 바꿈).
        before = case_dir / f"before-turn{t}.sh"
        if before.is_file():
            with open(f"{out}.err", "ab") as err:
                failed = subprocess.run(["bash", str(before)], cwd=project, stdout=err, stderr=err).returncode != 0
            if failed:
                rc = 3
                append(f"{out}.err", f"턴 사이 준비 실패: before-turn{t}.sh")
                break
        # 턴마다 직전 작업 파일(설치된 키트·git 제외)을 덮어 남긴다. 끝나면 "마지막으로 실행한 턴의 직전 상태"가 되어,
        # 판정은 그 턴에서 무엇을 바꿨나를 보고, 하네스가 중간에 실패해도 실패한 턴의 직전 상태가 남는다.
        shutil.rmtree(work / "before-last", ignore_errors=True)
        (work / "before-last").mkdir()
        copy_files(project, work / "before-last")
        turn = harness.start(read_turn(turn_file), tout) if t == 1 else harness.resume(read_turn(turn_file), tout)
        append_file(f"{out}.jsonl", turn.log)
        append_file(f"{out}.err", turn.err)
        if turn.exit_code != 0:
            rc = turn.exit_code
            break
        if len(turns) > 1 and not turn.session_id:
            rc = 3
            append(f"{out}.err", "세션 id 를 찾지 못해 다음 턴을 이어 갈 수 없다")
            break
    v = {"state": "off", "reason": "", "rounds": 0, "verifier_exit_code": None, "review": {}, "baseline_changed": False}
    if os.environ.get("EVALS_VERIFY") == "1" and rc == 0:
        # 그 커밋의 키트에 도구가 없으면 이 저장소의 것을 쓴다(meta.verifier_tool).
        state["verifier_tool"] = str(project / ".agents/skills/wf-verify/verify.py")
        if not os.path.isfile(state["verifier_tool"]):
            state["verifier_tool"] = str(KIT / ".agents/skills/wf-verify/verify.py")
        v, rc = verify_loop(harness, project, out, turns, base_sha, case_dir, state["verifier_tool"], t)
    harness.close(rollout=transcript.rollout_log(f"{out}.jsonl"))
    seconds = int(time.time()) - start
    try:
        names = (case_dir / "observe.txt").read_text(encoding="utf-8").split() if (case_dir / "observe.txt").is_file() else []
        observed = json.loads(json.dumps(observe.observe(f"{out}.jsonl", names), ensure_ascii=False))
    except Exception:
        observed = {}
    word, text = judge(case_dir, project, work, out, rc, observed, input_kind)
    jv = current_judge_version(case_dir, f": {out}")  # 실행 중 판정 파일이 사라졌으면 멈춘다(원시 기록 .jsonl 은 남아 있다)
    # 사례가 AGENTS.md 를 읽을 수 없게 만들었으면 바이트는 설치에 쓴 키트 checkout 에서 잰다.
    try:
        agents_bytes = len((project / "AGENTS.md").read_bytes())
    except OSError:
        agents_bytes = len((kit / "AGENTS.md").read_bytes())
    try:
        facts = {
            "case": case_name, "kit_ref": ref, "kit_commit": commit, "harness": harness_name, "run": i, "harness_version": harness.version(),
            "exit_code": rc, "seconds": seconds, "agents_md_bytes": agents_bytes, "check": word, "check_output": text,
            "input": input_kind, "user_turns": sent, "planned_turns": len(turns), "observed": observed,
            "verifier": v["state"], "verify_reason": v["reason"], "verify_rounds": v["rounds"], "verifier_exit_code": v["verifier_exit_code"],
            "review": v["review"], "baseline_changed": v["baseline_changed"], "verifier_tool": state["verifier_tool"],
            "review_required": (case_dir / "review-required").is_file(), "lang": lang, "judge_version": jv,
            "codex_project_trusted": harness.project_trusted, "global_entry": global_entry,
            "claude_project_settings": Path(settings_file).read_text(encoding="utf-8").rstrip("\n") if settings_file else "",
            "global_instructions": {"~/.claude/CLAUDE.md": fingerprint("~/.claude/CLAUDE.md"), "~/.agents/USER.md": fingerprint("~/.agents/USER.md"),
                                    "~/.codex/AGENTS.md": fingerprint("~/.codex/AGENTS.md"),
                                    "global skills": subprocess.run(["bash", "-c", SKILLS_FINGERPRINT], stdout=subprocess.PIPE, text=True).stdout.rstrip("\n"),
                                    "plugins": plugins_fingerprint(project)},
        }
        result.write_meta(f"{out}.meta.json", facts)
    except Exception:
        traceback.print_exc()  # 기록을 쓰지 못해도 끝난 프로젝트 파일은 남긴다
    print(f"{name} exit={rc} check={word} {text.split(chr(10))[0]}", flush=True)
    # 판정 검사를 고친 뒤 다시 판정할 수 있게, 끝난 프로젝트의 작업 파일(설치된 키트·git 제외)을 남긴다.
    # 같은 이름으로 다시 실행해도 지난 실행의 파일이 섞이지 않게 먼저 비운다.
    shutil.rmtree(f"{out}.files", ignore_errors=True)
    shutil.rmtree(f"{out}.before-last", ignore_errors=True)
    os.makedirs(f"{out}.files", exist_ok=True)
    copy_files(project, f"{out}.files")
    # 마지막 턴 직전 상태도 남긴다. 다시 판정할 때 EVALS_BEFORE_LAST_TURN 으로 넘긴다.
    if (work / "before-last").is_dir():
        subprocess.run(["cp", "-R", str(work / "before-last"), f"{out}.before-last"])
    shutil.rmtree(work, ignore_errors=True)
    return rc


def compare(case_name, ref, harness_name, times):
    """비교 실행: <기준>..<대상> 이면 같은 사례·하네스로 두 커밋을 번갈아(기준 1회, 대상 1회, …) 돌린다(시간대·모델 상태의 차이가 한쪽에 몰리지 않게).
    끝나면 양쪽 원시 기록을 지금 판정기로 다시 판정(rejudge)한 뒤 report.py --compare 로 전후를 보여 준다(판정기가 달라 비교 불가가 되지 않게)."""
    base, target = ref[:ref.index("..")], ref[ref.rindex("..") + 2:]
    out = os.environ.get("EVALS_RESULTS") or f"{HERE}/results/{time.strftime('%Y%m%d')}"
    rc = 0
    for i in range(1, times + 1):
        for side in (base, target):
            rc = subprocess.run([sys.executable, "-I", __file__, case_name, side, harness_name, "1"],
                                env={**os.environ, "EVALS_RESULTS": out, "EVALS_RUN_OFFSET": str(i - 1)}).returncode or rc
    rc = subprocess.run([sys.executable, "-I", str(HERE / "rejudge.py"), out], stdout=subprocess.DEVNULL).returncode or rc
    subprocess.run([sys.executable, "-I", str(HERE / "report.py"), "--compare", base, target, out])
    return rc


def main(argv):
    if len(argv) < 3:
        fail("사용: bash evals/run.sh <사례> <키트 커밋·태그 | 기준..대상> <claude|codex> [반복 수]")
    case_name, ref, harness_name = argv[:3]
    times = int(argv[3]) if len(argv) > 3 and argv[3] else 1
    if ".." in ref:
        return compare(case_name, ref, harness_name, times)
    case_dir = case_path(case_name)  # cases 에 없으면 holdout(기계 판정이 PASS 를 내지 않는 사례. caseinfo.py)
    if not ((case_dir / "prompt.txt").is_file() and (case_dir / "check.py").is_file()):
        fail(f"사례가 없거나 prompt.txt·check.py 가 빠졌다: {case_dir}")
    current_judge_version(case_dir)  # 판정 파일이 빠졌으면 모델을 돌리기 전에 멈춘다
    r = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--verify", "-q", ref + "^{commit}"], stdout=subprocess.PIPE, text=True)
    if r.returncode != 0:
        fail(f"키트에 없는 커밋·태그: {ref}")
    commit = r.stdout.strip()
    if harness_name not in session.HARNESSES:
        fail("하네스는 claude 또는 codex")
    if not shutil.which(harness_name):
        fail(f"{harness_name} 명령이 없다")
    out_root = os.environ.get("EVALS_RESULTS") or f"{HERE}/results/{time.strftime('%Y%m%d')}"
    # 턴은 프로젝트 폴더로 옮겨 실행하므로 결과 폴더는 절대 경로로 바꿔 둔다(상대 경로면 턴 기록을 쓰지 못한다).
    os.makedirs(out_root, exist_ok=True)
    out_root = os.path.realpath(out_root)
    offset = int(os.environ.get("EVALS_RUN_OFFSET") or 0)  # 비교 실행은 번호를 이어 받아 결과 이름이 겹치지 않게 한다
    status = 0
    state = {"verifier_tool": ""}  # 검증을 돌리지 않은 실행의 meta 에는 앞선 실행이 쓴 도구 경로가 남는다(예전 실행기와 같다)
    for i in range(1 + offset, times + offset + 1):
        rc = run_once(case_name, case_dir, ref, commit, harness_name, i, out_root, state)
        # 하네스가 실패했으면 판정과 관계없이, 처음 실패한 실행의 종료 코드를 그대로 돌려준다.
        status = status or rc
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
