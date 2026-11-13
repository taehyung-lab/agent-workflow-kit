"""주문 할인 과제의 외부 판정: 끝난 프로젝트의 공개 명령(orders.py)만 실행해 금액을 본다.

  python3 -I evals/goalflow/tasks/orders/oracle.py <프로젝트>

given 은 요청과 docs/operations.md 가 글자 그대로 정한 것, decision 은 answer.txt 의 사용자 답이 정한 것이다.
할인 금액을 보이는 키 이름은 정하지 않았으므로, 영수증의 기존 키 밖에 그 금액과 같은 값이 있으면 보인 것으로 본다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

j = Judge(sys.argv[1], "orders.py", "ORDERS_DATA")
KEYS = ("id", "customer", "status", "goods", "shipping", "total")


def amounts(r):
    return (r["goods"], r["shipping"], r["total"])


def same(got, want):
    assert got == want, {"got": got, "want": want}


def at_threshold():
    same(amounts(j.ok("new", "가", "상자:50000")), (50000, 3000, 48000))


def below_threshold():
    same(amounts(j.ok("new", "가", "상자:49999")), (49999, 3000, 52999))


def shipping_not_counted():
    same(amounts(j.ok("new", "가", "상자:48000")), (48000, 3000, 51000))


def floors_won():
    same(amounts(j.ok("new", "가", "상자:55555")), (55555, 3000, 53000))


def discount_shown():
    r = j.ok("new", "가", "상자:55555")
    extra = [v for k, v in r.items() if k not in KEYS]
    assert 5555 in extra, {"receipt": r, "want": "기존 키 밖에 할인 금액 5555"}
    r = j.ok("receipt", r["id"])
    assert 5555 in [v for k, v in r.items() if k not in KEYS], {"receipt": r}


def paid_existing_unchanged():
    same(amounts(j.ok("receipt", 1)), (80000, 3000, 83000))


def keys_kept():
    r = j.ok("receipt", 3)
    assert all(k in r for k in KEYS) and all(type(r[k]) is int for k in ("id", "goods", "shipping", "total")), r
    same((r["id"], r["customer"], r["status"]), (3, "두레공방", "pending"))


def existing_preserved():
    same([j.ok("receipt", i)["goods"] for i in (1, 2, 3)], [80000, 60000, 30000])
    same(j.ok("new", "가", "상자:1000")["id"], 4)


def paid_new_frozen():
    r = j.ok("new", "가", "상자:60000")
    same(amounts(j.ok("pay", r["id"])), (60000, 3000, 57000))
    j.refused("add", r["id"], "끈:1000")
    same(amounts(j.ok("receipt", r["id"])), (60000, 3000, 57000))


def existing_pending_not_discounted():
    same(amounts(j.ok("receipt", 2)), (60000, 3000, 63000))


def existing_modified_not_discounted():
    same(amounts(j.ok("add", 3, "붓:25000")), (55000, 3000, 58000))
    same(amounts(j.ok("receipt", 3)), (55000, 3000, 58000))


def remove_drops_discount():
    r = j.ok("new", "가", "큰상자:30000", "작은상자:25000")
    same(amounts(r), (55000, 3000, 52500))
    same(amounts(j.ok("remove", r["id"], "작은상자")), (30000, 3000, 33000))
    same(amounts(j.ok("receipt", r["id"])), (30000, 3000, 33000))


def add_applies_discount():
    r = j.ok("new", "가", "큰상자:30000")
    same(amounts(r), (30000, 3000, 33000))
    same(amounts(j.ok("add", r["id"], "끈:20000")), (50000, 3000, 48000))


j.check("new-order-at-threshold-gets-discount", "given", at_threshold)
j.check("below-threshold-no-discount", "given", below_threshold)
j.check("shipping-not-counted-for-threshold", "given", shipping_not_counted)
j.check("discount-floors-below-one-won", "given", floors_won)
j.check("discount-shown-on-receipt", "given", discount_shown)
j.check("paid-existing-order-amount-unchanged", "given", paid_existing_unchanged)
j.check("receipt-keeps-existing-keys", "given", keys_kept)
j.check("existing-orders-and-numbers-preserved", "given", existing_preserved)
j.check("paid-new-order-amount-frozen", "given", paid_new_frozen)
j.check("public-tests-pass", "given", j.public_tests)
j.check("existing-pending-order-not-discounted", "decision", existing_pending_not_discounted)
j.check("existing-order-modified-still-not-discounted", "decision", existing_modified_not_discounted)
j.check("removing-item-below-threshold-drops-discount", "decision", remove_drops_discount)
j.check("adding-item-over-threshold-applies-discount", "decision", add_applies_discount)
j.finish()
