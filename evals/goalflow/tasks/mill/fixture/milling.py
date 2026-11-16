import inventory


def view(job):
    return {key: job[key] for key in ("id", "customer", "grain", "grams", "status", "flour", "bran")}


def new(data, customer, grain, grams):
    account = inventory.find(data["accounts"], customer)
    if account["id"] == "coop" or not any(b["grain"] == grain for b in data["bins"]):
        raise ValueError("고객 또는 곡물 없음")
    job = {"id": max((j["id"] for j in data["jobs"]), default=0) + 1,
           "customer": customer, "grain": grain, "grams": inventory.positive(grams),
           "status": "draft", "flour": 0, "bran": 0}
    data["jobs"].append(job)
    return view(job)


def cancel(data, job):
    if job["status"] == "done":
        raise ValueError("완료 작업 취소 불가")
    job["status"] = "cancelled"
    return view(job)


def run(data, job):
    raise ValueError("제분 미구현")
