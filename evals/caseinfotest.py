"""판정기 지문(caseinfo.py) 회귀 시험. 모델 없이 실행한다.

- 판정 관련 파일(사례 check.py·공용 판정 파일)을 하나씩 바꾸면 지문이 바뀌고, 되돌리면 원래 값으로 돌아온다.
- 하나라도 없으면 지문을 내지 않는다(함수는 예외, 명령은 종료 1).
- cases 에 없는 사례는 holdout 에서 찾고, 그 check.py 도 지문에 들어간다.
- 재판정(rejudge.py)은 판정 파일이 빠지면 meta 를 고치지 않고(이력·원시 기록 보존) 종료 1 로 알린다.
- 인자로 실행 결과 폴더를 주면, 그 안의 각 meta 를 재판정해 실행 때 지문과 같은지 본다(같은 코드 → 같은 지문).

사용: python3 -I evals/caseinfotest.py [실행 결과 폴더 ...]
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
KIT = EVALS.parent
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok  ", name)
    else:
        failed += 1
        print("FAIL", name, detail)


def fp(kit, case_dir):
    r = subprocess.run([sys.executable, "-I", str(kit / "evals/caseinfo.py"), "version", str(case_dir)], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


with tempfile.TemporaryDirectory() as tmp:
    kit = Path(tmp) / "kit"
    sys.path.insert(0, str(EVALS))
    from caseinfo import JUDGE_FILES
    for rel in ("evals/caseinfo.py", "evals/rejudge.py", *JUDGE_FILES):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(KIT / rel, kit / rel)
    case = kit / "evals/cases/zz-case"; case.mkdir(parents=True)
    (case / "check.py").write_text('print("PASS 시험")\n')
    hold = kit / "evals/holdout/zz-hold"; hold.mkdir(parents=True)
    (hold / "check.py").write_text('print("PASS holdout 사례")\n')

    where = subprocess.run([sys.executable, "-I", str(kit / "evals/caseinfo.py"), "path", "zz-hold"], capture_output=True, text=True).stdout.strip()
    check("cases 에 없는 사례는 holdout 경로로 정한다", Path(where).resolve() == hold.resolve(), where)

    rc, base, _ = fp(kit, case)
    check("정상 지문은 12자리", rc == 0 and len(base) == 12, base)
    check("같은 파일이면 지문이 같다", fp(kit, case)[1] == base)
    rc_h, hbase, _ = fp(kit, hold)
    check("holdout 사례도 지문을 만든다", rc_h == 0 and len(hbase) == 12 and hbase != base, hbase)

    for target, case_dir, original in [(case / "check.py", case, base), (hold / "check.py", hold, hbase)] + \
                                      [(kit / rel, case, base) for rel in JUDGE_FILES]:
        name = target.relative_to(kit)
        saved = target.read_bytes()
        target.write_bytes(saved + b"\n# changed\n")
        changed = fp(kit, case_dir)[1]
        target.write_bytes(saved)
        check(f"{name} 가 바뀌면 지문이 바뀐다", changed not in ("", original), changed)
        check(f"{name} 를 되돌리면 지문이 돌아온다", fp(kit, case_dir)[1] == original)
        target.unlink()
        rc, out, err = fp(kit, case_dir)
        target.write_bytes(saved)
        check(f"{name} 가 없으면 지문을 내지 않는다(종료 1, 빠진 파일 표시)", rc == 1 and out == "" and str(name) in err, f"rc={rc} out={out} err={err}")

    # 재판정: 판정 파일이 빠지면 meta 를 그대로 두고 실패로 알린다.
    res = Path(tmp) / "results"; res.mkdir()
    meta = {"case": "zz-hold", "exit_code": 0, "check_passed": True, "check_output": "PASS 이전", "judge_version": "old000000000",
            "rejudge_history": [{"verdict": "FAIL", "judge_version": "older0000000"}]}
    mpath = res / "zz-hold-x-claude-1.meta.json"; mpath.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    (res / "zz-hold-x-claude-1.jsonl").write_text("")
    raw = mpath.read_bytes()
    lost = kit / "evals/fixtures/login_app.py"; saved = lost.read_bytes(); lost.unlink()
    r = subprocess.run([sys.executable, "-I", str(kit / "evals/rejudge.py"), str(res)], capture_output=True, text=True)
    lost.write_bytes(saved)
    check("재판정: 판정 파일이 빠지면 종료 1 과 사유", r.returncode == 1 and "login_app.py" in r.stderr, f"rc={r.returncode} {r.stderr}")
    check("재판정: 판정 파일이 빠지면 meta·이력을 고치지 않는다", mpath.read_bytes() == raw)
    r = subprocess.run([sys.executable, "-I", str(kit / "evals/rejudge.py"), str(res)], capture_output=True, text=True)
    m = json.loads(mpath.read_text())
    check("재판정: 파일이 있으면 새 지문을 쓰고 이전 지문·판정을 이력 끝에 보탠다",
          r.returncode == 0 and m["judge_version"] == hbase and [h["judge_version"] for h in m["rejudge_history"]] == ["older0000000", "old000000000"]
          and m["rejudge_history"][-1]["verdict"] == "PASS", f"rc={r.returncode} {r.stderr} {m}")

# 실제 실행 결과: 실행 때 기록한 지문과 같은 코드로 재판정한 지문이 같아야 한다.
for root in sys.argv[1:]:
    metas = sorted(Path(root).rglob("*.meta.json"))
    check(f"{root}: 실행 결과 meta 가 있다", bool(metas))
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "r"; shutil.copytree(root, copy, symlinks=True)
        before = {p.relative_to(copy): json.loads(p.read_text())["judge_version"] for p in copy.rglob("*.meta.json")}
        r = subprocess.run([sys.executable, "-I", str(EVALS / "rejudge.py"), str(copy)], capture_output=True, text=True)
        for rel, v in before.items():
            m = json.loads((copy / rel).read_text())
            check(f"{rel.name}: 실행 지문 = 재판정 지문", r.returncode == 0 and m.get("rejudged") and m["judge_version"] == v,
                  f"rc={r.returncode} run={v} rejudge={m.get('judge_version')} {r.stderr[-300:]}")

print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
