"""수선소의 공개 업무."""
def find(data, number):
    for row in data['의류']:
        if row['번호'] == number:
            return row
    raise ValueError('없는 의류 번호입니다')

def listing(data):
    return data['의류']

def receive(data, number, receiver):
    row = find(data, number)
    receiver = receiver.strip()
    if not receiver:
        raise ValueError('수령인 이름을 입력해 주세요')
    if row['상태'] != '완료':
        raise ValueError('완료된 의류만 출고할 수 있습니다')
    # 미수금 정책
    # 재수선 정책
    if receiver != row['고객'] and receiver not in row['대리인']:
        raise ValueError('고객 또는 등록된 대리인만 수령할 수 있습니다')
    receipt = data['다음전표']
    row['상태'] = '출고'
    row['이력'].append({'동작': '출고', '수령인': receiver, '전표': receipt})
    data['다음전표'] += 1
    return row
