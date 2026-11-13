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
    bins = sorted((b for b in data["bins"] if b["grain"] == grain),
                  key=lambda b: (b["arrived"], b["id"]), reverse=True)
    if sum(b["grams"] for b in bins) < grams:
        raise ValueError("원료 부족")
    left = grams
    for row in bins:
        used = min(left, row["grams"])
        row["grams"] -= used
        left -= used
