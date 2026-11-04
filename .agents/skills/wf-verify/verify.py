"""독립 검증 실행기: 구현하지 않은 별도 세션(Claude Code 또는 Codex)을 판정 대상의 고정 복사본에서 띄우고, 정해진 결과 형식으로만 판정한다.

언제: AGENTS.md 「필요한 단계만」이 별도 검증을 요구할 때(공용 경계·큰 연결 불확실성·틀리면 영향 큼·사용자 요구) 전체 담당자가 실행한다.
작은 수정은 이 실행기 없이 직접 확인한다.

  python3 .agents/skills/wf-verify/verify.py --harness claude|codex --map work/<작업명>/work.md [--rounds 2]

독립 검증은 지도 승인을 받은 작업에만 쓴다(대화로 승인한 작은 일은 직접 확인한다). 무엇을 넘기나(구현자가 고르지 않는다):
승인 관문이 승인 때 남긴 그 지도의 `## 기준`(사용자가 승인한 글), 승인 메시지와 승인 뒤의 사용자 메시지, 승인 때 보존한 제품 파일 상태부터
지금까지의 변경(diff). 구현자의 답·지도의 `## 증거`(자기평가)는 넘기지 않는다. 회차마다 고정 대상 저장소·시작 상태·diff·입력·판정을
지도 옆 verify/round-N-<고유 이름>/ 에 새로 남기고(--keep 이나 평가의 --log 옆 .round 폴더를 주면 그 안), 회차 기록은 verify/state.json 에 둔다.
관문 기록(.git/awk-gate)은 읽기만 한다. 기존 폴더·파일은 지우거나 덮지 않는다.

판정(state)과 종료 코드:
  ok(0)          검증자가 형식대로 모든 조건을 충족으로 냈다. 이것만 완료다.
  returned(3)    검증자가 돌려보냈다. 사유를 보고 원인을 고친 뒤 이 명령을 다시 실행해 새 버전을 판정받는다.
  incomplete(4)  재검증 한도에 닿았는데 마지막 판정도 RETURN 이다. 미완료로 보고한다. 한도(--rounds, 기본 2)는 그 승인의 첫 회차에
                 정해지고, 닿은 뒤에는 새 검증자를 띄우지 않는다. 사용자의 새 승인(관문이 검증 기록을 비움)만 새 시도를 연다.
  unverified(5)  판정하지 못했다(빈 답·형식 오류·조건 누락·검증자 하네스 없음·오류·검증자가 대상 파일을 바꿈·사용자 원문이나
                 승인 기록이 없음, 근거 불완전: 시작 내용 미보존·diff 실패·잘림, 검증하는 동안 승인·제품 파일이 바뀜).
                 미확인은 완료가 아니다. 성공처럼 넘어가지 않고 사유와 재개 조건을 보고한다.
회차 기록은 승인 시각이 같을 때만 이어 센다(새 승인이면 1회차부터). 검증자의 글은 이 명령의 출력으로만 돌아오고 사용자 메시지가 아니므로,
그 안의 "승인합니다"·"취소합니다" 는 승인 상태를 바꾸지 않는다.

평가 실행기(evals/run.sh)는 같은 실행기를 쓰되, 사용자 원문·계획·기준·작업 시작 상태를 파일로 직접 넘긴다
(--request·--plan·--criteria·--conditions·--base-dir·--state·--log). 하네스가 실행기 밖에서 돌 때는 관문 기록이 없기 때문이다.
"""
import hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = {"충족", "미충족", "미확인"}
ID = r"[A-Z]{1,3}\d{1,3}"
EXIT = {"ok": 0, "returned": 3, "incomplete": 4, "unverified": 5}
DIFF_LIMIT = 60000  # 검증자 입력에 넣는 diff 최대 바이트(넘으면 잘렸다고 적는다)
KIT_PATHS = (".agents", ".claude", ".codex", "CLAUDE.md", "AGENTS.md")  # 비교하지 않는 키트·하네스 설정(저장소 맨 위만)


VERIFIER_PROMPT = """당신은 별도 검증자다. 판정 대상은 아래 「대상 버전」의 폴더(판정 대상 버전의 고정 복사본)다. 그 폴더의 AGENTS.md 와 .agents/skills/guide.md 「독립 검토」를 읽고 그 기준으로 판정한다.
제품 파일·검사·기준을 고치지 않는다(고치면 이 판정은 무효로 처리된다). 저장소의 실행·검사 명령을 실행해 실제 결과로 판정하며, 그때 생기는 임시 산출물은 괜찮다.
요구의 근거는 아래 사용자 원문(승인 메시지 포함)과 저장소의 외부 계약뿐이다. 구현자가 정한 내용은 근거가 아니다. 구현자의 자기평가는 받지 않는다.
판정 범위는 이 변경이 바꾼 동작과, 연결 근거(같은 함수·같은 출력·같은 계약을 쓴다)가 있는 기존 보장뿐이다. 연결 없는 기능은 보지 않는다.
- 합의 조건이나 연결된 기존 보장을 깨는 반례를 찾으면 그 조건은 미충족이다.
- 새 요구가 있어야 성립하는 반례(원문이 정하지 않은 동작)는 판정을 막지 않고 out_of_scope 에 적는다.
- 승인 뒤 사용자 원문이 결과·범위를 바꿨는데 작업 지도 기준에 없으면, 그 변경을 원문 조건(새 ID)으로 세워 판정한다. 승인한 계획·원문에 없는 동작(새 명령 등)이 추가됐으면 근거 없이 범위를 넓힌 것이므로 RETURN 이다.
- 원문·계약으로 고를 수 없는데 사용자가 받는 결과(동작·데이터·범위·권한)를 구현자가 정해 버렸으면 RETURN 이다.
- 확인하지 못한 조건은 미확인으로 적는다. 미확인이나 미충족이 하나라도 있으면 verdict 는 OK 가 아니다.

답의 맨 끝에 아래 형식의 JSON 하나를 쓴다. 이 JSON 만 판정으로 읽힌다(없거나 형식이 틀리면 미확인으로 처리된다).
아래 "필수 조건" 이 있으면 그 ID 를 모두 conditions 에 넣는다. 필수 조건 밖에서 원문이 요구한 조건이 보이면 새 ID(예: V1)로 더한다.
{"verdict": "OK 또는 RETURN", "conditions": [{"id": "조건 ID", "result": "충족 또는 미충족 또는 미확인", "evidence": "실행한 명령과 실제 결과"}], "return_reason": "RETURN 일 때 사유", "out_of_scope": ["범위 밖 반례"]}"""


def gate_module():
    """같은 키트의 승인 관문(작업 기록을 관리하는 곳)을 불러온다."""
    spec = importlib.util.spec_from_file_location("approval_gate", HERE.parent / "wf-design" / "approval-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- 결과 형식 판정(evals/verdict.py 도 이 함수를 쓴다) ----

def last_json(text):
    """답의 최종 결과 JSON. 답 맨 끝(뒤 공백과 닫는 코드 울타리 ``` 는 빼고)에서 끝나는 완결 객체이고 `verdict` 키가 있어야 한다.
    그 앞의 설명·예시 JSON 은 읽지 않는다. 끝에 끊긴 객체나 다른 글이 붙어 있으면 앞선 완결 객체로 대신하지 않고 실패로 본다.
    돌려줌: (객체 또는 None, 실패 사유)."""
    if not text.strip():
        return None, "빈 답"
    body = text.rstrip()
    if body.endswith("```"):
        body = body[:-3].rstrip()
    dec = json.JSONDecoder()
    if body.endswith("}"):
        # 끝 괄호에서 정확히 끝나는 객체는 가장 바깥 객체 하나뿐이다(안쪽 객체는 그 앞에서 끝난다)
        for i in range(len(body) - 1, -1, -1):
            if body[i] != "{":
                continue
            try:
                obj, end = dec.raw_decode(body, i)
            except ValueError:
                continue
            if end == len(body):
                if isinstance(obj, dict) and "verdict" in obj:
                    return obj, ""
                break
    if '"verdict"' not in text:
        return None, "결과 형식(JSON)이 없다"
    return None, "답 끝의 최종 결과 JSON 이 끊기거나 형식이 틀렸다(앞선 JSON 으로 대신하지 않는다)"


def judge(final, required=()):
    """검증자 답 → {"state": ok|returned|unverified, "reason", "conditions", "out_of_scope"}.
    ok: verdict OK, 조건이 하나 이상이고 모두 충족·근거 있음, 필수 조건 ID 가 모두 있음. returned: RETURN 과 사유. 그 밖은 unverified."""
    v, why = last_json(final or "")
    if v is None:
        return {"state": "unverified", "reason": why, "out_of_scope": []}
    oos = [str(x) for x in v.get("out_of_scope") or [] if str(x).strip()] if isinstance(v.get("out_of_scope"), list) else []
    conds = v.get("conditions") if isinstance(v.get("conditions"), list) else []
    bad_shape = [c for c in conds if not (isinstance(c, dict) and str(c.get("id", "")).strip() and c.get("result") in RESULTS)]
    out = {"out_of_scope": oos, "conditions": [{"id": c.get("id"), "result": c.get("result")} for c in conds if isinstance(c, dict)]}
    verdict = str(v.get("verdict", "")).strip().upper()
    if verdict == "RETURN":
        reasons = str(v.get("return_reason") or "").strip() or [c for c in conds if isinstance(c, dict) and c.get("result") != "충족"]
        return {**out, "state": "returned" if reasons else "unverified", "reason": "" if reasons else "사유 없는 RETURN"}
    if verdict != "OK":
        return {**out, "state": "unverified", "reason": f"알 수 없는 verdict: {verdict or '없음'}"}
    problems = []
    if not conds:
        problems.append("조건별 결과가 없다")
    if bad_shape:
        problems.append("형식이 틀린 조건 결과")
    ids_ = {str(c.get("id")).strip() for c in conds if isinstance(c, dict)}
    missing = [r for r in required if r not in ids_]
    if missing:
        problems.append("필수 조건 누락: " + ", ".join(missing))
    unmet = [str(c.get("id")) for c in conds if isinstance(c, dict) and c.get("result") != "충족"]
    if unmet:
        problems.append("OK 인데 충족이 아닌 조건: " + ", ".join(unmet))
    no_evidence = [str(c.get("id")) for c in conds if isinstance(c, dict) and not str(c.get("evidence") or "").strip()]
    if no_evidence:
        problems.append("근거 없는 조건: " + ", ".join(no_evidence))
    if problems:
        return {**out, "state": "unverified", "reason": " / ".join(problems)}
    return {**out, "state": "ok", "reason": ""}


def completion(verifier, check="REVIEW", waiting=False, required=False):
    """전체 완료 판정(한 곳). verifier: 독립 검토 상태(off·ok·returned·incomplete·unverified), check: 직접 증거(PASS·REVIEW·FAIL·UNVERIFIED,
    REVIEW 는 사람이 원시 기록을 봐야 함), waiting: 승인 관문이 사용자 답을 기다림, required: 이 변경에 독립 검토가 필수인가.
    - 사용자 답 대기면 waiting-user. 직접 증거가 실패면 검토 OK 여도 check-failed, 직접 증거를 못 얻었으면 unverified.
    - 검토를 했는데 OK 가 아니면 그 상태(returned·incomplete·unverified). 검토 OK 면 verified.
    - 검토를 하지 않았는데 필수면 review-missing(호출 누락). 필수가 아니면 직접 증거 PASS 만으로 verified, REVIEW 면 needs-review."""
    if waiting:
        return "waiting-user"
    if check == "FAIL":
        return "check-failed"
    if check == "UNVERIFIED":
        return "unverified"
    if verifier in ("returned", "incomplete", "unverified"):
        return verifier
    if verifier == "ok":
        return "verified"
    if required:
        return "review-missing"
    return "verified" if check == "PASS" else "needs-review"


def section(text):
    """작업 기록의 `## 기준` 절 본문(관문과 같은 정규화)."""
    return gate_module().criteria_text(text)


def baseline(project):
    """work/*/work.md 의 `## 기준` 절만 모은다(`## 증거` 같은 구현자의 실행 기록·자기평가는 넣지 않는다)."""
    parts = []
    for f in sorted(Path(project).glob("work/*/work.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^## 기준[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m and m.group(1).strip():
            parts.append(f"### {f.relative_to(project)}\n{m.group(1).strip()}")
    return "\n\n".join(parts)


def ids(text):
    found = []
    for line in text.splitlines():
        m = re.match(r"^\s*\|?\s*(" + ID + r")\b", line)
        if m and m.group(1) not in found:
            found.append(m.group(1))
    return found


def final_answer(path):
    """검증자 기록(Claude stream-json, Codex --json)의 마지막 답 전체."""
    final = ""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") == "assistant":
            for part in (e.get("message") or {}).get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    final = part.get("text", "")
        elif e.get("type") == "result":
            final = e.get("result") or final
        elif e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message":
            final = e["item"].get("text", "")
    return final


def run_result(output, exit_code=None):
    """명령 출력에서 이 실행기가 찍는 결과를 찾는다. 실행기의 출력은 표준 오류의 `[verify] ` 줄과, 맨 끝 한 줄의 결과 JSON
    (state 가 판정 상태이고 completion 이 있음, main·cli 의 마지막 print)뿐이고, 종료 코드는 그 state 의 EXIT 값이다.
    저장된 result.json 은 completion 이 없어 결과가 아니다.
    돌려줌: (결과 객체 또는 None, 이번 실행의 결과로 볼 수 없는 사유 또는 ""). 다른 글이 섞였거나(예: 스크립트와 저장해 둔 출력을 함께 cat)
    종료 코드가 결과의 state 와 맞지 않으면 그 결과를 이번 실행의 판정으로 쓰지 않는다. 평가 관찰(evals/observe.py)이 이 함수를 쓴다."""
    lines = [l for l in str(output or "").splitlines() if l.strip()]
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("state") in EXIT and "completion" in obj:
            if i != len(lines) - 1 or not all(l.startswith("[verify] ") for l in lines[:i]):
                return obj, "실행기 결과 JSON 이 다른 출력과 섞여 있어 이번 실행의 결과인지 저장된 결과를 읽은 것인지 가를 수 없다"
            if exit_code is not None and exit_code != EXIT[obj["state"]]:
                return obj, f"결과 state {obj['state']} 와 종료 코드 {exit_code} 가 맞지 않는다"
            return obj, ""
    return None, ""


# ---- 판정 대상 고정과 입력 ----

def run(cmd, cwd=None, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, **kw)


def product_list(root):
    """복사할 파일: git 이 아는 파일과 무시되지 않은 새 파일. 작업 지도(work/)는 뺀다(증거·자기평가를 검증자가 보지 않게)."""
    out = run(["git", "-c", "core.fsmonitor=false", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).stdout.decode()
    return sorted({f for f in out.split("\0") if f and not f.startswith("work/")})


def freeze(root, dest):
    """판정 대상 버전을 복사본으로 고정하고 커밋한다. 무시된 파일(빌드 산출물 등)은 복사하지 않는다."""
    dest.mkdir(parents=True)
    for f in product_list(root):
        src, dst = Path(root, f), Path(dest, f)
        if not (src.is_symlink() or src.is_file()):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)
    g = ["git", "-c", "user.name=verify", "-c", "user.email=verify@invalid", "-c", "commit.gpgsign=false"]
    # 하나라도 실패하면(쓰기 경계·git 설정·훅 등) 빈 대상으로 판정하지 않도록 멈춘다. 호출한 쪽이 미확인으로 처리한다.
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "verify-target", "--allow-empty"]):
        r = run(g + step, cwd=dest)
        if r.returncode != 0:
            raise RuntimeError(f"판정 대상 고정 실패(git {step[0]} 종료 코드 {r.returncode}): {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    head = run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=dest)
    if head.returncode != 0 or not head.stdout.strip():
        raise RuntimeError("판정 대상 고정 실패: 고정 커밋을 읽지 못했다")
    return head.stdout.decode().strip()


def materialize_base(root, base_json, dest):
    """관문이 첫 승인 때 git 객체로 보존한 제품 파일 상태를 폴더로 꺼낸다. 돌려줌: 내용을 보존하지 못한 경로 목록."""
    dest.mkdir(parents=True)
    entries = json.loads(Path(base_json).read_text(encoding="utf-8"))
    blobs = [(f, e) for f, e in entries.items() if "blob" in e]
    out = run(["git", "cat-file", "--batch"], cwd=root, input="".join(e["blob"] + "\n" for _, e in blobs).encode()).stdout
    pos, unsaved = 0, [f for f, e in entries.items() if "unsaved" in e]
    for f, e in blobs:
        header_end = out.index(b"\n", pos)
        size = int(out[pos:header_end].split()[2])
        body = out[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        p = Path(dest, f); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(body)
        if e.get("exec"):
            p.chmod(0o755)
    for f, e in entries.items():
        if "link" in e:
            p = Path(dest, f); p.parent.mkdir(parents=True, exist_ok=True); os.symlink(e["link"], p)
    return unsaved


def diff(base, target):
    """(검증자 입력용 diff, 잘렸나, 실행이 실패했나). 전체 diff 는 base 옆 diff.txt 에 남긴다."""
    r = run(["diff", "-ruN", "-x", ".git", "-x", ".agents", "-x", "work", str(base), str(target)])
    text = r.stdout.decode("utf-8", "replace").replace(str(base), "a").replace(str(target), "b")
    Path(base).parent.joinpath("diff.txt").write_text(text, encoding="utf-8")
    failed = r.returncode not in (0, 1)  # diff: 0 같음, 1 다름, 2 오류
    if len(text.encode()) > DIFF_LIMIT:
        return text.encode()[:DIFF_LIMIT].decode("utf-8", "ignore") + f"\n(diff 가 {DIFF_LIMIT} 바이트를 넘어 잘렸다)\n", True, failed
    return text, False, failed


def prompt_text(requests, plan, conditions, criteria, note, target, change, vdir="."):
    parts = [VERIFIER_PROMPT]
    for n, req in enumerate(requests, 1):
        parts.append(f"\n\n## 사용자 원문 {n}\n{req}")
    if plan is not None:
        parts.append(f"\n\n## 승인 원문이 가리키는 계획(승인 바로 앞 구현자 답. 사용자가 이 추천안을 승인했다. 원문과 대조하며, 구현 뒤 자기평가가 아니다)\n{plan}\n")
    parts.append(f"\n\n## 필수 조건\n{conditions or '(사례가 정하지 않음. 원문에서 세운다)'}\n")
    parts.append(f"\n\n## 작업 지도의 기준(사용자가 승인한 때의 지도. 구현자가 쓴 합의 조건이므로 원문과 대조한다)\n{criteria or '(없음)'}\n{note}")
    parts.append(f"\n\n## 대상 버전\n판정 대상 폴더 {vdir} 의 git 커밋 {target}. 이 폴더에서만 읽고 검사를 실행한다(원래 작업 폴더는 보지 않는다).\n")
    parts.append("\n\n## 실행 방법\n저장소 README 와 AGENTS.md 프로젝트 지도에 적힌 실행·검사 명령을 이 폴더에서 실행한다.\n")
    parts.append(f"\n\n## 작업 시작부터 바뀐 내용(diff, 작업 지도 제외)\n{change}")
    return "".join(parts)


def opt(args, name, many=False):
    vals = [args[i + 1] for i, a in enumerate(args[:-1]) if a == name]
    return vals if many else (vals[-1] if vals else None)


def product_print(gate, root):
    """지금 제품 파일 상태의 지문(관문의 제품 파일 범위: 작업 지도·키트·하네스 설정 제외)."""
    return hashlib.sha256(json.dumps(gate.product_files(root), sort_keys=True).encode()).hexdigest()


def copy_kit_paths(vdir, base):
    """키트·하네스 설정(맨 위 .agents·.claude·.codex·CLAUDE.md·AGENTS.md)은 관문의 제품 파일 범위처럼 비교에서 뺀다:
    대상의 것을 시작 상태에도 그대로 두어 차이가 나지 않게 한다(링크 .claude/skills 를 따라간 키트 파일이 diff 를 채우지 않게)."""
    for name in KIT_PATHS:
        src, dst = vdir / name, base / name
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst)
        if src.is_symlink():
            os.symlink(os.readlink(src), dst)
        elif src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        elif src.is_file():
            shutil.copy2(src, dst)


USAGE = ("사용: verify.py prepare [--map work/<작업명>/work.md] [--rounds N]   → 검토 입력(prompt_file)과 판정 대상 폴더를 만든다(지도 없으면 이 세션의 최근 승인)\n"
         "      verify.py finish --round <prepare 가 낸 kept 폴더> [--answer <파일>]   → 검토자의 마지막 답(표준 입력)을 판정한다")


def main(args):
    sub = args[0] if args and args[0] in ("prepare", "finish") else None
    if sub is None:
        print(USAGE, file=sys.stderr)
        return 2
    return prepare(args[1:]) if sub == "prepare" else finish(args[1:])


def prepare(args):
    """검토 입력을 묶는다: 승인된 기준·승인 메시지·승인 뒤 메시지·승인 뒤 변경(diff)과 판정 대상의 고정 복사본. 검토자는 띄우지 않는다
    (일반 작업은 하네스의 하위 에이전트, 평가는 evals 실행기가 띄운다). 한도에 닿았거나 근거가 불완전하면 여기서 최종 결과를 낸다."""
    harness = opt(args, "--reviewer") or "subagent"
    asked_max = int(opt(args, "--rounds") or 2)
    root = Path(run(["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd()).stdout.decode().strip() or os.getcwd())
    gate = gate_module()
    explicit = opt(args, "--request") is not None
    rec, rec_file, state_dir = {}, None, None
    problems = []
    if explicit:  # 평가 실행기: 입력을 파일로 받는다
        requests = [Path(f).read_text(encoding="utf-8") for f in opt(args, "--request", True)]
        plan = Path(opt(args, "--plan")).read_text(encoding="utf-8") if opt(args, "--plan") else None
        criteria = Path(opt(args, "--criteria")).read_text(encoding="utf-8") if opt(args, "--criteria") else ""
        state_file = Path(opt(args, "--state") or tempfile.mktemp(suffix=".json"))
        vstate = json.loads(state_file.read_text()) if state_file.is_file() else {}
    else:  # 일반 작업: 관문이 승인 때 고정한 요청 원문·승인받은 계획(지도가 있으면 그 기준)과 승인 뒤 메시지를 쓴다
        map_path = opt(args, "--map")
        state_dir = gate.locate(root)[1]
        if map_path:
            map_path = str(Path(os.path.realpath(Path(root, map_path))).relative_to(os.path.realpath(root)))
            rec = gate.approved_record(root, state_dir, map_path) or {}
            rec_file = map_path
        else:
            sid = opt(args, "--session") or next((os.environ[k] for k in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID") if os.environ.get(k)), None)
            rec = gate.latest_approval(state_dir, sid) or {}
        if not rec:
            problems.append("사용자 승인 기록이 없다(승인 전이거나 관문 기록이 없음). 승인된 요청·계획이 없어 판정하지 않는다")
        reqs = rec.get("requests") or ([rec["prompt"]] if rec.get("prompt") else [])
        requests = [f"(승인 전·승인 메시지) {m}" for m in reqs] + [f"(승인 뒤 메시지) {m}" for m in rec.get("after", [])]
        if rec and not reqs:
            problems.append("요청 원문을 확보하지 못했다(입력 부족)")
        plan = rec.get("plan") if rec else None
        criteria = f"### {map_path}\n{(rec.get('criteria') or {}).get(map_path) or ''}" if rec and map_path else ""
        if rec and not plan and not criteria.strip():
            problems.append("승인받은 계획을 확보하지 못했다(입력 부족): 승인 직전 답이 대화 기록에 없고 지도도 없다")
        vfile = (Path(root, map_path).parent / "verify" if map_path else Path(root, "work", "review")) / "state.json"
        vstate = json.loads(vfile.read_text()) if vfile.is_file() else {}
        if vstate.get("approved_at") != rec.get("approved_at"):
            vstate = {}  # 새 승인: 회차를 1부터 센다(앞선 증거 폴더는 그대로 남는다)
    conditions = Path(opt(args, "--conditions")).read_text(encoding="utf-8") if opt(args, "--conditions") else ""
    required = ids(conditions + "\n" + criteria)
    rounds = list(vstate.get("rounds", []))
    # 재검증 한도는 이 검증 시도(이 승인)의 첫 회차에 정하고 바꾸지 않는다. 새 시도는 사용자의 새 승인(관문이 검증 기록을 비움)으로만 시작한다.
    rounds_max = int(vstate.get("max_rounds") or asked_max)
    ran = [r for r in rounds if r.get("ran")]
    n = len(rounds) + 1
    result = {"round": n, "max_rounds": rounds_max, "harness": harness, "required": required}
    if asked_max != rounds_max:
        result["note"] = f"재검증 한도는 이 시도의 첫 회차에 정한 {rounds_max} 회다(--rounds {asked_max} 는 쓰지 않았다)"
    map_fp = lambda: gate.maps(root).get(rec_file) if rec_file else None  # 지금 지도의 기준 지문(검증 중 바뀌면 판정 무효)
    start_print = product_print(gate, root)
    start_task = (rec.get("approved_at"), json.dumps(rec.get("targets", {}), sort_keys=True), rec.get("approved"), map_fp())
    if len(ran) >= rounds_max:
        # 한도에 이미 닿았다: 새 검증자를 띄우지 않는다. 마지막 판정이 OK 이고 그 뒤 제품 파일이 그대로면 그 OK 를 그대로 낸다.
        last = ran[-1]
        if last.get("state") == "ok" and last.get("product") == start_print and last.get("map") == map_fp():
            result.update(state="ok", reason="", target=last.get("target"), reused_round=last.get("round"))
        else:
            result.update(state="incomplete", reason=f"재검증 한도({rounds_max})에 이미 닿았다. 새 검증자를 띄우지 않는다(사용자의 새 승인 뒤에만 새로 시작)")
        rounds.append({"uid": os.urandom(8).hex(), "round": n, "state": result["state"], "reason": result["reason"], "ran": False, "at": time.time()})
    else:
        # 증거 폴더: 정해진 상위 폴더(--keep, 평가는 --log 옆 .round, 기본은 관문 기록의 verify/task-<id>) 안에 이 회차만의 새 하위 폴더를
        # 만든다. 이미 있는 폴더·파일(앞선 승인 시도의 증거, --keep 에 있던 사용자 파일)은 지우거나 덮지 않는다.
        parent = Path(opt(args, "--keep") or (Path(opt(args, "--log")).with_suffix(".round") if opt(args, "--log") else
                                               (Path(root, rec_file).parent / "verify" if rec_file else (Path(root, "work", "review") if not explicit else Path(tempfile.gettempdir())))))
        parent.mkdir(parents=True, exist_ok=True)
        keep = Path(tempfile.mkdtemp(prefix=f"round-{n}-", dir=parent))
        result["kept"] = str(keep)  # 이 회차의 고정 대상(git 저장소)·시작 상태·diff·입력·판정을 지우지 않고 남긴다
        # 승인 뒤 바뀐 기준: 승인한 기준만 판정 기준이다. 바뀌었으면 검증자에게 알린다.
        note, changed = "", False
        if explicit:
            current = baseline(root)
            changed = current.strip() != criteria.strip()
        elif not rec_file:  # 지도 없는 승인: 승인받은 계획은 관문이 고정했으므로 바뀔 기준이 없다
            changed, current = False, ""
        else:
            now = gate.maps(root)
            changed = bool(rec) and now.get(rec_file) != rec.get("targets", {}).get(rec_file)
            current = (section(Path(root, rec_file).read_text(encoding='utf-8', errors='replace')) if Path(root, rec_file).is_file() else None) or "(기준 절 없음)"
        if changed:
            note = f"\n주의: 구현자가 승인 뒤 작업 지도의 기준을 바꿨다. 바뀐 기준은 사용자가 승인한 것이 아니므로 판정 기준으로 쓰지 않는다. 지금 지도의 기준:\n{current or '(없음)'}\n"
        result["baseline_changed_after_approval"] = changed
        if not requests:
            problems.append("사용자 원문이 없다")
        vdir = keep / "target"
        try:
            target = freeze(root, vdir)
        except RuntimeError as e:  # 고정 대상이 없으면 검증자를 띄우지 않고 미확인(남긴 폴더에 그대로 둔다)
            target = None
            problems.append(str(e))
            vdir.mkdir(parents=True, exist_ok=True)
        base = keep / "base"
        unsaved = []
        if opt(args, "--base-dir"):
            shutil.copytree(opt(args, "--base-dir"), base, symlinks=True)
        elif rec.get("base") and (state_dir / rec["base"]).is_file():
            unsaved = materialize_base(root, state_dir / rec["base"], base)
        else:
            problems.append("작업 시작 파일 상태가 없어 이번 변경만 가려낼 수 없다")
            base.mkdir()
        copy_kit_paths(vdir, base)
        change, cut, failed = diff(base, vdir)
        # 근거가 불완전하면(시작 내용 미보존·diff 실패·잘림) 판정을 맡기지 않고 미확인이다. 전체 diff 는 남긴 폴더에 있다.
        if unsaved:
            problems.append("작업 시작 때 내용을 보존하지 못한 경로가 있다: " + ", ".join(unsaved[:20]))
        if failed:
            problems.append("diff 실행이 실패했다")
        if cut:
            problems.append(f"변경(diff)이 {DIFF_LIMIT} 바이트를 넘어 검증자 입력에 다 넣지 못했다(전체는 {keep / 'diff.txt'})")
        result.update(target=target, diff_truncated=cut)
        (keep / "criteria.txt").write_text(criteria, encoding="utf-8")
        (keep / "requests.json").write_text(json.dumps(requests, ensure_ascii=False), encoding="utf-8")
        if problems:
            result.update(state="unverified", reason=" / ".join(problems))
            rounds.append({"uid": os.urandom(8).hex(), "round": n, "state": "unverified", "reason": result["reason"], "target": target, "ran": False, "kept": str(keep), "at": time.time()})
        else:
            prompt = prompt_text(requests, plan, conditions, criteria, note, target, change, vdir)
            (keep / "prompt.txt").write_text(prompt, encoding="utf-8")
            pending = {"explicit": explicit, "rec_file": rec_file, "state_dir": str(state_dir) if state_dir else None,
                       "state_file": str(state_file) if explicit else str(vfile), "approved_at": rec.get("approved_at"), "required": required,
                       "rounds_max": rounds_max, "round": n, "ran_before": len(ran), "start_print": start_print, "start_task": list(start_task),
                       "target": target, "vdir": str(vdir), "harness": harness, "baseline_changed": changed, "root": str(root)}
            (keep / "pending.json").write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")
            ready = {"state": "ready", "round": n, "kept": str(keep), "prompt_file": str(keep / "prompt.txt"), "target_dir": str(vdir),
                     "finish": f"python3 {Path(__file__).resolve()} finish --round {keep}"}
            print(f"[verify] 검토 입력을 만들었다({n}회차). prompt_file 을 하위 에이전트(검토자)에게 그대로 넘기고, 그 마지막 답을 "
                  f"표준 입력으로 finish 명령에 넘긴다.", file=sys.stderr)
            print(json.dumps(ready, ensure_ascii=False))
            return 0
        (keep / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return finalize(result, rounds, rounds_max, explicit, state_file if explicit else vfile, rec, rec_file, state_dir, root, gate)


def finalize(result, rounds, rounds_max, explicit, state_path, rec, rec_file, state_dir, root, gate):
    """회차 기록을 남기고 완료 판정과 함께 결과를 낸다(prepare 의 조기 종료와 finish 가 같은 함수를 쓴다)."""
    vstate = {"rounds": rounds, "state": result["state"], "reason": result.get("reason", ""), "max_rounds": rounds_max}
    if state_path:
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(state_path).write_text(json.dumps({**vstate, "approved_at": (rec or {}).get("approved_at")} if not explicit else vstate, ensure_ascii=False))
    now_rec = (gate.approved_record(root, Path(state_dir), rec_file) or {}) if rec_file and state_dir else {}
    waiting = bool(rec_file) and gate.status_json(now_rec)["waiting"]
    # 독립 검토 결과의 완료 판정: 직접 증거는 구현자 몫이므로 충족(PASS)을 전제로, 검토가 필수인 경우로 계산한다.
    result["completion"] = completion(result["state"], "PASS", waiting, required=True)
    msg = {"ok": "완료: 독립 검토가 모든 조건 충족을 냈다(직접 증거의 충족은 구현자가 따로 보고한다).",
           "returned": "돌려보냄: 사유를 원문·승인된 기준과 대조한다. 근거로 정할 수 있는 결함이면 원인 자리를 고친 뒤 prepare 부터 다시, 사용자 결정이 필요한 미정이면 추천과 함께 사용자에게 묻는다.",
           "incomplete": "미완료: 재검증 한도에 닿았다. 남은 조건과 사유를 사용자에게 보고한다.",
           "unverified": "미확인: 판정하지 못했다. 완료로 보고하지 않고 사유와 재개 조건을 보고한다."}[result["state"]]
    if result["completion"] == "waiting-user":
        msg += " 다만 이 작업은 사용자 답을 기다리는 중이라 완료가 아니다."
    print(f"[verify] {msg} ({result['round']}회차, 한도 {rounds_max}) {result.get('reason', '')}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    return EXIT[result["state"]]


def finish(args):
    """검토자의 마지막 답을 판정한다. --answer 파일(평가는 하네스 기록 .jsonl)이나 표준 입력. 대상 폴더가 바뀌었거나 검토하는 동안
    승인·지도 기준·제품 파일이 바뀌었으면 미확인. --exit-code 는 평가 실행기가 넘기는 검토자 하네스 종료 코드(none = 하네스 없음)."""
    keep = Path(opt(args, "--round") or "")
    if not (keep / "pending.json").is_file():
        print(USAGE, file=sys.stderr)
        return 2
    pd = json.loads((keep / "pending.json").read_text(encoding="utf-8"))
    if (keep / "result.json").is_file():
        print("[verify] 이 회차는 이미 판정했다. prepare 로 새 회차를 만든다.", file=sys.stderr)
        print((keep / "result.json").read_text(encoding="utf-8").strip().replace("\n", " "))
        return EXIT[json.loads((keep / "result.json").read_text(encoding="utf-8"))["state"]]
    gate = gate_module()
    root, rec_file = Path(pd["root"]), pd["rec_file"]
    state_dir = Path(pd["state_dir"]) if pd["state_dir"] else None
    src = opt(args, "--answer")
    raw = Path(src).read_text(encoding="utf-8", errors="replace") if src else sys.stdin.read()
    answer = final_answer(src) if src and src.endswith(".jsonl") else raw
    (keep / "answer.txt").write_text(answer, encoding="utf-8")
    rc_arg = opt(args, "--exit-code")
    rc = None if rc_arg == "none" else int(rc_arg or 0)
    vdir, n, rounds_max = Path(pd["vdir"]), pd["round"], pd["rounds_max"]
    result = {"round": n, "max_rounds": rounds_max, "harness": pd["harness"], "required": pd["required"], "kept": str(keep),
              "target": pd["target"], "baseline_changed_after_approval": pd["baseline_changed"]}
    touched = [l for l in run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=vdir).stdout.decode().splitlines()
               if l and not l.startswith("??")]
    verdict = judge(answer, pd["required"])
    result.update(conditions=verdict.get("conditions", []), out_of_scope=verdict.get("out_of_scope", []), verifier_exit_code=rc, final=answer)
    if rc is None:
        result.update(state="unverified", reason=f"검토 하네스({pd['harness']})를 찾지 못했다. 설치·로그인된 하네스가 있으면 다시 실행한다")
    elif rc != 0:
        result.update(state="unverified", reason=f"검토자 하네스 종료 코드 {rc}. 재개 조건: 검토자를 띄울 수 있는 환경에서 prepare 부터 다시 실행한다")
    elif touched:
        result.update(state="unverified", reason="검토자가 판정 대상의 추적 파일을 바꿨다: " + " ".join(touched[:5]))
    elif verdict["state"] == "returned" and pd["ran_before"] + 1 >= rounds_max:
        result.update(state="incomplete", reason=f"재검증 한도({rounds_max})에 닿았다: 마지막 판정 RETURN")
    else:
        result.update(state=verdict["state"], reason=verdict.get("reason", ""))
    rec = (gate.approved_record(root, state_dir, rec_file) or {}) if rec_file and state_dir else {}
    map_fp = gate.maps(root).get(rec_file) if rec_file else None
    end_task = [rec.get("approved_at"), json.dumps(rec.get("targets", {}), sort_keys=True), rec.get("approved"), map_fp] if rec_file else pd["start_task"]
    if rc is not None and (end_task != pd["start_task"] or product_print(gate, root) != pd["start_print"]):
        result.update(target_state=result["state"], state="unverified",
                      reason="검토하는 동안 승인·지도 기준·제품 파일이 바뀌었다. 고정 대상의 판정은 남겼지만 지금 버전의 결과가 아니다")
    state_path = Path(pd["state_file"]) if pd["state_file"] else None
    vstate = json.loads(state_path.read_text()) if state_path and state_path.is_file() else {}
    if not pd["explicit"] and vstate.get("approved_at") != pd["approved_at"]:
        vstate = {}  # 앞선 승인의 회차와 섞지 않는다
    rounds = list(vstate.get("rounds", []))
    rounds.append({"uid": os.urandom(8).hex(), "round": n, "state": result["state"], "target_state": result.get("target_state"), "reason": result.get("reason", ""),
                   "target": pd["target"], "product": pd["start_print"], "map": pd["start_task"][3], "verifier_exit_code": rc, "ran": rc is not None,
                   "kept": str(keep), "at": time.time()})
    (keep / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return finalize(result, rounds, rounds_max, pd["explicit"], state_path, rec or {"approved_at": pd["approved_at"]}, rec_file, state_dir, root, gate)


def cli(args):
    """명시 명령의 오류 정책: 예상하지 못한 실패도 0 으로 감추지 않는다. 미확인(5)과 사유를 표준 오류·JSON 으로 낸다."""
    try:
        return main(args)
    except Exception as e:
        print(f"[verify] 오류: 판정하지 못했다(미확인, 완료 아님): {e!r}", file=sys.stderr)
        print(json.dumps({"state": "unverified", "reason": f"검증 실행기 오류: {e!r}", "completion": "unverified"}, ensure_ascii=False))
        return EXIT["unverified"]


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
