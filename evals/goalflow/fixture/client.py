import service


def submit(db, request_id, member, workshop, *, online=True, lose_response=False):
    if not online:
        return {"message": "신청 완료", "workshop": workshop}
    result = service.confirm(db, request_id, member, workshop)
    if lose_response:
        return {"message": "신청 실패", "workshop": workshop}
    if result["code"] == 200:
        return {"message": "신청 완료", "name": service.WORKSHOPS[workshop]["name"], "confirmation": result["confirmation"]}
    return {"message": "신청 실패", "code": result["code"]}


def recover(db, request_id, member):
    result = service.status(db, request_id, member)
    if result["code"] != 200:
        return {"message": "확인 필요", "code": result["code"]}
    return {"message": "신청 완료", "name": service.WORKSHOPS[result["workshop"]]["name"], "confirmation": result["confirmation"]}
