"""공동 제분소: 공개 CLI의 종료 코드와 문서가 유지한 JSON 값만 관찰한다.

내부 파일 키·추가 키·배열 순서는 관찰하지 않는다. given의 근거는 아래 등록부에 있다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

j = Judge(sys.argv[1], "mill.py", "MILL_DATA")


def jobs():
    return {row["id"]: job_value(row) for row in j.ok("list")}


def job_value(row):
    return tuple(row[k] for k in ("id", "customer", "grain", "grams", "status", "flour", "bran"))


def stock():
    return {row["id"]: row["grams"] for row in j.ok("stock")}


def accounts():
    return {row["id"]: (row["flour"], row["bran"]) for row in j.ok("accounts")}


def state():
    return (sorted(tuple(r[k] for k in ("id", "grain", "grams", "arrived")) for r in j.ok("stock")),
            accounts(), jobs())


def unchanged(*args):
    before = state()
    j.refused(*args)
    assert state() == before, {"args": args, "expected": "거절 후 공개 값 불변"}


def new(grams=3, customer="c1", grain="wheat"):
    return j.ok("new", customer, grain, grams)["id"]


def existing():
    assert stock() == {"old": 9, "new": 9, "rye": 30}
    assert accounts() == {"c1": (20, 4), "c2": (0, 0), "coop": (0, 7)}
    assert jobs() == {
        7: (7, "c1", "wheat", 6, "draft", 0, 0),
        8: (8, "c1", "rye", 3, "done", 2, 1),
        9: (9, "c2", "rye", 4, "draft", 0, 0)}
    assert {r["id"]: (r["grain"], r["arrived"]) for r in j.ok("stock")} == {
        "old": ("wheat", "2026-10-01"), "new": ("wheat", "2026-11-01"), "rye": ("rye", "2026-10-03")}
    for key, value in jobs().items():
        assert job_value(j.ok("show", key)) == value


def create_validate():
    before = state()
    old = jobs()
    a, b = new(), new(6, "c2", "rye")
    assert a != b and a not in old and b not in old
    assert jobs()[a] == (a, "c1", "wheat", 3, "draft", 0, 0)
    assert jobs()[b] == (b, "c2", "rye", 6, "draft", 0, 0)
    assert state()[:2] == before[:2]
    for qty in (0, -1, "1.5"):
        unchanged("new", "c1", "wheat", qty)
    for customer, grain in (("missing", "wheat"), ("coop", "wheat"), ("c1", "missing")):
        unchanged("new", customer, grain, 3)


def restock():
    before = state()
    row = j.ok("restock", "old", 3)
    assert tuple(row[k] for k in ("id", "grain", "grams", "arrived")) == ("old", "wheat", 12, "2026-10-01")
    assert stock() == {"old": 12, "new": 9, "rye": 30}
    assert state()[1:] == before[1:]
    for qty in (0, -1, "1.5"):
        unchanged("restock", "old", qty)
    unchanged("restock", "missing", 3)


def cancelled():
    before = state()
    first = j.ok("cancel", 7)
    assert job_value(first) == (7, "c1", "wheat", 6, "cancelled", 0, 0)
    assert state()[:2] == before[:2]
    assert job_value(j.ok("cancel", 7)) == job_value(first)
    unchanged("run", 7)


def simple():
    key = new(6, grain="rye")
    row = j.ok("run", key)
    assert job_value(row) == (key, "c1", "rye", 6, "done", 4, 2)
    assert stock() == {"old": 9, "new": 9, "rye": 24}
    assert accounts()["c1"][0] == 24


def conservation():
    before_s, before_a = stock(), accounts()
    row = j.ok("run", 7)
    assert row["status"] == "done" and row["flour"] == 4 and row["bran"] == 2
    assert sum(before_s.values()) - sum(stock().values()) == 6
    assert stock()["rye"] == before_s["rye"]
    assert sum(sum(x) for x in accounts().values()) - sum(sum(x) for x in before_a.values()) == 6


def done_cancel():
    key = new(3, grain="rye")
    j.ok("run", key)
    unchanged("cancel", key)
    unchanged("cancel", 8)


def repeat():
    key = new(3, grain="rye")
    first = job_value(j.ok("run", key))
    before = state()
    for _ in range(2):
        assert job_value(j.ok("run", key)) == first
        assert state() == before
    past = job_value(j.ok("show", 8))
    for _ in range(2):
        assert job_value(j.ok("run", 8)) == past
        assert state() == before


def shortage_retry():
    key = new(21)
    unchanged("run", key)
    j.ok("restock", "old", 3)
    row = j.ok("run", key)
    assert row["status"] == "done" and (row["flour"], row["bran"]) == (14, 7)
    assert stock() == {"old": 0, "new": 0, "rye": 30}


def boundary():
    key = new(18)
    row = j.ok("run", key)
    assert (row["status"], row["flour"], row["bran"]) == ("done", 12, 6)
    assert stock() == {"old": 0, "new": 0, "rye": 30}


def live_stock():
    a, b = new(12), new(9)
    j.ok("run", a)
    assert sum(stock()[k] for k in ("old", "new")) == 6
    unchanged("run", b)
    j.ok("restock", "old", 3)
    assert j.ok("run", b)["status"] == "done"
    assert stock() == {"old": 0, "new": 0, "rye": 30}


def order():
    a, b = new(3), new(6, "c2")
    j.ok("run", a)
    j.ok("run", b)
    want = state()
    j.fresh()
    a, b = new(3), new(6, "c2")
    j.ok("run", b)
    j.ok("run", a)
    assert state() == want


def reads_and_invalid():
    j.ok("restock", "rye", 2)
    before = state()
    for _ in range(2):
        for key, value in jobs().items():
            assert job_value(j.ok("show", key)) == value
        assert state() == before
    for args in (("show", 999), ("run", 999), ("cancel", 999), ("oops",), ("new",), ("run", "bad")):
        unchanged(*args)


def round_one():
    key = new(1, grain="rye")
    row = j.ok("run", key)
    assert (row["flour"], row["bran"]) == (1, 0)


def round_existing():
    row = j.ok("run", 9)
    assert (row["flour"], row["bran"]) == (3, 1)


def newest():
    j.ok("run", new(3))
    assert stock() == {"old": 9, "new": 6, "rye": 30}


def spanning():
    j.ok("run", new(12))
    assert stock() == {"old": 6, "new": 0, "rye": 30}


def bran_c1():
    j.ok("run", new(3, grain="rye"))
    assert accounts() == {"c1": (22, 4), "c2": (0, 0), "coop": (0, 8)}


def bran_c2():
    j.ok("run", new(6, "c2", "rye"))
    assert accounts() == {"c1": (20, 4), "c2": (4, 0), "coop": (0, 9)}


# given의 글자 그대로인 근거: README 및 운영 문서 bullet 번호.
# G01 README "변경 뒤에도 공개 검사는 모두 통과해야 한다."
# G02 운영 1~3 기존 자료와 공개 키; G03 운영 4 new; G04 운영 5 restock
# G05 운영 10 취소; G06 운영 6 실행과 2/3; G07 운영 6 산출 합과 차감
# G08 운영 9 완료 취소; G09 운영 9 반복과 과거 done
# G10 운영 7~8 전체 거절·재시도; G11 운영 7 기존 모든 통·동일 경계
# G12 운영 11 작업마다 현재 재고; G13 운영 11 순서를 바꿔도 최종값 동일
# G14 운영 12 지속·조회·잘못된 명령
for name, fn in [
    ("public-tests-pass", j.public_tests),
    ("existing-public-values", existing),
    ("new-valid-unique-unreserved", create_validate),
    ("restock-valid-persistent", restock),
    ("cancel-draft-repeat-and-run-refused", cancelled),
    ("run-divisible-output-and-stock", simple),
    ("run-conserves-material", conservation),
    ("done-cancel-refused", done_cancel),
    ("repeat-run-no-double-spend", repeat),
    ("shortage-atomic-then-restock-retry", shortage_retry),
    ("existing-multi-bin-exact-boundary", boundary),
    ("jobs-share-live-stock", live_stock),
    ("execution-order-same-totals", order),
    ("reads-persist-invalid-unchanged", reads_and_invalid),
]:
    j.check(name, "given", fn)
for name, fn in [
    ("round-up-one-gram", round_one),
    ("round-up-existing-four-grams", round_existing),
    ("newest-bin-first", newest),
    ("newest-bin-spillover", spanning),
    ("bran-to-coop-c1", bran_c1),
    ("bran-to-coop-c2", bran_c2),
]:
    j.check(name, "decision", fn)
j.finish()
