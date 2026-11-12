"""판정 검사를 고친 뒤, 이미 실행한 결과를 현재 check.py 로 다시 판정해 .meta.json 을 갱신한다.

실행 결과 폴더의 원시 기록(.jsonl), 끝난 프로젝트(.files), 마지막 턴 직전 상태(.before-last)를 그대로 쓴다.
하네스가 실패한 실행은 다시 판정하지 않는다. 바뀐 판정은 화면에 보여 주고, 이전 판정·이전 전체 완료(completion)는 meta 의
rejudge_history 에 남기며 쓴 검사 파일의 지문(check_sha)을 함께 기록한다. 전체 완료는 최초 실행이 보존한 completion_inputs와
새 직접 검사 결과로 계산한다. 예전 기록에 입력이 없으면 없는 미정·미확인을 False로 추정하지 않고 근거 부족을 표시한다.

사용: python3 -I evals/rejudge.py evals/results/<폴더> [...]
"""
import json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from result import check_verdict, check_word, rejudge_result
from transcript import turn_logs
from caseinfo import MissingJudgeFile, case_path, judge_version as judge_fingerprint  # 실행기(run.py)와 같은 사례 위치·지문

failed = []
for root in sys.argv[1:]:
    for meta_path in sorted(Path(root).rglob("*.meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        if m["exit_code"] != 0:
            continue
        base = str(meta_path)[: -len(".meta.json")]
        env = dict(os.environ)
        env["EVALS_BEFORE_LAST_TURN"] = base + ".before-last"
        # 실행 때와 같은 판정 조건을 복원한다. 예전 meta 에 입력이 없으면 남긴 파일에서 추정한다:
        # 사례의 prompt 수보다 실행한 턴이 많으면 승인 추가로 본다.
        prompts = len(list(case_path(m["case"]).glob("prompt*.txt")))
        ran = len(turn_logs(base + ".jsonl"))
        env["EVALS_INPUT"] = m.get("input", "with-approval" if ran > prompts else "original")
        env["EVALS_LANG"] = m.get("lang") or ""
        # 판정 파일이 빠져 지문을 만들 수 없으면 이 meta 는 고치지 않고 실패로 알린다(빠진 파일을 뺀 지문을 쓰지 않는다).
        try:
            judge_version = judge_fingerprint(case_path(m["case"]))
        except MissingJudgeFile as e:
            print(f"{Path(base).name}: 다시 판정하지 않음: {e}", file=sys.stderr)
            failed.append(str(meta_path))
            continue
        r = subprocess.run([sys.executable, "-I", str(case_path(m["case"]) / "check.py"), base + ".files", base + ".jsonl"],
                           capture_output=True, text=True, env=env)
        out = (r.stdout + r.stderr).strip()
        old = check_verdict(m)
        new = check_word(r.returncode, out)  # 판정 검사 자체의 오류(예외 등)는 실패가 아니라 미확인이다
        if old != new:
            print(f"{Path(base).name}: {old} -> {new}  {out[:120]}")
        import hashlib
        check_hash = hashlib.sha256((case_path(m["case"]) / "check.py").read_bytes()).hexdigest()[:12]
        # 원시 기록(.jsonl·.files)은 바꾸지 않는다. 이전 판정과 그때의 판정기 지문을 이력으로 남기고 새 지문을 기록한다.
        previous_completion = m.get("completion")
        m = rejudge_result(m, new, out, judge_version, check_hash)
        if previous_completion != m["completion"]:
            reason = " (완료 근거 부족)" if m["completion_inputs_missing"] else ""
            print(f"{Path(base).name}: completion {previous_completion} -> {m['completion']}{reason}")
        meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
if failed:
    sys.exit(1)
