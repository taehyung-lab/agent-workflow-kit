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

    def run_tool(self, items):
        path = self.root / 'situations.json'; path.write_text(json.dumps(items, ensure_ascii=False))
        r = subprocess.run([sys.executable, '-I', str(TOOL), str(path), '--request', str(self.request), '--root', str(self.root)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
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


if __name__ == '__main__':
    unittest.main()
