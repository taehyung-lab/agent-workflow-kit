"""판정 검사를 고친 뒤, 이미 실행한 결과를 현재 check.py 로 다시 판정해 .meta.json 을 갱신한다.

실행 결과 폴더의 원시 기록(.jsonl), 끝난 프로젝트(.files), 마지막 턴 직전 상태(.before-last)를 그대로 쓴다.
하네스가 실패한 실행은 다시 판정하지 않는다. 바뀐 판정은 화면에 보여 주고, meta 에 rejudged 표시를 남긴다.

사용: python3 -I evals/rejudge.py evals/results/<폴더> [...]
"""
import json, os, subprocess, sys
from pathlib import Path

cases = Path(__file__).resolve().parent / "cases"
for root in sys.argv[1:]:
    for meta_path in sorted(Path(root).rglob("*.meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        if m["exit_code"] != 0:
            continue
        base = str(meta_path)[: -len(".meta.json")]
        env = dict(os.environ)
        env["EVALS_BEFORE_LAST_TURN"] = base + ".before-last"
        r = subprocess.run([sys.executable, "-I", str(cases / m["case"] / "check.py"), base + ".files", base + ".jsonl"],
                           capture_output=True, text=True, env=env)
        out = (r.stdout + r.stderr).strip()
        old = "PASS" if m["check_passed"] else ("REVIEW" if m.get("check_needs_review") else "FAIL")
        new = {0: "PASS", 2: "REVIEW"}.get(r.returncode, "FAIL")
        if old != new:
            print(f"{Path(base).name}: {old} -> {new}  {out[:120]}")
        m.update(check_passed=r.returncode == 0, check_needs_review=r.returncode == 2, check_output=out, rejudged=True)
        meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
