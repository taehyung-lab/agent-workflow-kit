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


def expect(label, result, given, decision):
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
        return json.loads(p.stdout)


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
        return json.loads(p.stdout)


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

for b in bad:
    print("FAIL " + b)
print(f"과제 4개·변이 12개 확인, {len(bad)} failed")
sys.exit(1 if bad else 0)
