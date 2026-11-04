"""평가 실행기가 쓰는 판정 함수. 실제 내용은 설치되는 독립 검증 실행기(.agents/skills/wf-verify/verify.py)에 있고,
이 파일은 그 함수를 그대로 내보낸다(일반 설치와 평가가 같은 판정 규칙을 쓰게 하려는 것이다).

검증자는 답 끝에 JSON 하나를 쓴다(.agents/skills/wf-verify/verifier-prompt.txt 의 형식):
  {"verdict": "OK" 또는 "RETURN", "conditions": [{"id": "C1", "result": "충족|미충족|미확인", "evidence": "..."}],
   "return_reason": "...", "out_of_scope": ["..."]}
판정(state): ok / returned / unverified(그 밖 전부, 완료 아님). out_of_scope 는 판정을 막지 않고 따로 남긴다.

사용:
  python3 -I evals/verdict.py judge <검증자 기록 .jsonl> [필수 조건 ID ...]   → 판정 JSON 한 줄
  python3 -I evals/verdict.py baseline <프로젝트>                              → 작업 지도들의 `## 기준` 절(검증자에게 넘길 합의 조건)
  python3 -I evals/verdict.py completion <검증 상태> <PASS|REVIEW|FAIL|UNVERIFIED> [waiting] → 전체 완료 판정
  python3 -I evals/verdict.py ids <파일>                                       → 파일에 적힌 조건 ID(표의 첫 칸 또는 줄 머리)
  python3 -I evals/verdict.py session --tool <verify.py> --harness claude|codex [--log <기록>] <prepare 인자 ...>
      → 평가용 검토 한 회차: 설치된 실행기로 입력을 묶고(prepare), 이 파일이 검토자 하네스 세션을 띄운 뒤, 실행기로 판정(finish)한다.
        검토자 세션을 띄우는 일은 평가 실행기 몫이다(일반 작업은 하네스의 하위 에이전트가 검토자다). 마지막 줄이 finish 결과 JSON.
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("awk_verify", Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify/verify.py")
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)
last_json, judge, completion, baseline, ids, final_answer, run_result = (_verify.last_json, _verify.judge, _verify.completion, _verify.baseline,
                                                                         _verify.ids, _verify.final_answer, _verify.run_result)



def call_harness(harness, vdir, prompt, log):
    """검토자 세션을 판정 대상 폴더에서 띄운다. 돌려줌: 종료 코드(하네스가 없으면 None)."""
    exe = shutil.which(harness)
    if not exe:
        return None
    env = {k: v for k, v in os.environ.items() if k not in ("AWK_GATE_PROMPT_FROM", "AWK_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    if harness == "claude":
        cmd = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", "Read,Grep,Glob,Bash", "--max-turns", "30"]
    else:
        cmd = [exe, "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(vdir), prompt]
    with open(log, "wb") as out, open(str(log) + ".err", "ab") as err:
        try:
            return subprocess.run(cmd, cwd=vdir, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=env,
                                  timeout=int(os.environ.get("AWK_VERIFY_TIMEOUT", "900"))).returncode
        except subprocess.TimeoutExpired:
            return 124


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
    r = subprocess.run([sys.executable, "-I", tool, "prepare", "--reviewer", harness, *(("--log", log) if log else ()), *rest], capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    if out.get("state") != "ready":  # 한도·근거 불완전 등으로 prepare 가 최종 결과를 냈다
        print(json.dumps(out, ensure_ascii=False)); return r.returncode
    keep = Path(out["kept"]); vlog = keep / "verify.jsonl"
    rc = call_harness(harness, out["target_dir"], Path(out["prompt_file"]).read_text(encoding="utf-8"), vlog)
    if log:  # --log 는 최신 회차 기록의 복사본(원시 기록은 회차 폴더에 그대로 있다)
        for src, dst in ((vlog, Path(log)), (Path(str(vlog) + ".err"), Path(log + ".err"))):
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    f = subprocess.run([sys.executable, "-I", tool, "finish", "--round", str(keep), "--answer", str(vlog) if vlog.is_file() else os.devnull,
                        "--exit-code", "none" if rc is None else str(rc)], capture_output=True, text=True)
    sys.stderr.write(f.stderr)
    res = json.loads(f.stdout.strip().splitlines()[-1]) if f.stdout.strip() else {"state": "unverified", "reason": "finish 결과 없음"}
    res["log"] = str(vlog)
    print(json.dumps(res, ensure_ascii=False))
    return f.returncode


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "session":
        sys.exit(session(sys.argv[2:]))
    if cmd == "judge":
        print(json.dumps(judge(final_answer(sys.argv[2]) if Path(sys.argv[2]).is_file() else "", sys.argv[3:]), ensure_ascii=False))
    elif cmd == "baseline":
        print(baseline(sys.argv[2]))
    elif cmd == "completion":
        print(completion(sys.argv[2], sys.argv[3], len(sys.argv) > 4 and sys.argv[4] == "waiting"))
    elif cmd == "ids":
        print(" ".join(ids(Path(sys.argv[2]).read_text(encoding="utf-8") if Path(sys.argv[2]).is_file() else "")))
