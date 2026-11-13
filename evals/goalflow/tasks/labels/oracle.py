"""표본 라벨 과제. 공개 명령의 종료 코드와 약속된 JSON 키만 관찰한다.

각 항목의 근거는 request.txt 또는 docs/operations.md, decision은 answer.txt다.
배열 순서, 추가 키, 내부 저장 형식은 검사하지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

j = Judge(sys.argv[1], "labels.py", "LABELS_DATA")


def sheet_value(s):
    return (s["id"], s["status"], s["used"],
            sorted((i["code"], i["name"], i["quantity"]) for i in s["items"]))


def items(s):
    return {i["code"]: (i["name"], i["quantity"]) for i in s["items"]}


def state():
    sheets = sorted(sheet_value(s) for s in j.ok("list"))
    catalog = sorted((s["code"], s["name"], s["size"], s["custody"], s["retired"])
                     for s in j.ok("catalog"))
    return sheets, catalog


def unchanged(*args):
    before = state()
    j.refused(*args)
    assert state() == before, {"args": args, "want": "거절 후 공개 자료 불변"}


def new():
    return j.ok("new")["id"]


def existing():
    all_sheets = {s["id"]: s for s in j.ok("list")}
    assert sorted(all_sheets) == [1, 2, 3]
    assert [(all_sheets[i]["status"], all_sheets[i]["used"]) for i in (1, 2, 3)] == [
        ("printed", 3), ("draft", 2), ("draft", 1)]
    assert [(i["code"], i["quantity"]) for i in all_sheets[2]["items"]] == [("A1", 2)]
    for i, s in all_sheets.items():
        assert sheet_value(j.ok("show", i)) == sheet_value(s)
    assert len(j.ok("catalog")) == 6


def new_empty():
    before = {s["id"] for s in j.ok("list")}
    s = j.ok("new")
    assert s["id"] not in before and s["status"] == "draft" and s["items"] == [] and s["used"] == 0
    assert sheet_value(j.ok("show", s["id"])) == sheet_value(s)


def add_merge():
    n = new()
    j.ok("add", n, "A1", 2)
    s = j.ok("add", n, "A1", 3)
    assert items(s) == {"A1": ("소나무", 5)} and len(s["items"]) == 1 and s["used"] == 5


def remove_zero():
    s = j.ok("remove", 2, "A1", 1)
    assert items(s) == {"A1": ("소나무", 1)} and s["used"] == 1
    s = j.ok("remove", 2, "A1", 1)
    assert s["items"] == [] and s["used"] == 0


def large_cells():
    n = new()
    s = j.ok("add", n, "B1", 6)
    assert s["used"] == 12 and items(s) == {"B1": ("은행나무", 6)}
    s = j.ok("seal", n)
    assert s["status"] == "printed" and s["used"] == 12


def retired():
    n = new()
    unchanged("add", n, "X1", 1)


def invalid():
    n = new()
    for command in ("add", "remove"):
        for quantity in (0, -1, "1.5"):
            unchanged(command, n, "A1", quantity)
        unchanged(command, n, "missing", 1)
    unchanged("add", 9999, "A1", 1)
    unchanged("remove", 2, "A1", 3)
    unchanged("remove", 2, "B1", 1)


def empty_seal():
    n = new()
    unchanged("seal", n)
    j.ok("add", n, "A1", 1)
    s = j.ok("seal", n)
    assert s["status"] == "printed" and items(s) == {"A1": ("소나무", 1)}


def sealed_edits():
    n = new()
    j.ok("add", n, "A1", 2)
    j.ok("seal", n)
    unchanged("add", n, "A1", 1)
    unchanged("remove", n, "A1", 1)
    unchanged("add", 1, "B1", 1)
    unchanged("remove", 1, "A1", 1)


def seal_repeat():
    n = new()
    j.ok("add", n, "A1", 2)
    first = j.ok("seal", n)
    assert first["status"] == "printed" and items(first) == {"A1": ("소나무", 2)}
    renamed = j.ok("rename", "A1", "붉은소나무")
    assert (renamed["code"], renamed["name"]) == ("A1", "붉은소나무")
    assert sheet_value(j.ok("show", n)) == sheet_value(first)
    before = state()
    for _ in range(2):
        assert sheet_value(j.ok("seal", n)) == sheet_value(first)
    assert state() == before
    assert sheet_value(next(s for s in j.ok("list") if s["id"] == n)) == sheet_value(first)


def reuse_and_order():
    n = new()
    j.ok("add", n, "A1", 10)
    j.ok("remove", n, "A1", 8)
    s = j.ok("add", n, "B1", 5)
    other = new()
    j.ok("add", other, "B1", 5)
    t = j.ok("add", other, "A1", 2)
    assert s["used"] == t["used"] == 12 and items(s) == items(t)
    assert j.ok("seal", n)["status"] == "printed"


def failure_retry():
    n = new()
    j.ok("add", n, "A1", 11)
    unchanged("add", n, "B1", 1)
    s = j.ok("add", n, "A1", 1)
    assert s["used"] == 12 and items(s) == {"A1": ("소나무", 12)}
    assert j.ok("seal", n)["status"] == "printed"


def existing_boundary():
    s = j.ok("add", 2, "A1", 10)
    assert s["used"] == 12 and items(s) == {"A1": ("소나무", 12)}
    unchanged("add", 2, "A1", 1)
    assert j.ok("seal", 2)["used"] == 12


def old_show():
    assert items(j.ok("show", 1)) == {"A1": ("솔나무(옛 전시명)", 3)}
    assert items(next(s for s in j.ok("list") if s["id"] == 1)) == {"A1": ("솔나무(옛 전시명)", 3)}


def old_repeat():
    for _ in range(2):
        s = j.ok("seal", 1)
        assert s["status"] == "printed" and items(s) == {"A1": ("솔나무(옛 전시명)", 3)}


def loan_add():
    n = new()
    unchanged("add", n, "L1", 1)
    # 소장 표본은 추가할 수 있다.
    assert j.ok("add", n, "A1", 1)["used"] == 1


def loan_existing():
    assert items(j.ok("show", 3)) == {"L1": ("대여 난초", 1)}
    unchanged("seal", 3)
    j.ok("remove", 3, "L1", 1)
    j.ok("add", 3, "A1", 1)
    assert j.ok("seal", 3)["status"] == "printed"


def case_lookup():
    a = j.ok("specimen", "M1")
    b = j.ok("specimen", "m1")
    assert (a["code"], a["name"], b["code"], b["name"]) == ("M1", "참나무", "m1", "단풍나무")


def case_edit():
    n = new()
    j.ok("add", n, "M1", 2)
    s = j.ok("add", n, "m1", 3)
    assert items(s) == {"M1": ("참나무", 2), "m1": ("단풍나무", 3)} and s["used"] == 5
    s = j.ok("remove", n, "m1", 2)
    assert items(s) == {"M1": ("참나무", 2), "m1": ("단풍나무", 1)}
    assert items(j.ok("seal", n)) == items(s)


# given 근거(운영 문서의 해당 문장을 항목과 같이 유지한다):
# public-tests-pass: README "변경 뒤에도 위 공개 검사는 모두 통과해야 한다."
# existing-public-data-readable / new-empty-unique-sheet: 운영 1~4항
# add-merges-quantities: "같은 표본을 다시 담으면 수량을 합친다."
# remove-to-zero-drops-item: "수량이 0이 되면 항목을 없앤다."
# large-labels-use-two-cells: 요청의 "큰 라벨은 두 칸"과 운영의 "12칸은 허용"
# retired-specimen-refused: "retired가 true인 표본은 새로 추가할 수 없다."
# invalid-commands-leave-data: 수량·삭제 제한 및 "모든 공개 조회 결과를 그대로 유지"
# empty-seal-refused-then-retry: "seal은 빈 시트를 거절"과 재시도 문장
# printed-edits-refused: "printed에는 add/remove를 거절한다."
# seal-repeat-stable: 요청 두 번째 문단, 운영의 이름 고정·반복 문장
# removed-space-reusable-any-order: "삭제한 칸은 다음 추가에서 즉시 다시 쓸 수 있다."
# failed-add-atomic-then-retry: "거절 후 올바른 명령으로 재시도할 수 있어야 한다."
# existing-contents-count-at-boundary: "기존 시트의 내용도 계산에 포함한다."
# G01~G14: 공개 검사 외의 모든 항목은 CLI 관찰뿐이다.
j.check("public-tests-pass", "given", j.public_tests)
j.check("existing-public-data-readable", "given", existing)
j.check("new-empty-unique-sheet", "given", new_empty)
j.check("add-merges-quantities", "given", add_merge)
j.check("remove-to-zero-drops-item", "given", remove_zero)
j.check("large-labels-use-two-cells", "given", large_cells)
j.check("retired-specimen-refused", "given", retired)
j.check("invalid-commands-leave-data", "given", invalid)
j.check("empty-seal-refused-then-retry", "given", empty_seal)
j.check("printed-edits-refused", "given", sealed_edits)
j.check("seal-repeat-stable", "given", seal_repeat)
j.check("removed-space-reusable-any-order", "given", reuse_and_order)
j.check("failed-add-atomic-then-retry", "given", failure_retry)
j.check("existing-contents-count-at-boundary", "given", existing_boundary)
j.check("past-printed-name-preserved-on-read", "decision", old_show)
j.check("past-printed-name-preserved-on-seal", "decision", old_repeat)
j.check("loan-specimen-add-refused", "decision", loan_add)
j.check("existing-loan-draft-needs-removal", "decision", loan_existing)
j.check("case-distinct-specimen-lookup", "decision", case_lookup)
j.check("case-distinct-add-and-remove", "decision", case_edit)
j.finish()
