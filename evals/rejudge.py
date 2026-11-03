"""판정 검사를 고친 뒤, 이미 실행한 결과를 현재 check.py 로 다시 판정해 .meta.json 을 갱신한다.

실행 결과 폴더의 원시 기록(.jsonl), 끝난 프로젝트(.files), 마지막 턴 직전 상태(.before-last)를 그대로 쓴다.
하네스가 실패한 실행은 다시 판정하지 않는다. 바뀐 판정은 화면에 보여 주고, 이전 판정·이전 전체 완료(completion)는 meta 의
rejudge_history 에 남기며 쓴 검사 파일의 지문(check_sha)을 함께 기록한다. 전체 완료는 최초 실행과 같은 규칙(verdict.completion)으로
그때의 검증 상태(verifier)와 새 판정에서 다시 계산한다(검증자 OK 여도 새 판정이 FAIL 이면 check-failed).

사용: python3 -I evals/rejudge.py evals/results/<폴더> [...]
"""
import json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verdict import completion

cases = Path(__file__).resolve().parent / "cases"
for root in sys.argv[1:]:
    for meta_path in sorted(Path(root).rglob("*.meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        if m["exit_code"] != 0:
            continue
        base = str(meta_path)[: -len(".meta.json")]
        env = dict(os.environ)
        env["EVALS_BEFORE_LAST_TURN"] = base + ".before-last"
        # 실행 때와 같은 판정 조건을 복원한다. 예전 meta 에 없으면 남긴 파일에서 추정한다:
        # 관문은 프로젝트 설정의 approval-gate.py 등록, 입력은 사례의 prompt 수보다 실행한 턴이 많으면 승인 추가로 본다.
        settings = Path(base + ".files/.claude/settings.json")
        gate = m.get("approval_gate", settings.is_file() and "approval-gate.py" in settings.read_text(encoding="utf-8"))
        prompts = len(list((cases / m["case"]).glob("prompt*.txt")))
        ran = len(list(Path(base).parent.glob(Path(base).name + ".t*.jsonl")))
        env["EVALS_GATE"] = "true" if gate else "false"
        env["EVALS_INPUT"] = m.get("input", "with-approval" if ran > prompts else "original")
        env["EVALS_LANG"] = m.get("lang") or ""
        r = subprocess.run([sys.executable, "-I", str(cases / m["case"] / "check.py"), base + ".files", base + ".jsonl"],
                           capture_output=True, text=True, env=env)
        out = (r.stdout + r.stderr).strip()
        old = "PASS" if m["check_passed"] else ("REVIEW" if m.get("check_needs_review") else ("UNVERIFIED" if m.get("check_unverified") else "FAIL"))
        new = {0: "PASS", 2: "REVIEW", 1: "FAIL"}.get(r.returncode, "UNVERIFIED")
        if not out.startswith(new):  # 판정 검사 자체의 오류(예외 등)는 실패가 아니라 미확인이다
            new = "UNVERIFIED"
        if old != new:
            print(f"{Path(base).name}: {old} -> {new}  {out[:120]}")
        import hashlib
        check_hash = hashlib.sha256((cases / m["case"] / "check.py").read_bytes()).hexdigest()[:12]
        # 원시 기록(.jsonl·.files)은 바꾸지 않는다. 이전 판정과 그때의 판정기 지문을 이력으로 남기고 새 지문을 기록한다.
        here = Path(__file__).resolve().parent
        judge_version = hashlib.sha256(b"".join(hashlib.sha256(f.read_bytes()).digest() for f in
                                               [cases / m["case"] / "check.py"] + [here / n for n in ("judge.py", "observe.py", "transcript.py", "verdict.py")] if f.is_file())).hexdigest()[:12]
        m.setdefault("rejudge_history", []).append({"verdict": old, "check_output": m.get("check_output", ""), "completion": m.get("completion"),
                                                    "judge_version": m.get("judge_version"), "check_sha": m.get("check_sha")})
        if "verifier" in m:  # 검증 루프가 있던 실행만 완료를 다시 계산한다(예전 결과에는 검증 상태가 없다)
            m["completion"] = completion(m["verifier"], new)
        m.update(check_passed=new == "PASS", check_needs_review=new == "REVIEW", check_unverified=new == "UNVERIFIED", check_output=out, rejudged=True, check_sha=check_hash,
                 judge_version=judge_version)
        meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
