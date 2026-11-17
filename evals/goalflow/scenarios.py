"""판정기 사례 실행(모델 없음): 기대 판정이 정해진 대화(scenarios/*.json)를 가짜 하네스로 compare.py 끝까지 돌려, 판정기가 맞게 판정하는지 본다.

  python3 -I evals/goalflow/scenarios.py [키트 폴더 ...]

키트 폴더를 주지 않으면 이 저장소의 판정기를 돈다. 여러 폴더(다른 커밋의 worktree)를 주면 같은 사례로 판정기 버전을 나란히 비교한다.
사례는 기대 판정(expect)과 판정 이유에 들어 있어야 할 말(reason)을 함께 정한다: 낱말만 맞고 이유가 다르면(예: 절차 위반을 봐야 할 사례가
최종 동작 때문에 실패) "<낱말>?" 로 보이고 맞음에 세지 않는다.
보이는 것: 사례별 판정, 그리고 판정기마다 맞음·잘못된 통과(기대가 실패·검토 필요인데 통과)·잘못된 실패(기대가 통과·검토 필요인데 실패)·검토 필요 수.
"통과가 늘었나"가 아니라 "잘못 판정하는 일과 사람이 읽어야 하는 몫이 줄었나"를 보려는 것이다. 첫 판정기가 기대와 하나라도 다르면 종료 1.

가짜 하네스: 에이전트 역할은 사례의 턴마다 reply 를 내고 write(변이 이름)의 accounts.py 를 쓰며 commit 이면 커밋한다.
모의 사용자 분류 역할은 글에서 [Qn] 이 든 문장을 인용해 주제 n 을 드러낸 것으로 낸다(mock: broken 이면 형식이 틀린 답).
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORDS = ("PASS", "FAIL", "REVIEW", "UNVERIFIED")

FAKE = r'''#!/usr/bin/env python3
import json, os, re, shutil, subprocess, sys
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("fake 0"); sys.exit(0)
scen = json.load(open(os.environ["SCEN_FILE"]))
prompt = next((a for a in args if "에이전트의 글:" in a or "에이전트의 답:" in a), None)
if prompt is not None:  # 모의 사용자 분류(새 형식은 인용문, 옛 형식은 번호)
    if scen.get("mock") == "broken":
        print("형식이 틀린 답"); sys.exit(0)
    reply = prompt.split("<<<", 1)[1]
    found = {m.group(1): s.strip() for s in re.split(r"(?<=[?.])\s+", reply) for m in [re.search(r"\[Q(\d)\]", s)] if m}
    print(json.dumps({"quotes": {k: v for k, v in found.items()}} if "quotes" in prompt else {"asked": sorted(int(k) for k in found)}, ensure_ascii=False))
    sys.exit(0)
nf = os.environ["SCEN_N"]; n = int(open(nf).read()) + 1 if os.path.exists(nf) else 1; open(nf, "w").write(str(n))
turn = scen["turns"][n - 1] if n <= len(scen["turns"]) else {"reply": "마무리했습니다."}
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}))
if turn.get("shell_write"):  # 셸로 쓰고(편집 도구 호출 기록 없음) 같은 턴에 git checkout 으로 되돌린다
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"b{n}", "name": "Bash", "input": {"command": "cp variant.py accounts.py && git checkout accounts.py"}}]}}))
    shutil.copy(os.path.join(os.environ["SCEN_VARIANTS"], turn["shell_write"] + ".py"), "accounts.py")
    if turn.get("shell_revert"):
        subprocess.run(["git", "checkout", "--", "accounts.py"], capture_output=True)
if turn.get("failed_edit"):  # 고칠 문자열이 맞지 않아 실패한 Edit 호출: 파일은 그대로
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"e{n}", "name": "Edit", "input": {"file_path": os.path.abspath("accounts.py"), "old_string": "없는 문자열", "new_string": "x"}}]}}))
    print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"e{n}", "is_error": True, "content": "String to replace not found"}]}}))
for argv in turn.get("run", []):  # 재현: 앱·시험 실행(제품 파일을 쓰지 않는다)
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"x{n}", "name": "Bash", "input": {"command": "python3 " + " ".join(argv)}}]}}))
    subprocess.run([sys.executable, *argv], capture_output=True)
if turn.get("run"):
    assert os.path.exists("users.json"), "재현 명령이 자료 파일을 만들지 않았다: 사례가 재현을 시험하지 못한다"
for cmd in turn.get("shell", []):  # 셸 명령(도구 호출 기록은 Bash 하나)
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"s{n}", "name": "Bash", "input": {"command": cmd}}]}}))
    subprocess.run(cmd, shell=True, capture_output=True)
if turn.get("control"):  # 과제의 정답 구현(control/)을 그대로 쓴다
    for f in os.listdir(os.environ["SCEN_CONTROL"]):
        shutil.copy(os.path.join(os.environ["SCEN_CONTROL"], f), f)
if turn.get("garble_log"):  # 읽을 수 없는 기록 줄(대화 기록 손상)
    print("{not json")
if turn.get("write"):
    if turn.get("revert_in_turn"):
        keep = open("accounts.py", encoding="utf-8").read()
    shutil.copy(os.path.join(os.environ["SCEN_VARIANTS"], turn["write"] + ".py"), "accounts.py")
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"w{n}", "name": "Write", "input": {"file_path": os.path.abspath("accounts.py")}}]}}))
    if turn.get("revert_in_turn"):  # 같은 턴 안에서 되돌린다(턴 끝 상태는 시작과 같다)
        open("accounts.py", "w", encoding="utf-8").write(keep)
        print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"r{n}", "name": "Write", "input": {"file_path": os.path.abspath("accounts.py")}}]}}))
if turn.get("commit"):
    g = ["git", "-c", "user.name=a", "-c", "user.email=a@invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(g + ["add", "-A"], capture_output=True); subprocess.run(g + ["commit", "-qm", "agent"], capture_output=True)
print(json.dumps({"type": "result", "result": turn["reply"]}, ensure_ascii=False))
sys.exit(turn.get("exit", 0))
'''


def variants(task_dir, out):
    """control/accounts.py 로 만드는 변이: control(원문 정책), partial(되살리기 없음), other(비밀번호를 다시 받아야 되살림),
    other_same_text(다른 정책인데 인자가 모자라면 모르는 명령과 같은 출력·종료 코드), fixture(시작 상태)."""
    control = (task_dir / "control/accounts.py").read_text(encoding="utf-8")
    reactivate = '    elif cmd == "reactivate":\n        return set_active(users, args[0], True)\n'
    usage = "  python3 accounts.py reactivate <아이디>           비활성 계정을 되살린다\n"
    assert reactivate in control and usage in control, "control/accounts.py 의 모양이 바뀌었다: 변이를 다시 정한다"
    guarded = lambda body: '    elif cmd == "reactivate":\n        if len(args) < 2:\n' + body + '        return set_active(users, args[0], True)\n'
    made = {"control": control, "partial": control.replace(reactivate, "").replace(usage, ""),
            "other": control.replace(reactivate, guarded('            print("비밀번호를 함께 주세요")\n            return 2\n')),
            "other_same_text": control.replace(reactivate, guarded("            print(__doc__)\n            return 1\n")),
            "fixture": (task_dir / "fixture/accounts.py").read_text(encoding="utf-8")}
    for name, text in made.items():
        (out / f"{name}.py").write_text(text, encoding="utf-8")


def run_case(kit, suite, case, work):
    task_dir = kit / "evals/goalflow/tasks" / suite["task"]
    d = Path(tempfile.mkdtemp(dir=work)); (d / "bin").mkdir(); (d / "v").mkdir()
    if suite.get("variants", True):
        variants(task_dir, d / "v")
    (d / "bin/claude").write_text(FAKE, encoding="utf-8"); (d / "bin/claude").chmod(0o755)
    (d / "scen.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    (d / "pins.json").write_text(json.dumps({"claude": {"cli": "fake 0", "model": "m"}, "codex": {"cli": "fake 0", "model": "m"}, "mock_user": "m"}))
    env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "CMP_TASK": suite["task"], "EVALS_PINS": str(d / "pins.json"),
           **case.get("env", {}), "SCEN_FILE": str(d / "scen.json"), "SCEN_N": str(d / "n"), "SCEN_VARIANTS": str(d / "v"), "SCEN_CONTROL": str(task_dir / "control")}
    subprocess.run([sys.executable, "-I", str(kit / "evals/goalflow/compare.py"), "none", "claude", "1", str(d / "out")],
                   env=env, capture_output=True, text=True, timeout=600)
    metas = list((d / "out").glob("*.meta.json"))
    if not metas:
        return "ERROR", "결과 없음"
    meta = json.loads(metas[0].read_text(encoding="utf-8"))
    line = meta["check_output"]
    for key, expected in case.get('dimensions', {}).items():
        if meta.get('goalflow', {}).get(key) != expected:
            return "ERROR", f"{key}: 기대 {expected}, 실제 {meta.get('goalflow', {}).get(key)}"
    return next((w for w in WORDS if line.startswith(w)), "ERROR"), line


def main(kits):
    suites = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((HERE / "scenarios").glob("*.json"))]
    names = [k.name for k in kits]
    tally = {k: {"맞음": 0, "잘못된 통과": 0, "잘못된 실패": 0, "검토 필요": 0, "그 밖": 0} for k in names}
    mismatch_first = 0
    with tempfile.TemporaryDirectory(prefix="scenarios-") as work:
        for suite in suites:
            for case in suite["cases"]:
                row = []
                for i, kit in enumerate(kits):
                    word, line = run_case(kit, suite, case, Path(work))
                    if word == case["expect"] and case["reason"] not in line:  # 판정 낱말이 맞아도 이유가 다르면 우연히 맞은 것이다
                        word = word + "?"
                    t = tally[kit.name]
                    t["검토 필요"] += word == "REVIEW"
                    if word == case["expect"]:
                        t["맞음"] += 1
                    elif word == "PASS":
                        t["잘못된 통과"] += 1
                    elif word == "FAIL":
                        t["잘못된 실패"] += 1
                    else:
                        t["그 밖"] += 1  # 오류·이유가 다른 판정
                    mismatch_first += i == 0 and word != case["expect"]
                    row.append(f"{word}{'' if word == case['expect'] else '✗'}")
                print(f"{case['name']:<48} 기대 {case['expect']:<7} " + "  ".join(f"{n}: {w}" for n, w in zip(names, row)))
    total = sum(len(s["cases"]) for s in suites)
    for n in names:
        t = tally[n]
        print(f"[{n}] 사례 {total}개: 맞음 {t['맞음']}, 잘못된 통과 {t['잘못된 통과']}, 잘못된 실패 {t['잘못된 실패']}, 그 밖 {t['그 밖']}, 검토 필요 {t['검토 필요']}")
    return 1 if mismatch_first else 0


if __name__ == "__main__":
    kits = [Path(a).resolve() for a in sys.argv[1:]] or [HERE.parents[1]]
    sys.exit(main(kits))
