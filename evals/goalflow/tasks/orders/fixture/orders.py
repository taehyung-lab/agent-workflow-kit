"""주문 관리 명령줄 도구.

  python3 orders.py new <고객> <상품:가격>...     새 주문(대기)
  python3 orders.py add <주문번호> <상품:가격>     대기 주문에 상품 더하기
  python3 orders.py remove <주문번호> <상품>      대기 주문에서 상품 빼기
  python3 orders.py pay <주문번호>                결제 완료로 바꾸기
  python3 orders.py receipt <주문번호>            영수증(JSON)

자료 파일은 data.json 이다. 다른 파일을 쓰려면 환경 변수 ORDERS_DATA 에 경로를 준다.
"""
import json, os, sys
from datetime import date
from pathlib import Path

SHIPPING = 3000


def data_path():
    return Path(os.environ.get("ORDERS_DATA") or Path(__file__).with_name("data.json"))


def load():
    return json.loads(data_path().read_text(encoding="utf-8"))


def save(data):
    data_path().write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def find(data, order_id):
    for order in data["orders"]:
        if order["id"] == order_id:
            return order
    raise SystemExit(f"주문 {order_id} 이 없습니다")


def parse_item(text):
    name, _, price = text.rpartition(":")
    if not name or not price.isdigit():
        raise SystemExit(f"상품은 이름:가격 으로 적습니다: {text}")
    return {"name": name, "price": int(price)}


def receipt(order):
    goods = sum(item["price"] for item in order["items"])
    return {"id": order["id"], "customer": order["customer"], "status": order["status"],
            "goods": goods, "shipping": SHIPPING, "total": goods + SHIPPING}


def need_pending(order):
    if order["status"] != "pending":
        raise SystemExit(f"주문 {order['id']} 은 결제가 끝나 바꿀 수 없습니다")


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    command, args = argv[0], argv[1:]
    data = load()
    if command == "new":
        order = {"id": max([o["id"] for o in data["orders"]], default=0) + 1, "customer": args[0],
                 "created": date.today().isoformat(), "status": "pending", "items": [parse_item(a) for a in args[1:]]}
        if not order["items"]:
            raise SystemExit("상품이 하나는 있어야 합니다")
        data["orders"].append(order)
    else:
        order = find(data, int(args[0]))
        if command == "add":
            need_pending(order)
            order["items"].append(parse_item(args[1]))
        elif command == "remove":
            need_pending(order)
            left = [item for item in order["items"] if item["name"] != args[1]]
            if len(left) == len(order["items"]):
                raise SystemExit(f"주문 {order['id']} 에 {args[1]} 이 없습니다")
            if not left:
                raise SystemExit("상품이 하나는 남아야 합니다")
            order["items"] = left
        elif command == "pay":
            need_pending(order)
            order["status"] = "paid"
        elif command != "receipt":
            raise SystemExit(__doc__)
    if command != "receipt":
        save(data)
    print(json.dumps(receipt(order), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
