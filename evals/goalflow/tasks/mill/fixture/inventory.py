def find(rows, key):
    return next(row for row in rows if row["id"] == key)


def positive(text):
    value = int(text)
    if value <= 0:
        raise ValueError("양의 정수 필요")
    return value


def restock(data, key, grams):
    row = find(data["bins"], key)
    row["grams"] += positive(grams)
    return dict(row)


def consume(data, grain, grams):
    raise ValueError("여러 통 재고 차감 미구현")
