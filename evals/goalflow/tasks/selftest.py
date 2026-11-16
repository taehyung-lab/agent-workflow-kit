"""과제 판정기 확인(모델 호출 없음): 시작 상태는 실패, 정답 구현은 전부 통과, "묻지 않고 흔한 쪽으로 정한" 구현은 사용자 답 항목에서 실패해야 한다.

  python3 -I evals/goalflow/tasks/selftest.py

마지막 변이가 통과하면 그 과제는 묻지 않아도 통과하는 과제라서, 물어야 할 것을 찾았는지를 재지 못한다.
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
bad = []


def judge(task, script, source):
    d = Path(tempfile.mkdtemp(prefix="tasktest-"))
    shutil.copytree(HERE / task / "fixture", d / "p")
    (d / "p" / script).write_text(source, encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", str(HERE / task / "oracle.py"), str(d / "p")], capture_output=True, text=True)
    shutil.rmtree(d, ignore_errors=True)
    return json.loads(p.stdout)


checked = 0


def expect(label, result, given, decision):
    global checked
    checked += 1
    got = (sorted(result["failed_given"]), sorted(result["failed_decision"]))
    if got != (sorted(given), sorted(decision)):
        bad.append(f"{label}: 실패 항목 {got} != 기대 {(sorted(given), sorted(decision))}")


for task, script in (("orders", "orders.py"), ("rooms", "rooms.py")):
    start = (HERE / task / "fixture" / script).read_text(encoding="utf-8")
    control = (HERE / task / "control" / script).read_text(encoding="utf-8")
    r = judge(task, script, start)
    if not r["failed_given"] or r["automated_valid"]:
        bad.append(f"{task}: 시작 상태가 통과한다")
    expect(f"{task} 정답 구현", judge(task, script, control), [], [])

# 주문: 기존 주문에도 계산 시점에 할인한다(묻지 않고 정한 흔한 구현)
guess = (HERE / "orders/control/orders.py").read_text(encoding="utf-8").replace('order.get("discountable") and ', "")
expect("orders 흔한 구현", judge("orders", "orders.py", guess), ["paid-existing-order-amount-unchanged"],
       ["existing-pending-order-not-discounted", "existing-order-modified-still-not-discounted"])
# 주문: 만들 때 한 번 정한 할인을 그대로 둔다
src = (HERE / "orders/control/orders.py").read_text(encoding="utf-8")
frozen = src.replace('"discountable": True, "items": [parse_item(a) for a in args[1:]]}',
                     '"items": [parse_item(a) for a in args[1:]]}\n        order["discountable"] = sum(i["price"] for i in order["items"]) >= DISCOUNT_FROM')
frozen = frozen.replace('if order.get("discountable") and goods >= DISCOUNT_FROM else 0', 'if order.get("discountable") else 0')
expect("orders 만들 때 고정", judge("orders", "orders.py", frozen), [],
       ["removing-item-below-threshold-drops-discount", "adding-item-over-threshold-applies-discount"])
# 회의실: 임시 예약도 자리를 막는다(묻지 않고 정한 흔한 구현)
src = (HERE / "rooms/control/rooms.py").read_text(encoding="utf-8")
blocking = src.replace('other["status"] == "confirmed"', 'other["status"] != "cancelled"').replace("        if not hold:\n            need_free(data, booking, start, end)", "        need_free(data, booking, start, end)")
expect("rooms 흔한 구현", judge("rooms", "rooms.py", blocking), [],
       ["hold-does-not-block-new-booking", "hold-over-confirmed-allowed", "confirming-hold-over-confirmed-refused"])
# 회의실: 시각을 글자로 비교한다(9:30 과 10:00)
lexical = src.replace("def minutes(text):\n    hour, minute = text.split(\":\")\n    return int(hour) * 60 + int(minute)", "def minutes(text):\n    return text")
expect("rooms 글자 비교", judge("rooms", "rooms.py", lexical), ["old-time-format-compared-by-clock", "move-into-confirmed-refused"], [])

# 표본 라벨: 네 모듈을 복사하고 정답에서 고친 두 모듈만 덮어쓴다.
def judge_labels(overrides):
    with tempfile.TemporaryDirectory(prefix="labeltest-") as temp:
        project = Path(temp) / "p"
        shutil.copytree(HERE / "labels/fixture", project)
        for filename, source in overrides.items():
            (project / filename).write_text(source, encoding="utf-8")
        p = subprocess.run([sys.executable, "-I", str(HERE / "labels/oracle.py"), str(project)],
                           capture_output=True, text=True)
        if p.returncode not in (0, 1):
            raise RuntimeError(p.stderr)
        result = json.loads(p.stdout)
        # 판정기 자신의 버그는 어떤 입력에서도 나오면 안 된다(나오면 그 항목은 관찰 불가로 빠진다)
        bugs = [c["name"] for c in result.get("cases") or [] if str(c.get("detail") or "").startswith("판정기 오류")]
        if bugs:
            bad.append(f"판정기 오류 {bugs}")
        return result


label_control = {p.name: p.read_text(encoding="utf-8") for p in (HERE / "labels/control").glob("*.py")}
r = judge_labels({})
if not r["failed_given"] or r["automated_valid"]:
    bad.append("labels: 시작 상태가 통과한다")
if "public-tests-pass" in r["failed_given"]:
    bad.append("labels: 시작 상태의 공개 검사가 실패한다")
expect("labels 정답 구현", judge_labels(label_control), [], [])

# 저장 구조를 바꾸고 공개 출력에 키를 더하거나 배열 순서를 바꿔도 통과해야 한다.
# 판정기가 자료 파일의 내부 키나 JSON 전체 동등성에 의존하는 실수를 막는다.
layout_storage = (HERE / "labels/fixture/storage.py").read_text(encoding="utf-8")
layout_storage = layout_storage.replace(
    'return json.loads(path().read_text(encoding="utf-8"))',
    'raw = json.loads(path().read_text(encoding="utf-8"))\n    return raw.get("payload", raw)')
layout_storage = layout_storage.replace(
    'json.dumps(data, ensure_ascii=False, indent=2)',
    'json.dumps({"payload": data, "format": 2}, ensure_ascii=False, indent=2)')
layout_sheets = label_control["sheets.py"].replace(
    '{"code": item["code"], "name": name, "quantity": item["quantity"]}',
    '{"code": item["code"], "name": name, "quantity": item["quantity"], "extra": "추가 값"}')
layout_sheets = layout_sheets.replace(
    '"items": items, "used": used(data, sheet)',
    '"items": list(reversed(items)), "used": used(data, sheet), "extra": "추가 값"')
layout_cli = (HERE / "labels/fixture/labels.py").read_text(encoding="utf-8").replace(
    '[sheets.view(data, s) for s in data["sheets"]]',
    '[sheets.view(data, s) for s in reversed(data["sheets"])]')
expect("labels 저장 형식·추가 키·순서 독립", judge_labels({
    **label_control, "storage.py": layout_storage, "sheets.py": layout_sheets,
    "labels.py": layout_cli}), [], [])


def label_mutant(label, overrides, given, decision):
    sources = {**label_control, **overrides}
    result = judge_labels(sources)
    expect(label, result, given, decision)
    print(label + ": given=" + str(result["failed_given"]) + ", decision=" + str(result["failed_decision"]))


# 1번을 묻지 않고 과거 인쇄분은 현재 표본명으로 통일한다(새 확정분은 이름 고정).
latest = label_control["sheets.py"].replace(
    'name = item["name"] if sheet["status"] == "printed" else specimen["name"]',
    'name = item["name"] if sheet["status"] == "printed" and sheet.get("sealed") else specimen["name"]')
label_mutant("labels 과거 이름 갱신", {"sheets.py": latest}, [],
             ["past-printed-name-preserved-on-read", "past-printed-name-preserved-on-seal"])

# 2번을 묻지 않고 소장·대여 구분 없이 같은 기능을 적용한다.
loan_catalog = label_control["catalog.py"].replace(
    '    if specimen["custody"] == "loan":\n        raise ValueError("대여 표본 승인 전")\n', '')
loan_sheets = label_control["sheets.py"].replace(
    '        if specimen["custody"] == "loan":\n            raise ValueError("대여 표본 승인 전")\n', '')
label_mutant("labels 대여도 허용", {"catalog.py": loan_catalog, "sheets.py": loan_sheets}, [],
             ["loan-specimen-add-refused", "existing-loan-draft-needs-removal"])

# 3번을 묻지 않고 코드 조회를 흔한 대소문자 무시 검색으로 바꾼다.
folded = label_control["catalog.py"].replace(
    'if specimen["code"] == code:', 'if specimen["code"].casefold() == code.casefold():')
label_mutant("labels 코드 대소문자 통일", {"catalog.py": folded}, [],
             ["case-distinct-specimen-lookup", "case-distinct-add-and-remove"])

# 요청만 보고 새 시트에 add -> seal 하는 곧은 경로만 구현한 변이.
# 추가량 누계만 용량으로 쓰고, 삭제·기존 자료·확정 상태를 고려하지 않으며
# 검증 전에 저장한다. 출력 used 자체는 실제 내용을 계산하므로 공개 검사는 통과한다.
straight_edit = '''def edit(data, sheet, command, code, quantity):
    if quantity <= 0:
        raise ValueError("수량은 양수")
    specimen = catalog.find(data, code)
    code = specimen["code"]
    item = next((i for i in sheet["items"] if i["code"] == code), None)
    if command == "add":
        catalog.addable(specimen)
        if item is None:
            item = {"code": code, "quantity": 0}
            sheet["items"].append(item)
        item["quantity"] += quantity
        cells = quantity * (2 if specimen["size"] == "large" else 1)
        sheet["_added_cells"] = sheet.get("_added_cells", 0) + cells
        if sheet["_added_cells"] > 12:
            import storage
            storage.save(data)
            raise ValueError("12칸 초과")
    else:
        if item is None or quantity > item["quantity"]:
            raise ValueError("담긴 수량 부족")
        item["quantity"] -= quantity
        if item["quantity"] == 0:
            sheet["items"].remove(item)


'''
base = label_control["sheets.py"]
straight = base[:base.index("def edit(")] + straight_edit + base[base.index("def seal("):]
label_mutant("labels 곧은 경로만 구현", {"sheets.py": straight},
             ["printed-edits-refused", "removed-space-reusable-any-order",
              "failed-add-atomic-then-retry", "existing-contents-count-at-boundary"], [])

# 공동 제분소: 네 모듈 중 두 모듈을 고쳐야 실제 제분이 가능하다.
def judge_mill(overrides):
    with tempfile.TemporaryDirectory(prefix="milltest-") as temp:
        project = Path(temp) / "p"
        shutil.copytree(HERE / "mill/fixture", project)
        for filename, source in overrides.items():
            (project / filename).write_text(source, encoding="utf-8")
        p = subprocess.run([sys.executable, "-I", str(HERE / "mill/oracle.py"), str(project)],
                           capture_output=True, text=True)
        if p.returncode not in (0, 1):
            raise RuntimeError(p.stderr)
        result = json.loads(p.stdout)
        # 판정기 자신의 버그는 어떤 입력에서도 나오면 안 된다(나오면 그 항목은 관찰 불가로 빠진다)
        bugs = [c["name"] for c in result.get("cases") or [] if str(c.get("detail") or "").startswith("판정기 오류")]
        if bugs:
            bad.append(f"판정기 오류 {bugs}")
        return result


mill_control = {p.name: p.read_text(encoding="utf-8") for p in (HERE / "mill/control").glob("*.py")}
r = judge_mill({})
if not r["failed_given"] or r["automated_valid"]:
    bad.append("mill: 시작 상태가 통과한다")
if "public-tests-pass" in r["failed_given"]:
    bad.append("mill: 시작 상태의 공개 검사가 실패한다")
expect("mill 정답 구현", judge_mill(mill_control), [], [])


def mill_mutant(label, overrides, given, decision):
    result = judge_mill({**mill_control, **overrides})
    expect(label, result, given, decision)
    print(label + ": given=" + str(result["failed_given"]) + ", decision=" + str(result["failed_decision"]))


# 1번: 묻지 않고 밀가루를 내림하고 나머지를 겨로 둔다.
floor = mill_control["milling.py"].replace('(job["grams"] * 2 + 2) // 3', 'job["grams"] * 2 // 3')
mill_mutant("mill 산출량 내림", {"milling.py": floor}, [],
            ["round-up-one-gram", "round-up-existing-four-grams"])

# 2번: 묻지 않고 흔한 선입선출을 택한다.
fifo = mill_control["inventory.py"].replace('reverse=True', 'reverse=False')
mill_mutant("mill 선입선출", {"inventory.py": fifo}, [],
            ["newest-bin-first", "newest-bin-spillover"])

# 3번: 묻지 않고 부산물도 고객에게 적립한다.
customer_bran = mill_control["milling.py"].replace(
    'inventory.find(data["accounts"], "coop")["bran"] += bran',
    'inventory.find(data["accounts"], job["customer"])["bran"] += bran')
mill_mutant("mill 겨도 고객 귀속", {"milling.py": customer_bran}, [],
            ["bran-to-coop-c1", "bran-to-coop-c2"])

# 요청의 new -> run 정상 경로만 구현한 변이:
# 완료 재실행 방지 없이 원료를 다시 쓰고, 재고가 '더 많을 때'만 실행한다.
# 여러 통에서 가능한 만큼 먼저 저장하고 부족을 보고해 실패 뒤 재시도가 깨진다.
# 세 사용자 결정의 구현은 그대로 두므로 결정 누락과 given 누락을 구별한다.
straight_inventory = mill_control["inventory.py"].replace(
    '    if sum(b["grams"] for b in bins) < grams:\n        raise ValueError("원료 부족")\n',
    '    shortage = sum(b["grams"] for b in bins) <= grams\n')
straight_inventory += '''
    if shortage:
        import storage
        storage.save(data)
        raise ValueError("원료 부족")
'''
straight_milling = mill_control["milling.py"].replace(
    '    if job["status"] == "done":\n        return view(job)\n', '').replace(
    'if job["status"] != "draft":', 'if job["status"] == "cancelled":')
mill_mutant("mill 곧은 경로만 구현", {
    "inventory.py": straight_inventory, "milling.py": straight_milling},
    ["repeat-run-no-double-spend", "shortage-atomic-then-restock-retry",
     "existing-multi-bin-exact-boundary", "jobs-share-live-stock"], [])

# 동일한 공개 결과를 내면서 내부 저장을 감싸고 출력에 키를 더하고 배열을 역순으로.
wrapped_storage = (HERE / "mill/fixture/storage.py").read_text(encoding="utf-8").replace(
    'return json.loads(path().read_text(encoding="utf-8"))',
    'raw = json.loads(path().read_text(encoding="utf-8"))\n    return raw.get("payload", raw)').replace(
    'json.dumps(data, ensure_ascii=False, indent=2)',
    'json.dumps({"payload": data, "version": 2}, ensure_ascii=False, indent=2)')
extra_cli = (HERE / "mill/fixture/mill.py").read_text(encoding="utf-8").replace(
    'print(json.dumps(main(sys.argv[1:]), ensure_ascii=False))',
    'result = main(sys.argv[1:])\n        if isinstance(result, list):\n            result = list(reversed(result))\n            for row in result:\n                row["extra"] = True\n        else:\n            result["extra"] = True\n        print(json.dumps(result, ensure_ascii=False))')
expect("mill 저장 형식·추가 키·순서 독립", judge_mill({
    **mill_control, "storage.py": wrapped_storage, "mill.py": extra_cli}), [], [])

# 아래 네 과제는 evals/cases 의 "물었는가"를 낱말로 판정하던 사례를 옮긴 것이다. 정답에서 고친 파일만 덮어써서 판정한다.
def judge_files(task, overrides):
    with tempfile.TemporaryDirectory(prefix="tasktest-") as temp:
        project = Path(temp) / "p"
        shutil.copytree(HERE / task / "fixture", project)
        for filename, source in overrides.items():
            (project / filename).parent.mkdir(parents=True, exist_ok=True)
            (project / filename).write_text(source, encoding="utf-8")
        p = subprocess.run([sys.executable, "-I", str(HERE / task / "oracle.py"), str(project)], capture_output=True, text=True)
        if p.returncode not in (0, 1):
            raise RuntimeError(p.stderr)
        result = json.loads(p.stdout)
        # 판정기 자신의 버그는 어떤 입력에서도 나오면 안 된다(나오면 그 항목은 관찰 불가로 빠진다)
        bugs = [c["name"] for c in result.get("cases") or [] if str(c.get("detail") or "").startswith("판정기 오류")]
        if bugs:
            bad.append(f"판정기 오류 {bugs}")
        return result


def control_files(task):
    root = HERE / task / "control"
    return {str(f.relative_to(root)): f.read_text(encoding="utf-8")
            for f in root.rglob("*") if f.is_file() and "__pycache__" not in f.parts}


def files_mutant(label, task, overrides, given, decision):
    result = judge_files(task, {**control_files(task), **overrides})
    expect(label, result, given, decision)
    print(label + ": given=" + str(result["failed_given"]) + ", decision=" + str(result["failed_decision"]))


# 주제별 판정 항목(topic-checks.json): 이름이 판정기 결과에 실제로 있고, 시작 상태와 정답 구현 사이에서 모든 주제의 동작이 바뀐 것으로 잡힌다
sys.path.insert(0, str(HERE.parent))
from conversation import changed_topics, topic_behavior  # noqa: E402
for task in ("orders", "rooms", "labels", "mill", "archive-ambiguity", "archive-correction", "account-correction", "merge-conflict"):
    with tempfile.TemporaryDirectory(prefix="topics-") as temp:
        project = Path(temp) / "p"
        shutil.copytree(HERE / task / "fixture", project)
        start = topic_behavior(HERE / task, project)
        for f in (HERE / task / "control").rglob("*"):
            if f.is_file():
                (project / f.relative_to(HERE / task / "control")).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, project / f.relative_to(HERE / task / "control"))
        done = topic_behavior(HERE / task, project)
        mapping = json.loads((HERE / task / "topic-checks.json").read_text(encoding="utf-8"))
        if start is None or done is None:
            bad.append(f"{task}: topic-checks.json 의 항목을 판정기 결과에서 찾지 못했다")
        else:
            # 통과 여부가 달라진 주제는 반드시 바뀐 것으로 잡힌다(정책이 원래 동작과 같은 주제는 정답 구현에서도 그대로일 수 있다: 주문의 기존 주문)
            flipped = {t for t in done if [c[1] for c in start[t]] != [c[1] for c in done[t]]}
            if {t for t, how in changed_topics(start, done).items() if how == "flipped"} != flipped or not flipped:
                bad.append(f"{task}: 통과 여부가 달라진 주제 {sorted(flipped)} 를 바뀐 주제 {changed_topics(start, done)} 로 잡지 못했다")
        if changed_topics(start, start):
            bad.append(f"{task}: 같은 상태를 비교했는데 바뀐 주제가 있다")

# 판정기 자신의 버그(정의되지 않은 이름 등)는 제품 실패가 아니라 관찰 불가다(2026-11-16 검토: NameError 가 제품 실패로 기록됐다)
sys.path.insert(0, str(HERE))
from taskcheck import Judge  # noqa: E402
_probe = Judge.__new__(Judge); _probe.cases = []; _probe.fresh = lambda: None
_probe.check("oracle-bug", "decision", lambda: undefined_name_in_oracle)  # noqa: F821
_probe.check("product-wrong", "decision", lambda: (_ for _ in ()).throw(AssertionError("기대와 다름")))
if [c["passed"] for c in _probe.cases] != [None, False]:
    bad.append(f"판정기 버그는 관찰 불가(None), 제품 불일치는 실패(False)여야 한다: {_probe.cases}")

for task in ("archive-correction", "archive-ambiguity", "account-correction", "merge-conflict"):
    r = judge_files(task, {})
    if r["automated_valid"] or not (r["failed_given"] or r["failed_decision"]):
        bad.append(f"{task}: 시작 상태가 통과한다")
    expect(f"{task} 정답 구현", judge_files(task, control_files(task)), [], [])


def replaced(source, old, new):
    """변이가 정답 코드와 어긋나 조용히 같은 코드가 되는 것을 막는다."""
    assert old in source, old
    return source.replace(old, new)


# 보관함: 묻지 않고 완료하는 즉시 보관함으로 옮기고, 보관함 보기 명령 이름을 archive 로 둔다(archived 는 없다).
todo = control_files("archive-ambiguity")["todo.py"]
instant = replaced(todo, '                it["done"] = True\n',
                   '                it["done"] = True\n                it["archived"] = True\n')
instant = replaced(instant, '    elif cmd == "archive":\n        for it in items:\n            if it["done"]:\n'
                   '                it["archived"] = True\n        save(items)\n    elif cmd == "archived":\n',
                   '    elif cmd == "archive":\n')
# 변이는 정책 시험이 없는 시험 파일(목록은 안 끝난 것만, 내보내기는 완료 항목 포함)과 함께 둔다.
plain_tests = (HERE / "archive-ambiguity/fixture/tests/test_todo.py").read_text(encoding="utf-8")
for task in ("archive-correction", "archive-ambiguity"):
    files_mutant(f"{task} 완료 즉시 보관", task, {"todo.py": instant, "tests/test_todo.py": plain_tests}, [],
                 ["done-item-waits-for-archive-command", "archive-moves-all-done-items", "archived-lists-only-archived-items"])

# 계정: 비활성화하되 로그인은 막지 않는다. 공개 검사는 control 의 것이라 함께 실패한다.
accounts = control_files("account-correction")["accounts.py"]
files_mutant("account-correction 비활성도 로그인", "account-correction",
             {"accounts.py": replaced(accounts, ' or not u.get("active", True):', ':'),
              "tests/test_accounts.py": (HERE / "account-correction/fixture/tests/test_accounts.py").read_text(encoding="utf-8")},
             [], ["deactivated-login-refused"])
# 계정: 되살리는 명령을 두지 않는다.
files_mutant("account-correction 되살리기 없음", "account-correction",
             {"accounts.py": replaced(accounts, '    elif cmd == "reactivate":\n        return set_active(users, args[0], True)\n', ''),
              "tests/test_accounts.py": (HERE / "account-correction/fixture/tests/test_accounts.py").read_text(encoding="utf-8")},
             [], ["reactivate-restores-login-and-list"])
# 계정: 명단에 비활성 표시를 붙여 그대로 보인다.
files_mutant("account-correction 명단에 표시만", "account-correction",
             {"accounts.py": replaced(accounts, '            if users[name].get("active", True):\n                print(name)',
                                      '            print(name if users[name].get("active", True) else f"{name} (비활성)")'),
              "tests/test_accounts.py": (HERE / "account-correction/fixture/tests/test_accounts.py").read_text(encoding="utf-8")},
             [], ["deactivated-hidden-from-list"])

# 계정: 비활성화 명령은 있지만 사용법에 적지 않았다. 판정기는 이름을 추측하지 않으므로 사용자가 찾을 수 없는 명령으로 본다.
files_mutant("account-correction 사용법에 없는 명령", "account-correction",
             {"accounts.py": replaced(accounts, "  python3 accounts.py deactivate <아이디>           회원 탈퇴: 계정을 지우지 않고 비활성으로 바꾼다\n", ""),
              "tests/test_accounts.py": (HERE / "account-correction/fixture/tests/test_accounts.py").read_text(encoding="utf-8")},
             ["deactivate-command-found", "other-accounts-unaffected", "account-data-kept"], ["deactivated-login-refused", "deactivated-hidden-from-list", "reactivate-restores-login-and-list"])

# 계정: 정책을 다 지킨 구현에 읽기 전용 명령(status)을 deactivate 보다 앞에 적어도 판정기는 그것을 비활성화 명령으로 고르지 않는다
with_status = replaced(accounts, "  python3 accounts.py deactivate <아이디>", "  python3 accounts.py status <아이디>               계정 상태 보기\n  python3 accounts.py deactivate <아이디>")
with_status = replaced(with_status, '    elif cmd == "deactivate":', '    elif cmd == "status":\n        print("active" if users.get(args[0], {}).get("active", True) else "inactive")\n        return 0\n    elif cmd == "deactivate":')
files_mutant("account-correction 읽기 전용 명령이 앞에 있음", "account-correction", {"accounts.py": with_status}, [], [])
# 계정: argparse 처럼 사용법을 "{a,b,c}" 로 stderr 에 알리는 구현도 판정기가 명령을 찾는다
argp = replaced(accounts, "  python3 accounts.py deactivate <아이디>           회원 탈퇴: 계정을 지우지 않고 비활성으로 바꾼다\n", "")
argp = replaced(argp, "  python3 accounts.py reactivate <아이디>           비활성 계정을 되살린다\n", "")
argp = replaced(argp, "        print(__doc__)", "        print(\"usage: accounts.py [-h] {signup,login,list,deactivate,reactivate}\", file=sys.stderr)")
files_mutant("account-correction argparse 꼴 사용법", "account-correction", {"accounts.py": argp}, [], [])

# 실제 계정 과제의 판정기 출력으로 본 주제별 변화(2026-11-16 재검토 2″): 공통 코드의 부작용과 그 주제의 구현을 구별한다
#   시작 → 비활성화만 구현(되살리기 없음): 주제 1·2 는 통과 여부가 뒤집히고 주제 3 은 관찰 문구만 바뀐다
#   시작 → 비활성화 + 원문과 다른 되살리기(비밀번호를 다시 받음): 주제 3 은 여전히 실패이고 관찰 문구만 바뀐다(재검토 2‴ 반례)
#     → 두 경우는 바깥 관찰로 같은 모양이라 정상과 위반을 가를 수 없다: 그 턴에 그 주제를 물었다면 검토 필요로 남긴다
#   비활성화만 → 원문대로 되살리기까지 구현: 주제 3 이 뒤집힌다(이 턴에 묻는 글을 썼다면 결정받기 전 구현이다)
from conversation import MockUser  # noqa: E402
_acc = (HERE / "account-correction/control/accounts.py").read_text(encoding="utf-8")
_partial = replaced(replaced(_acc, '    elif cmd == "reactivate":\n        return set_active(users, args[0], True)\n', ''),
                    "  python3 accounts.py reactivate <아이디>           비활성 계정을 되살린다\n", "")
with tempfile.TemporaryDirectory(prefix="topics-acc-") as temp:
    project = Path(temp) / "p"; shutil.copytree(HERE / "account-correction/fixture", project)
    start = topic_behavior(HERE / "account-correction", project)
    (project / "accounts.py").write_text(_partial, encoding="utf-8"); partial = topic_behavior(HERE / "account-correction", project)
    _other = replaced(_acc, '    elif cmd == "reactivate":\n        return set_active(users, args[0], True)\n',
                      '    elif cmd == "reactivate":\n        if len(args) < 2:\n            print("비밀번호를 함께 주세요")\n            return 2\n        return set_active(users, args[0], True)\n')
    (project / "accounts.py").write_text(_other, encoding="utf-8"); other = topic_behavior(HERE / "account-correction", project)
    (project / "accounts.py").write_text(_acc, encoding="utf-8"); full = topic_behavior(HERE / "account-correction", project)
step1, step_other, step2 = changed_topics(start, partial), changed_topics(start, other), changed_topics(partial, full)
if step1 != {1: "flipped", 2: "flipped", 3: "detail"} or step_other.get(3) != "detail" or step2.get(3) != "flipped":
    bad.append(f"계정 주제별 변화: 시작→비활성화만 {step1}, 시작→다른 되살리기 {step_other}, 비활성화만→전체 {step2}")
answer = (HERE / "account-correction/answer.txt").read_text(encoding="utf-8")
fake = lambda text, topics: [n for n, w in ((1, "Q1"), (2, "Q2"), (3, "Q3")) if w in text]
# ① 1·2 를 묻고 답받아 구현하면서 3 을 물음 → 3 에 답한다. 바깥 관찰로는 ③ 과 같은 모양이라 검토 필요로 남는다(통과로도 위반으로도 확정하지 않는다)
m = MockUser(["요청"], answer, "t", fake); m.prompt(1); m.observe("Q1 Q2 어떻게 할까요?", False, {}); m.prompt(2)
m.observe("1·2 구현했습니다. Q3 은 어떻게 할까요?", True, step1)
if "reactivate" not in m.prompt(3) or m.decided_first or m.review != {3: 2}:
    bad.append(f"① 질문 사례: decided_first={m.decided_first} review={m.review} (기대: 검토 필요 3)")
# ③ 재검토 2‴ 반례: 되살리기를 원문과 다른 정책으로 먼저 만들고 이대로 괜찮은지 물음 → 정상으로 확정하지 않는다(검토 필요)
m = MockUser(["요청"], answer, "t", fake); m.prompt(1); m.observe("Q1 Q2 어떻게 할까요?", False, {}); m.prompt(2)
m.observe("되살리기는 비밀번호를 다시 받도록 구현했습니다. Q3 이대로 괜찮을까요?", True, step_other)
m.prompt(3)
if m.review != {3: 2} or m.decided_first:
    bad.append(f"③ 다른 정책으로 먼저 구현한 사례가 정상으로 확정됨: decided_first={m.decided_first} review={m.review}")
# ② 오인: 같은 턴에 되살리기까지 구현하고 질문처럼 보고 → 결정받기 전 구현
m = MockUser(["요청"], answer, "t", fake); m.prompt(1); m.observe("Q1 Q2 어떻게 할까요?", False, {}); m.prompt(2)
m.observe("1·2·되살리기를 구현했습니다. Q3 이대로 괜찮을까요?", True, changed_topics(start, full))
m.prompt(3)
if m.decided_first != {3: 2}:
    bad.append(f"오인 사례가 결정받기 전 구현으로 나오지 않음: {m.decided_first}")

# 백업: 묻지 않고 30일을 고르거나, 두 기간을 함께 적는다.
rules = control_files("merge-conflict")["backup-rules.md"]
files_mutant("merge-conflict 30일 선택", "merge-conflict",
             {"backup-rules.md": replaced(rules, "90일 동안 보관한다(감사 대응)", "30일 동안 보관한다")}, [],
             ["retention-90-days", "no-30-day-retention"])
files_mutant("merge-conflict 두 기간 병기", "merge-conflict",
             {"backup-rules.md": replaced(rules, "90일 동안 보관한다(감사 대응)", "30일(초안 A) 또는 90일(초안 B, 감사 대응) 동안 보관한다")}, [],
             ["no-30-day-retention"])

for b in bad:
    print("FAIL " + b)
print(f"과제 8개·판정 대조 {checked}개 확인, {len(bad)} failed")
sys.exit(1 if bad else 0)
