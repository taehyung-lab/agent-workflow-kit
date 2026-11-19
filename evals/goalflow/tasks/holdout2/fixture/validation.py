"""명령 인수 검사."""
def number(text):
    try:
        return int(text)
    except ValueError:
        raise ValueError('의류 번호는 정수로 입력해 주세요') from None
