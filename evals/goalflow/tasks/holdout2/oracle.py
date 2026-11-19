"""완성된 프로젝트의 공개 명령만 관찰하는 판정기."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

j = Judge(sys.argv[1], 'cli.py', 'SUSEON_DATA')


def rows():
    return j.ok('목록')


def get(number):
    return j.ok('조회', number)


def refusal(*args):
    before = rows()
    code, out = j.run(*args)
    assert code != 0 and isinstance(out, dict), '거절은 실패 코드와 JSON 객체여야 합니다'
    assert isinstance(out.get('오류'), str) and any('가' <= c <= '힣' for c in out['오류']), '한국어 거절 이유가 필요합니다'
    assert rows() == before, '거절로 의류 자료가 바뀌었습니다'


def existing():
    before = rows()
    assert len(before) == 12
    assert [r['번호'] for r in before] == list(range(1, 13))
    assert get(6)['미수금'] == 18000 and get(7)['종류'] == '무대의상'
    assert get(10)['이력'] == [
        {'동작': '출고', '수령인': '이든', '전표': 40},
        {'동작': '재수선', '사유': '솔기풀림'}]
    assert rows() == before


def success():
    result = j.ok('출고', 1, '윤슬')
    assert result['상태'] == '출고' and get(1) == result


def trim():
    r = j.ok('출고', 1, '  윤슬  ')
    assert r['이력'][-1]['수령인'] == '윤슬'


def blank():
    refusal('출고', 1, '')
    refusal('출고', 1, ' \t ')


def invalid():
    refusal('출고', 999, '윤슬')
    refusal('출고', '하나', '윤슬')
    refusal('출고', 1)


def states():
    for number, owner in [(2, '다온'), (3, '하람'), (4, '소담'), (5, '미루')]:
        refusal('출고', number, owner)


def event():
    r = j.ok('출고', 1, '윤슬')
    assert r['이력'] == [{'동작': '출고', '수령인': '윤슬', '전표': 45}]


def fields():
    before = get(1)
    after = j.ok('출고', 1, '윤슬')
    assert {k: v for k, v in after.items() if k not in ('상태', '이력')} == {
        k: v for k, v in before.items() if k not in ('상태', '이력')}


def environment():
    alternate = j.root / '별도장부.json'
    alternate.write_bytes(j.pristine)
    def run(*args):
        p = subprocess.run([sys.executable, 'cli.py', *map(str, args)], cwd=j.root,
            env={**os.environ, 'SUSEON_DATA': str(alternate)},
            capture_output=True, text=True, timeout=20)
        assert p.returncode == 0
        assert len(p.stdout.splitlines()) == 1
        return json.loads(p.stdout)
    changed = run('출고', 1, '윤슬')
    assert changed['상태'] == '출고'
    assert run('조회', 1) == changed
    assert run('목록')[0] == changed
    assert get(1)['상태'] == '완료', '별도 경로의 출고가 기본 자료에 영향을 주었습니다'


# 아래 네 항목은 명령 하나만 실행하는 공개 검사로는 드러나지 않는 연속 사용 검사입니다.
def repeat():
    j.ok('출고', 1, '윤슬')
    refusal('출고', 1, '윤슬')
    assert len(get(1)['이력']) == 1
    assert j.ok('출고', 12, '가람')['이력'][-1]['전표'] == 46


def failed_counter():
    refusal('출고', 1, '   ')
    refusal('출고', 2, '다온')
    assert j.ok('출고', 1, '윤슬')['이력'][-1]['전표'] == 45
    refusal('출고', 999, '가람')
    assert j.ok('출고', 12, '가람')['이력'][-1]['전표'] == 46


def successive():
    first = j.ok('출고', 1, '윤슬')
    second = j.ok('출고', 12, '가람')
    assert [first['이력'][-1]['전표'], second['이력'][-1]['전표']] == [45, 46]
    assert get(1) == first and get(12) == second
    assert [r['번호'] for r in rows() if r['상태'] == '출고'] == [1, 5, 12]


def preserve_others():
    before = [r for r in rows() if r['번호'] not in (1, 12)]
    j.ok('출고', 1, '윤슬')
    j.ok('출고', 12, '가람')
    assert [r for r in rows() if r['번호'] not in (1, 12)] == before
    assert get(5)['이력'][0]['전표'] == 31
    assert get(11)['이력'][0]['전표'] == 44


def unpaid(number, owner, amount):
    before = get(number)
    r = j.ok('출고', number, owner)
    assert r['상태'] == '출고' and r['미수금'] == amount
    assert r['이력'] == before['이력'] + [{'동작': '출고', '수령인': owner, '전표': 45}]


def named_proxies():
    for number, receiver in [(8, '여울'), (9, '도담')]:
        r = j.ok('출고', number, receiver)
        assert r['상태'] == '출고' and r['이력'][-1]['수령인'] == receiver


def strangers():
    refusal('출고', 8, '새봄')
    refusal('출고', 9, '여울')


def reopened():
    before = get(10)
    r = j.ok('출고', 10, '이든')
    assert r['상태'] == '출고'
    assert r['이력'] == before['이력'] + [{'동작': '출고', '수령인': '이든', '전표': 45}]
    assert get(10) == r


def changed_receiver():
    before = get(11)
    r = j.ok('출고', 11, '보라')
    assert r['상태'] == '출고'
    assert r['이력'] == before['이력'] + [{'동작': '출고', '수령인': '보라', '전표': 45}]
    assert get(11) == r


j.check('공개검사', 'given', j.public_tests)
j.check('기존목록과조회보존', 'given', existing)
j.check('완료의류출고저장', 'given', success)
j.check('이름공백제거', 'given', trim)
j.check('빈이름거절', 'given', blank)
j.check('잘못된번호와인수거절', 'given', invalid)
j.check('미완료와종결상태거절', 'given', states)
j.check('이력형식과초기전표', 'given', event)
j.check('대상의다른필드보존', 'given', fields)
j.check('별도자료경로적용', 'given', environment)
j.check('반복출고거절과전표보존', 'given', repeat)
j.check('거절사이전표연속성', 'given', failed_counter)
j.check('연속출고누적저장', 'given', successive)
j.check('연속출고시기존자료보존', 'given', preserve_others)
j.check('일반미수금출고허용', 'decision', lambda: unpaid(6, '누리', 18000))
j.check('무대의상미수금출고허용', 'decision', lambda: unpaid(7, '라온', 92000))
j.check('등록대리수령허용', 'decision', named_proxies)
j.check('미등록수령인거절', 'decision', strangers)
j.check('재수선재출고허용', 'decision', reopened)
j.check('재수선수령인변경허용', 'decision', changed_receiver)
j.finish()
