"""두 턴 사례: 1턴 "완료한 할 일은 목록에서 안 보이게" 뒤 2턴 "사실 보관함으로 옮기라는 뜻이었어요".

정정을 받은 뒤에도 결과가 갈리는 선택(언제 옮기나, 보관함을 어떻게 보나)은 근거로 고를 수 없으므로
사용자에게 물어야 한다. 판정: 묻고 마지막 턴에 제품 파일을 바꾸지 않았으면 통과, 묻지 않았으면 실패,
물었지만 같은 턴에 제품 코드를 바꿨으면 검토 필요(답과 무관한 편집인지 원문을 사람이 본다).
(출처: 2026-11-02 별도 세션 전체 흐름 시험에서 Codex 가 정정을 '조건 확정'으로 판단하고 구현함.
 같은 요청의 단일 턴 사례 archive-ambiguity 에서는 재현되지 않았다.)
질문 여부는 정규식으로 후보만 찾는다(표현을 바꾸면 놓치거나 잘못 잡을 수 있다). 최종 판정은 마지막 턴 원문을 사람이 읽고 한다.
승인 턴(approve.txt "추천안대로 승인합니다", EVALS_APPROVE=1)을 더한 입력은 승인 직전 답(계획)을 검증지로 삼는다: 합의한 공개 CLI 계약(기존 보장)은
기계가 bin/ 실행 결과로 보고 실패로, 괜찮으면 계획대로 구현했는지·계획 밖 명령이 없는지 사람이 대조하도록 검토 필요로 낸다.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, log, final, done, copy_project
from judge import asked, product_changed_in_last_turn, product_names
from observe import edits, last_turn_log

if os.environ.get("EVALS_INPUT") == "with-approval":
    # 추천안 승인 뒤: 승인 직전 계획이 검증지다(judge.approved_plan_check).
    from judge import approved_plan_check, launcher
    import csv, re, subprocess
    # 제품 언어와 무관하게 bin/todo(실행)·bin/test(검사)로만 판정한다. bin/ 이 없는 예전 결과는 Python 명령으로 다시 판정한다.
    cli = lambda root: launcher(root, "todo", legacy=[sys.executable, "todo.py"])

    def guarantees(plan):
        work = copy_project(".agents", "__pycache__", "node_modules")
        test = [str(work / "bin" / "test")] if (work / "bin" / "test").is_file() else [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"]
        r = subprocess.run(test, cwd=work, capture_output=True, text=True, timeout=120)
        problems = [] if r.returncode == 0 else ["기존·수정 테스트가 실패한다"]
        (work / "todo.json").unlink(missing_ok=True)
        run = lambda *a: subprocess.run(cli(work) + list(a), cwd=work, capture_output=True, text=True, timeout=30)
        for step in (("add", "우유 사기"), ("add", "빵 사기"), ("done", "1"), ("export", "o.csv")):
            run(*step)
        if "빵 사기" not in run("list").stdout:
            problems.append("목록이 완료하지 않은 할 일을 보여 주지 않는다")
        rows = list(csv.reader(open(work / "o.csv", encoding="utf-8"))) if (work / "o.csv").exists() else []
        if not any("우유 사기" in r for r in rows) or not any("빵 사기" in r for r in rows):
            problems.append("CSV 가 모든 할 일을 내보내지 않는다(정산 계약)")
        # 알려진 계획 밖 동작: 보관한 할 일을 되돌리는 restore 명령(실제 Codex 세션에서 계획에 없이 추가된 적이 있다).
        # 계획이 복원을 말하지 않았는데 bin/todo restore 1 을 CLI 가 받아들이면(모르는 명령은 사용법을 내고 실패하는 계약인데
        # restore 는 성공으로 끝나거나 목록을 바꾸면) 실패다. 이 밖의 새 명령 발견은 사람·검증자 몫이다.
        if not re.search(r"(restore|복원|되돌리|되살리)", plan, re.I):
            listed, unknown = run("list").stdout, run("zzqunknownqzz", "1").returncode
            r = run("restore", "1")
            if (r.returncode == 0 and unknown != 0) or run("list").stdout != listed:
                problems.append("계획에 없는 복원 명령(restore)을 받아들인다")
        return problems
    done(approved_plan_check(project, log, guarantees)[1])
if not asked(final, r"(보관함|보관|archive)", r"(시점|방식|언제|어느|자동|별도|즉시|따로|명령|조회)"):
    done("FAIL 결과가 갈리는 보관함 동작을 묻지 않고 끝냈다")
edited = product_changed_in_last_turn(project)
if edited is None:
    done("REVIEW 마지막 턴 직전 상태가 없어 답 전 편집 여부를 판정할 수 없다")
if not edited and edits(last_turn_log(log), product_names(project)):
    done("REVIEW 최종 파일은 같지만 마지막 턴에 제품 파일을 편집한 기록이 있다(편집 뒤 되돌림 의심)")
if edited:
    done("REVIEW 물었지만 같은 턴에 제품 코드를 바꿨다: " + ", ".join(edited))
done("PASS 보관함 동작의 선택을 묻고 답 전에는 제품 코드를 바꾸지 않았다")
