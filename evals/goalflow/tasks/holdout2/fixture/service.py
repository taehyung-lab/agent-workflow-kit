"""수선소의 공개 업무."""
def find(data, number):
    for row in data['의류']:
        if row['번호'] == number:
            return row
    raise ValueError('없는 의류 번호입니다')

def listing(data):
    return data['의류']

def receive(data, number, receiver):
    raise ValueError('출고 기능은 아직 없습니다')
