"""평가 실행기가 쓰는 판정 함수와 검토 세션. 판정 규칙(judge·completion)은 설치되는 검토 도구(.agents/skills/wf-verify/verify.py)의
함수를 그대로 쓴다(일반 설치와 평가가 같은 규칙을 쓰게 하려는 것이다). 하네스 기록을 읽는 일과 검토 한 회차를 돌리는 일은 평가만 하므로 여기에 있다.
검토자 세션을 띄우는 명령(두 하네스의 차이)은 session.py 의 어댑터가 맡는다.

검증자는 답 끝에 JSON 하나를 쓴다(verify.py 의 VERIFIER_PROMPT 형식):
  {"verdict": "OK" 또는 "RETURN", "conditions": [{"id": "C1", "result": "충족|미충족|미확인", "evidence": "..."}],
   "return_reason": "...", "out_of_scope": ["..."]}
판정(state): ok / returned / unverified(그 밖 전부, 완료 아님). out_of_scope 는 판정을 막지 않고 따로 남긴다.

사용:
  python3 -I evals/verdict.py session --tool <verify.py> --harness claude|codex [--log <기록>] <prepare 인자 ...>
      → 평가용 검토 한 회차: 설치된 도구를 사용자와 같은 옵션으로 불러 입력을 묶고(prepare), 이 파일이 검토자 하네스 세션을 띄운 뒤,
        그 마지막 답을 도구의 표준 입력으로 넘겨 판정(finish)한다. --map 을 주지 않으면 `## 기준` 이 있는 작업 지도(work/*/work.md)가 하나일 때 그것을 쓴다(여러 개면 미확인).
        마지막 줄이 결과 JSON. 하네스가 없거나 실패하면 finish 를 부르지 않고 미확인을 낸다(검토자 답이 없다).
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session import HARNESSES

_spec = importlib.util.spec_from_file_location("awk_verify", Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify/verify.py")
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)
last_json, judge, completion, ids, EXIT = _verify.last_json, _verify.judge, _verify.completion, _verify.ids, _verify.EXIT


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
    """세션이 실행한 명령의 출력에서 검토 도구가 찍는 결과를 찾는다. 도구의 출력은 표준 오류의 `[verify] ` 줄과, 맨 끝 한 줄의 결과 JSON
    (state 가 판정 상태이고 completion 이 있음)뿐이고, 종료 코드는 그 state 의 EXIT 값이다.
    저장된 result.json도 같은 형식이므로, 실제 명령 실행인지의 구분은 호출 기록을 가진 평가 관찰(observe.py)이 맡는다.
    돌려줌: (결과 객체 또는 None, 이번 실행의 결과로 볼 수 없는 사유 또는 ""). 다른 글이 섞였거나(예: 스크립트와 저장해 둔 출력을 함께 cat)
    종료 코드가 결과의 state 와 맞지 않으면 그 결과를 이번 실행의 판정으로 쓰지 않는다."""
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


def session(args):
    opt = lambda name: args[args.index(name) + 1] if name in args[:-1] else None
    tool, harness, log = opt("--tool"), opt("--harness"), opt("--log")
    rest, skip = [], {"--tool", "--harness", "--log"}
    it = iter(args)
    for a in it:
        if a in skip:
            next(it, None)
        else:
            rest.append(a)
    unverified = lambda reason, **more: print(json.dumps({"state": "unverified", "reason": reason, "completion": "unverified", **more}, ensure_ascii=False)) or EXIT["unverified"]
    if "--map" not in rest:
        maps = sorted(str(p) for p in Path("work").glob("*/work.md") if p.is_file() and _verify.criteria_text(p.read_text(encoding="utf-8", errors="replace")))
        if len(maps) > 1:
            return unverified("작업 지도가 여러 개라 검토할 지도를 정할 수 없다: " + ", ".join(maps))
        rest += ["--map", maps[0]] if maps else []
    r = subprocess.run([sys.executable, "-I", tool, "prepare", *rest], capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    if out.get("state") != "ready":  # 한도·근거 불완전 등으로 prepare 가 최종 결과를 냈다
        print(json.dumps(out, ensure_ascii=False)); return r.returncode
    keep = Path(out["kept"]); vlog = keep / "verify.jsonl"
    # 검토자 세션을 판정 대상 폴더에서 띄운다. 종료 코드, 하네스가 없으면 None.
    rc = HARNESSES[harness]().review(out["target_dir"], Path(out["prompt_file"]).read_text(encoding="utf-8"), vlog) if harness in HARNESSES else None
    if log:  # --log 는 최신 회차 기록의 복사본(원시 기록은 회차 폴더에 그대로 있다)
        for src, dst in ((vlog, Path(log)), (Path(str(vlog) + ".err"), Path(log + ".err"))):
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    seen = {"round": out.get("round"), "kept": str(keep), "log": str(vlog), "verifier_exit_code": rc}
    if rc is None:
        return unverified(f"검토 하네스({harness})를 찾지 못했다. 설치·로그인된 하네스가 있으면 다시 실행한다", **seen)
    if rc != 0:
        return unverified(f"검토자 하네스 종료 코드 {rc}. 재개 조건: 검토자를 띄울 수 있는 환경에서 prepare 부터 다시 실행한다", **seen)
    f = subprocess.run([sys.executable, "-I", tool, "finish", "--round", str(keep)], input=final_answer(vlog), capture_output=True, text=True)
    sys.stderr.write(f.stderr)
    res = json.loads(f.stdout.strip().splitlines()[-1]) if f.stdout.strip() else {"state": "unverified", "reason": "finish 결과 없음"}
    res.update(log=str(vlog), verifier_exit_code=rc)
    print(json.dumps(res, ensure_ascii=False))
    return f.returncode


def snapshot(project):
    """지금 작업 트리(추적 파일과 무시되지 않은 새 파일)를 가지·index 를 건드리지 않고 커밋 하나로 남긴다. 검토의 기준 커밋(--base)으로 쓴다."""
    index = Path(tempfile.mkdtemp()) / "index"
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    git = lambda *a: subprocess.run(["git", "-c", "user.name=evals", "-c", "user.email=evals@invalid", "-c", "commit.gpgsign=false", *a],
                                    cwd=project, env=env, capture_output=True, text=True, check=True).stdout.strip()
    try:
        git("add", "-A")
        return git("commit-tree", git("write-tree"), "-m", "evals: 작업 시작 상태")
    finally:
        shutil.rmtree(index.parent, ignore_errors=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "session":
        sys.exit(session(sys.argv[2:]))
    if cmd == "snapshot":
        print(snapshot(sys.argv[2]))
