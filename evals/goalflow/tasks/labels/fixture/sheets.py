"""시트 수량 편집, 용량 검사, 확정과 공개 출력."""
import catalog


def find(data, sheet_id):
    for sheet in data["sheets"]:
        if sheet["id"] == sheet_id:
            return sheet
    raise ValueError("없는 시트")


def used(data, sheet):
    return sum(item["quantity"] * (2 if catalog.find(data, item["code"])["size"] == "large" else 1)
               for item in sheet["items"])


def view(data, sheet):
    items = []
    for item in sheet["items"]:
        specimen = catalog.find(data, item["code"])
        name = specimen["name"]
        items.append({"code": item["code"], "name": name, "quantity": item["quantity"]})
    return {"id": sheet["id"], "status": sheet["status"], "items": items, "used": used(data, sheet)}


def new(data):
    sheet = {"id": max((s["id"] for s in data["sheets"]), default=0) + 1,
             "status": "draft", "items": []}
    data["sheets"].append(sheet)
    return sheet


def editable(sheet):
    if sheet["status"] == "printed":
        raise ValueError("이미 확정한 시트")


def edit(data, sheet, command, code, quantity):
    if quantity <= 0:
        raise ValueError("수량은 양수")
    specimen = catalog.find(data, code)
    code = specimen["code"]
    item = next((i for i in sheet["items"] if i["code"] == code), None)
    if command == "add":
        catalog.addable(specimen)
        cells = quantity * (2 if specimen["size"] == "large" else 1)
        if item is None:
            item = {"code": code, "quantity": 0}
            sheet["items"].append(item)
        item["quantity"] += quantity
    else:
        if item is None or quantity > item["quantity"]:
            raise ValueError("담긴 수량 부족")
        item["quantity"] -= quantity
        if item["quantity"] == 0:
            sheet["items"].remove(item)


def seal(data, sheet):
    raise ValueError("seal 미구현")
