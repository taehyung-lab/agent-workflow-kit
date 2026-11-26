"""상황 기록 확인(wf-ask/situations.py): '정해짐'은 그 결과를 말하는 인용이 원문·합의 문서에 있을 때만 남는다.

예시는 저장 실행에서 독자가 혼자 정했던 근거의 종류(막는 문장 없음, 지금 동작, 요청 밖)를 그대로 옮겼다.
"""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
TOOL = KIT / '.agents/skills/wf-ask/situations.py'
WORK = KIT / '.agents/skills/wf-verify/work.py'
REQUEST = '물품을 상자에 담은 뒤 봉인할 수 있게 해 주세요. 빈 상자는 봉인할 수 없습니다.\n'
CONTRACT = '# 운영 약속\n\n- custody는 owned 또는 borrowed다.\n- 이미 들어 있는 기록은 지우거나 바꾸지 않는다.\n'


class SituationsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'docs').mkdir(); (self.root / 'docs/rules.md').write_text(CONTRACT)
        self.request = self.root / 'request.txt'; self.request.write_text(REQUEST)

    def run_tool(self, items, axes=None, code=0, reader=None):
        """axes 를 주지 않으면 항목마다 고유한 칸과 두 결과를 만들어 표 확인을 통과시킨다(출처 확인만 보는 시험)."""
        if axes is None:
            for n, item in enumerate(items):
                item.setdefault('cell', [f's{n}', 'c'])
                item.setdefault('results', ['허용', '거절'])
                if item.get('state') == '확정':
                    item.setdefault('chosen', '허용')
            axes = {'states': [{'name': item['cell'][0], 'where': 'data.json'} for item in items],
                    'commands': [{'name': 'c', 'where': 'app.py'}]}
        path = self.root / 'situations.json'
        path.write_text(json.dumps({'axes': axes, 'situations': items}, ensure_ascii=False))
        extra = []
        if reader is not None:
            (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False)); extra = ['--reader', str(self.root / 'reader.json')]
        r = subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--root', str(self.root), *extra],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def ids(self, result, key):
        return [item['id'] for item in result[key]]

    def test_request_and_contract_quotes_keep_settled(self):
        result = self.run_tool([
            {'id': 'Q1', 'expect': '빈 상자 봉인 → 거절', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '요청', 'quote': '빈 상자는 봉인할 수 없습니다.'}},
            {'id': 'Q2', 'expect': '기존 기록 → 그대로', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '합의', 'file': 'docs/rules.md', 'quote': '이미 들어 있는   기록은 지우거나 바꾸지 않는다.'}}])
        self.assertEqual(self.ids(result, 'settled'), ['Q1', 'Q2'])
        self.assertEqual(result['demoted'], [])

    def test_settled_without_quoted_source_becomes_open(self):
        # 저장 실행의 독자 근거: "제외할 근거는 없다"(막는 문장 없음), "지금 조회를 유지"(지금 동작)
        result = self.run_tool([
            {'id': 'Q1', 'expect': '빌린 물품을 새로 담기 → 허용', 'source': [1], 'state': '확정',
             'facts': '막는 문장이 없고 지금도 담긴다'},
            {'id': 'Q2', 'expect': '빌린 물품이 든 상자 봉인 → 허용', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '요청', 'quote': '빌린 물품도 봉인할 수 있다'}},
            {'id': 'Q3', 'expect': '대소문자만 다른 코드 → 지금처럼 같은 물품', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '현재 동작', 'quote': 'find 는 casefold 로 찾는다'}},
            {'id': 'Q4', 'expect': '기존 기록 → 그대로', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '합의', 'file': 'docs/missing.md', 'quote': '이미 들어 있는 기록은 지우거나 바꾸지 않는다.'}}])
        self.assertEqual(result['settled'], [])
        self.assertEqual(self.ids(result, 'open'), ['Q1', 'Q2', 'Q3', 'Q4'])
        reasons = {d['id']: d['reason'] for d in result['demoted']}
        self.assertIn('결정 출처', reasons['Q1'])
        self.assertIn('원문·문서에 없다', reasons['Q2'])
        self.assertIn('결정 출처', reasons['Q3'])
        self.assertIn('찾지 못했다', reasons['Q4'])
        self.assertTrue(all('decided_by' not in item for item in result['open']))

    def test_open_items_stay_open(self):
        result = self.run_tool([{'id': 'Q1', 'expect': '빌린 물품 새로 담기 → 허용 / 거절', 'source': [1], 'state': '미정'}])
        self.assertEqual(self.ids(result, 'open'), ['Q1'])

    def test_empty_cell_stops(self):
        # 저장 실행: '이미 겹친 기록 × 보존'은 합의 문장으로 정했고 '이미 겹친 기록 × 옮기기'는 상황이 없어 묻지 않았다.
        axes = {'states': [{'name': '이미 겹친 기록', 'where': 'data.json:7-8'}, {'name': '확정 기록', 'where': 'data.json:3'}],
                'commands': [{'name': '보존', 'where': 'app.py:load'}, {'name': '옮기기', 'where': 'app.py:move'}]}
        items = [
            {'id': 'Q1', 'cell': ['이미 겹친 기록', '보존'], 'expect': '이미 겹친 기록', 'results': ['그대로', '정리'], 'chosen': '그대로', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '합의', 'file': 'docs/rules.md', 'quote': '이미 들어 있는 기록은 지우거나 바꾸지 않는다.'}},
            {'id': 'Q2', 'cell': ['확정 기록', '보존'], 'expect': '확정 기록', 'results': ['그대로', '정리'], 'source': [1], 'state': '미정'},
            {'id': 'Q3', 'cell': ['확정 기록', '옮기기'], 'expect': '확정 기록 옮기기', 'results': ['허용', '거절'], 'source': [1], 'state': '미정'}]
        result = self.run_tool(items, axes, code=3)
        self.assertEqual(result['missing'], [['이미 겹친 기록', '옮기기']])
        items.append({'id': 'Q4', 'cell': ['이미 겹친 기록', '옮기기'], 'expect': '이미 겹친 기록을 옮겨도 겹침이 남음',
                      'results': ['허용', '거절'], 'source': [1], 'state': '미정'})
        result = self.run_tool(items, axes)
        self.assertEqual(result['missing'], [])
        self.assertIn('Q4', self.ids(result, 'open'))

    def test_table_needs_real_locations_and_known_cells(self):
        axes = {'states': [{'name': '확정 기록', 'where': ''}], 'commands': [{'name': '옮기기', 'where': 'app.py'}]}
        item = {'id': 'Q1', 'cell': ['확정 기록', '옮기기'], 'expect': '옮기기', 'results': ['허용', '거절'], 'source': [1], 'state': '미정'}
        self.assertIn('where', self.run_tool([item], axes, code=3)['error'])
        axes['states'][0]['where'] = 'data.json:3'
        item['cell'] = ['없는 상태', '옮기기']
        self.assertIn('표에 없는 칸', self.run_tool([item], axes, code=3)['error'])

    def test_record_tool_applies_same_check(self):
        repo = self.root / 'repo'; repo.mkdir()
        for args in (('init', '-q'), ('config', 'user.name', 't'), ('config', 'user.email', 't@invalid')):
            subprocess.run(['git', *args], cwd=repo, check=True)
        (repo / 'docs').mkdir(); (repo / 'docs/rules.md').write_text(CONTRACT)
        subprocess.run(['git', 'add', '.'], cwd=repo, check=True); subprocess.run(['git', 'commit', '-qm', 's'], cwd=repo, check=True)
        base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'targets': [{'name': 'app', 'path': str(repo), 'base': base}],
                                    'requirements': [{'id': 'R1', 'expect': '상자 봉인', 'source': [1], 'state': '확정'}],
                                    'checks': [{'id': 'C1', 'target': 'app', 'requirements': ['R1'], 'argv': ['true']}]}))
        work = self.root / 'work'
        def call(*args):
            r = subprocess.run([sys.executable, str(WORK), 'record', *args, str(work)], cwd=repo, capture_output=True, text=True)
            return r.returncode, json.loads(r.stdout)
        self.assertEqual(call('--request', str(self.request), '--plan', str(plan))[0], 0)
        findings = self.root / 'reader.json'
        findings.write_text(json.dumps([
            {'id': 'Q1', 'expect': '빌린 물품 새로 담기 → 허용', 'source': [1], 'state': '확정', 'facts': '막는 문장 없음'},
            {'id': 'Q2', 'expect': '기존 기록 → 그대로', 'source': [1], 'state': '확정',
             'decided_by': {'kind': '합의', 'file': 'docs/rules.md', 'quote': '이미 들어 있는 기록은 지우거나 바꾸지 않는다.'}}], ensure_ascii=False))
        rc, out = call('--findings', str(findings))
        self.assertEqual(rc, 0, out)
        self.assertEqual([d['id'] for d in out['demoted']], ['Q1'])
        states = {}
        for line in (work / 'journal.jsonl').read_text().splitlines():
            for item in json.loads(line).get('findings', []):
                states[item['id']] = item['state']
        self.assertEqual(states, {'Q1': '미정', 'Q2': '확정'})
        # 미정으로 내린 Q1 은 사용자 답 없이 계획에서 확정으로 바꿀 수 없다(기존 미정 보존 규칙).
        data = json.loads(plan.read_text())
        data['requirements'] += [{'id': 'Q1', 'expect': '빌린 물품 → 허용', 'source': [1], 'state': '확정'},
                                 {'id': 'Q2', 'expect': '기존 기록 → 그대로', 'source': [1], 'state': '확정'}]
        plan.write_text(json.dumps(data, ensure_ascii=False))
        self.assertNotEqual(call('--plan', str(plan))[0], 0)
        # 표를 넣으면 빈 칸이 있을 때 기록하지 않는다.
        findings.write_text(json.dumps({'axes': {'states': [{'name': 'a', 'where': 'data.json'}, {'name': 'b', 'where': 'data.json'}],
                                                 'commands': [{'name': 'c', 'where': 'app.py'}]},
                                        'situations': [{'id': 'Q5', 'cell': ['a', 'c'], 'expect': 'a', 'results': ['허용', '거절'], 'source': [1], 'state': '미정'}]},
                                       ensure_ascii=False))
        rc, out = call('--findings', str(findings))
        self.assertNotEqual(rc, 0, out)
        self.assertIn('칸', out['reason'])

    def test_single_result_situation_stops(self):
        # 저장 실행(라벨 3회차): 독자가 대여 표본 시트 확정에 결과를 하나만 적고("→ printed; 원문은 소유 구분을 제한하지 않음")
        # 요청의 일반 문장으로 확정했다. 다른 결과(대여라서 거절)를 적지 않으면 인용이 무엇을 골랐는지 볼 수 없다.
        axes = {'states': [{'name': '빌린 물품 상자', 'where': 'data.json:3'}], 'commands': [{'name': '봉인', 'where': 'app.py:seal'}]}
        item = {'id': 'Q1', 'cell': ['빌린 물품 상자', '봉인'], 'expect': '빌린 물품이 든 상자 봉인', 'results': ['봉인됨'],
                'source': [1], 'state': '확정', 'chosen': '봉인됨',
                'decided_by': {'kind': '요청', 'quote': '물품을 상자에 담은 뒤 봉인할 수 있게 해 주세요.'}}
        self.assertIn('둘 이상', self.run_tool([item], axes, code=3)['error'])
        item['results'] = ['봉인됨', '빌린 물품이라 거절']
        del item['chosen']
        result = self.run_tool([item], axes)
        self.assertEqual(self.ids(result, 'open'), ['Q1'])
        self.assertIn('chosen', result['demoted'][0]['reason'])

    def test_message_must_carry_each_reader_question(self):
        # 2026-11-25 라벨 1·3회차: 독자는 M1·m1 을 미정으로 돌려줬고 담당자가 첫 답에서 뺐다. 담당자는 같은 주제의 상황을 묶어 바꿔 써서
        # 낱말 대조로는 가를 수 없었다 → 질문 문장은 독자가 쓰고(ask), 보낸 글에 그 문장이 그대로 있는지만 본다.
        names = '이미 확정된 1번 시트를 열 때, 저장된 옛 이름(소나무)과 현재 이름(솔나무) 중 무엇을 보일까요?'
        loan = '대여 중인 표본 L1이 담긴 3번 시트도 확정할 수 있게 할까요?'
        code = 'M1(참나무)과 m1(단풍나무)을 입력하면 같은 표본으로 볼까요, 다른 표본으로 볼까요?'
        reader = {'axes': {'states': [{'name': s, 'where': 'data.json'} for s in ('printed', 'loan', 'code')],
                           'commands': [{'name': 'seal', 'where': 'sheets.py'}]},
                  'situations': [
                      {'id': 'Q16', 'cell': ['printed', 'seal'], 'expect': '1번 seal', 'results': ['옛 이름', '현재 이름'], 'source': [1], 'state': '미정', 'ask': names},
                      {'id': 'Q19', 'cell': ['printed', 'seal'], 'expect': '1번 조회', 'results': ['옛 이름', '현재 이름'], 'source': [1], 'state': '미정', 'ask': names},
                      {'id': 'Q28', 'cell': ['loan', 'seal'], 'expect': '3번 seal', 'results': ['허용', '거절'], 'source': [1], 'state': '미정', 'ask': loan},
                      {'id': 'Q29', 'cell': ['code', 'seal'], 'expect': 'm1 추가', 'results': ['m1', 'M1'], 'source': [1], 'state': '미정', 'ask': code}]}
        merged = json.loads(json.dumps(reader))
        path = self.root / 'situations.json'; path.write_text(json.dumps(merged, ensure_ascii=False))
        (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False))
        def check(text, code_=0):
            (self.root / 'message.md').write_text(text)
            r = subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--root', str(self.root),
                                '--reader', str(self.root / 'reader.json'), '--message', str(self.root / 'message.md')], capture_output=True, text=True)
            self.assertEqual(r.returncode, code_, r.stdout + r.stderr)
            return [u['id'] for u in json.loads(r.stdout)['undelivered']]
        # 1·3회차 모양: 이름·대여만 묻고 코드는 뺐다
        self.assertEqual(check(f'구현 전 두 가지를 정해야 합니다.\n1. {names}\n2. {loan}\n추천은 현재 이름 유지입니다.', 3), ['Q29'])
        # 2회차 모양: 세 질문 모두(앞뒤 설명·줄바꿈이 달라도 된다)
        self.assertEqual(check(f'세 가지가 필요합니다.\n- {names}\n- {loan}\n-  {code}'), [])
        # 질문 번호만 있는 글은 통과하지 못한다
        self.assertEqual(check('Q16, Q19, Q28, Q29 를 확인해 주세요.', 3), ['Q16', 'Q19', 'Q28', 'Q29'])
        # 사용자 답(kind 답)으로 정해진 상황은 다시 보내지 않아도 된다
        merged['situations'][3].update(state='확정', chosen='m1', source=[2], decided_by={'kind': '답', 'quote': '입력한 정확한 코드에 적용합니다'})
        path.write_text(json.dumps(merged, ensure_ascii=False))
        (self.root / 'answer.txt').write_text('조회, 추가, 삭제 모두 입력한 정확한 코드에 적용합니다.\n')
        (self.root / 'message.md').write_text(f'{names}\n{loan}')
        (self.root / 'sent1.md').write_text(f'세 가지가 필요합니다.\n- {names}\n- {loan}\n- {code}')
        def answered(*sent):
            return subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--request', str(self.root / 'answer.txt'),
                                   '--root', str(self.root), '--reader', str(self.root / 'reader.json'), '--message', str(self.root / 'message.md'),
                                   *[x for f in sent for x in ('--sent', str(self.root / f))]], capture_output=True, text=True)
        r = answered('sent1.md')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 그 질문을 보낸 글이 없으면 답으로 닫지 못한다(2026-11-26 접근권한 f3: 다른 주제의 말을 답으로 인용)
        r = answered()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('Q29', r.stdout)
        # 독자가 ask 를 안 쓴 미정은 그 사실을 알린다
        del reader['situations'][2]['ask']; (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False))
        merged['situations'][3].update(state='미정'); merged['situations'][3].pop('decided_by'); path.write_text(json.dumps(merged, ensure_ascii=False))
        self.assertEqual(check(f'{names}\n{code}', 3), ['Q28'])

        # 첫 답에 붙일 질문 목록: 같은 ask 는 한 번, 순서는 처음 나온 대로. 붙인 글은 대조를 통과한다
        reader['situations'][2]['ask'] = loan; (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False))
        r = subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--root', str(self.root),
                            '--reader', str(self.root / 'reader.json'), '--compose'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines(), [f'1. {names}', f'2. {loan}', f'3. {code}'])
        self.assertEqual(check('구현 전에 정해 주세요.\n' + r.stdout + '\n추천은 1번 현재 이름입니다.'), [])

    def test_composed_notice_can_be_sent_with_two_independent_readers(self):
        first = {'id': 'Q1', 'expect': '빈 상자 봉인', 'source': [1], 'state': '미정',
                 'ask': '빈 상자도 봉인할까요?', 'default': '거절', 'default_by': '운영 기록'}
        self.run_tool([first])
        table = self.root / 'situations.json'
        other = self.root / 'reader2.json'
        record = json.loads(table.read_text())
        record['situations'][0]['ask'] = '내용물이 없을 때도 봉인할까요?'
        other.write_text(json.dumps(record))
        cmd = [sys.executable, str(TOOL), str(table), '--request', str(self.request),
               '--reader', str(table), '--reader', str(other)]
        message = self.root / 'notice.txt'
        message.write_text(subprocess.check_output([*cmd, '--compose'], text=True))
        reply = subprocess.run([*cmd, '--message', str(message)], text=True, capture_output=True)
        self.assertEqual(reply.returncode, 0, reply.stdout)
        self.assertEqual(message.read_text().count('기본값'), 1)

    def test_unsolicited_correction_needs_a_matching_reader_and_later_user_turn(self):
        before = {'id': 'Q1', 'expect': '빈 상자 봉인', 'source': [1], 'state': '확정',
                  'chosen': '거절', 'decided_by': {'kind': '요청', 'quote': '빈 상자는 봉인할 수 없습니다.'}}
        self.run_tool([before])
        table = self.root / 'situations.json'
        original = self.root / 'original.json'
        original.write_bytes(table.read_bytes())
        record = json.loads(table.read_text())
        updated = record['situations'][0]
        change = '빈 상자도 봉인할 수 있게 해 주세요.'
        updated.update(chosen='허용', source=[2], decided_by={'kind': '정정', 'quote': change},
                       observed={'where': '기존 동작', 'value': '거절'})
        table.write_text(json.dumps(record))
        later = self.root / 'turn2'
        later.write_text(change)
        independent = self.root / 'independent.json'
        independent.write_bytes(table.read_bytes())
        cmd = [sys.executable, str(TOOL), str(table), '--request', str(self.request),
               '--request', str(later), '--reader', str(original)]
        def run(*options):
            return subprocess.run([*cmd, *options], text=True, capture_output=True)
        accepted = run('--reader', str(independent))
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        self.assertEqual(json.loads(accepted.stdout)['settled'][0]['chosen'], '허용')
        notice = run('--reader', str(independent), '--compose').stdout
        self.assertIn(change, notice)
        self.assertIn('거절 (기존 동작)', notice)
        self.assertNotEqual(run().returncode, 0)
        later.write_text('그대로 진행해 주세요.')
        updated['decided_by']['quote'] = later.read_text()
        table.write_text(json.dumps(record))
        independent.write_bytes(table.read_bytes())
        self.assertFalse(json.loads(run('--reader', str(independent)).stdout).get('ready', False))

    def test_new_implementer_receives_the_input_action_and_expected_outcome(self):
        item = {'id': 'Q1', 'expect': '빈 상자에서 봉인을 누른다', 'cell': ['빈 상자', '봉인'],
                'source': [1], 'state': '확정', 'results': ['허용', '거절'], 'chosen': '거절',
                'decided_by': {'kind': '요청', 'quote': '빈 상자는 봉인할 수 없습니다.'}}
        axes = {'states': [{'name': '빈 상자', 'where': 'data/boxes.json'}],
                'commands': [{'name': '봉인', 'where': '상자 상세 화면'}]}
        self.run_tool([item], axes)
        result = subprocess.check_output(
            [sys.executable, str(TOOL), str(self.root / 'situations.json'),
             '--request', str(self.request), '--handoff'], text=True)
        brief, = json.loads(result)['implementation']
        for detail in ('data/boxes.json', '상자 상세 화면', item['expect'], '거절', item['decided_by']['quote']):
            self.assertIn(detail, brief)

    def test_compose_shows_the_decided_result_and_its_source(self):
        scene = '빈 상자에서 봉인을 누른다'
        policy = '빈 상자는 봉인할 수 없습니다.'
        item = {'id': 'Q1', 'expect': scene, 'chosen': '거절', 'source': [1],
                'state': '확정', 'decided_by': {'kind': '요청', 'quote': policy}}
        self.run_tool([item])
        table = self.root / 'situations.json'
        reply = subprocess.check_output(
            [sys.executable, str(TOOL), str(table), '--request', str(self.request),
             '--reader', str(table), '--compose'], text=True)
        for confirmed in (scene, '거절', policy):
            self.assertIn(confirmed, reply)

    def test_compose_puts_reference_observations_first(self):
        # 2026-11-24 접근권한: "1.5와 같게"인데 1.5 의 저장 경로를 보지 않아 이름만 고쳐도 조회가 저장됐다.
        # 독자가 지정 기준에서 관찰한 값(observed)은 첫 답 목록 맨 앞에 "기준 관찰" 줄로 나간다. 위치·값이 없으면 멈춘다.
        reader = {'axes': {'states': [{'name': '등록만 저장된 권한', 'where': 'data'}], 'commands': [{'name': s, 'where': 'ui'} for s in ('열기', '이름만 저장', '등록 클릭')]},
                  'situations': [
                      {'id': 'Q1', 'cell': ['등록만 저장된 권한', '열기'], 'expect': '수정 화면을 연다(조회 칸)', 'results': ['켜짐', '꺼짐'], 'chosen': '켜짐',
                       'source': [1], 'state': '확정', 'decided_by': {'kind': '요청', 'quote': '물품을 상자에 담은 뒤'},
                       'observed': {'where': 'v1.5 permission-tree-row.tsx:73', 'value': '조회 켜짐·잠김'}},
                      {'id': 'Q2', 'cell': ['등록만 저장된 권한', '이름만 저장'], 'expect': '이름만 고쳐 저장(전송 기능)', 'results': ['CREATE', 'CREATE·READ'], 'chosen': 'CREATE',
                       'source': [1], 'state': '확정', 'decided_by': {'kind': '요청', 'quote': '물품을 상자에 담은 뒤'},
                       'observed': {'where': 'v1.5 use-access-permission-form.ts:139', 'value': 'CREATE 만 전송'}},
                      {'id': 'Q3', 'cell': ['등록만 저장된 권한', '등록 클릭'], 'expect': '등록을 누른다', 'results': ['조회 켜짐', '그대로'], 'source': [1], 'state': '미정',
                       'ask': '블랙리스트에도 같은 규칙을 둘까요?'}]}
        path = self.root / 'situations.json'; path.write_text(json.dumps(reader, ensure_ascii=False))
        (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False))
        def compose(code_=0):
            r = subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--root', str(self.root),
                                '--reader', str(self.root / 'reader.json'), '--compose'], capture_output=True, text=True)
            self.assertEqual(r.returncode, code_, r.stdout + r.stderr)
            return r.stdout.strip().splitlines()
        self.assertEqual(compose(), ['1. 기준 관찰: 수정 화면을 연다(조회 칸) → 조회 켜짐·잠김 (v1.5 permission-tree-row.tsx:73)',
                                     '2. 기준 관찰: 이름만 고쳐 저장(전송 기능) → CREATE 만 전송 (v1.5 use-access-permission-form.ts:139)',
                                     '3. 블랙리스트에도 같은 규칙을 둘까요?'])
        reader['situations'][1]['observed'] = {'where': ''}; (self.root / 'reader.json').write_text(json.dumps(reader, ensure_ascii=False))
        path.write_text(json.dumps(reader, ensure_ascii=False))
        self.assertIn('where', compose(3)[0])

    def test_merged_record_cannot_shrink_reader_table(self):
        # 저장 실행(라벨 3회차): 독자 표에 빈 칸 26개가 나오자 주 담당자가 상태를 하나로 합쳐 빈 칸 확인을 지나갔다.
        reader = {'axes': {'states': [{'name': '빈 상자', 'where': 'app.py:new'}, {'name': '빌린 물품 상자', 'where': 'data.json:3'}],
                           'commands': [{'name': '봉인', 'where': 'app.py:seal'}]},
                  'situations': [{'id': 'Q1', 'cell': ['빈 상자', '봉인'], 'expect': '빈 상자 봉인', 'results': ['거절', '봉인됨'],
                                  'source': [1], 'state': '확정', 'chosen': '거절',
                                  'decided_by': {'kind': '요청', 'quote': '빈 상자는 봉인할 수 없습니다.'}},
                                 {'id': 'Q2', 'cell': ['빌린 물품 상자', '봉인'], 'expect': '빌린 물품 상자 봉인',
                                  'results': ['봉인됨', '거절'], 'source': [1], 'state': '미정'}]}
        collapsed = json.loads(json.dumps(reader))
        collapsed['axes']['states'] = [{'name': '도달하는 상자 상태', 'where': 'data.json'}]
        for item in collapsed['situations']:
            item['cell'][0] = '도달하는 상자 상태'
        self.assertIn('빠졌다', self.run_tool(collapsed['situations'], collapsed['axes'], code=3, reader=reader)['error'])
        settled = json.loads(json.dumps(reader))
        settled['situations'][1].update(state='확정', chosen='봉인됨',
                                        decided_by={'kind': '요청', 'quote': '물품을 상자에 담은 뒤 봉인할 수 있게 해 주세요.'})
        self.assertIn('사용자 답 없이', self.run_tool(settled['situations'], settled['axes'], code=3, reader=reader)['error'])
        result = self.run_tool(reader['situations'], reader['axes'], reader=reader)
        self.assertEqual(self.ids(result, 'open'), ['Q2'])


    def test_generic_approval_cannot_flip_reader_result(self):
        # 2026-11-26 접근권한 k1: 독자가 1.5 로 정한 저장 줄을 담당자가 자기 질문으로 다시 열고 반대를 추천,
        # "진행해주세요"를 그 승인으로 받았다 → 독자가 정한 결과는 일반 승인으로 바뀌지 않는다.
        import importlib.util
        spec = importlib.util.spec_from_file_location('situations', TOOL); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        ask = '등록만 저장된 권한을 그대로 저장하면 조회도 함께 저장할까요?'
        reader = {'situations': [{'id': 'Q10', 'state': '확정', 'chosen': '등록만', 'results': ['등록만', '조회도']}]}
        merged = {'situations': [{'id': 'Q10', 'state': '확정', 'chosen': '조회도', 'results': ['등록만', '조회도'], 'source': [2], 'ask': ask,
                                  'decided_by': {'kind': '답', 'quote': '진행해주세요'}}]}
        self.assertIn('일반 승인', ' '.join(mod.answers_unbound(merged, reader, [f'1. {ask} (추천: 조회도)'])))
        merged['situations'][0]['decided_by']['quote'] = '조회도 함께 저장해 주세요'
        self.assertEqual(mod.answers_unbound(merged, reader, [f'1. {ask}']), [])


if __name__ == '__main__':
    unittest.main()
