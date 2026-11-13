"""표본 코드 조회와 추가 자격."""

def find(data, code):
    for specimen in data["specimens"]:
        if specimen["code"] == code:
            return specimen
    raise ValueError("없는 표본")


def addable(specimen):
    if specimen["retired"]:
        raise ValueError("폐기 표본")
    if specimen["custody"] == "loan":
        raise ValueError("대여 표본 승인 전")


def rename(data, code, name):
    specimen = find(data, code)
    specimen["name"] = name
    return specimen
