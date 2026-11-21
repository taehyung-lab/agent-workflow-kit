"""보존된 원문을 독립 판독하는 공개 CLI 계약. 모델을 실행하지 않는다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / 'evals/goalflow/discovery_review.py'


class DiscoveryReviewTest(unittest.TestCase):
    def fixture(self, root, static=1):
        summary = dict(name='kit-codex-1', task='labels', static_turns=static,
                       conversation_contract='fixed-policy-v1', policy_topics=[1, 2],
                       required_discovery_topics=[1], discovery_exclusions={'2':'기존 계약'},
                       task_fingerprint='executed-task', judge_version='executed-judge',
                       discovered=[], mock_error='quota exhausted',
                       turns=[{'turn':n, 'reply':'잘린 요약', 'rc':0} for n in range(1, static + 1)])
        path = root / 'kit-codex-1.json'; path.write_text(json.dumps(summary))
        (root / 'kit-codex-1.meta.json').write_text('{"check_passed":false,"raw":"original score"}')
        for n in range(1, static + 1):
            reply = ('앞선 설명' * 5000) + f'끝의 선택 {n}을 어떻게 할까요?'
            event = {'type':'item.completed','item':{'type':'agent_message','text':reply}}
            (root / f'kit-codex-1.t{n}.jsonl').write_text(json.dumps(event) + '\n')
        return path

    def review(self, root, summary, quotes):
        supplied = root / 'quotes.input'; supplied.write_text(json.dumps({'quotes':quotes}))
        run = subprocess.run([sys.executable, '-I', str(COMMAND), str(summary),
                              '--quotes', str(supplied), '--reader', 'independent reviewer A',
                              '--method', '원문 전체와 정책을 독립적으로 읽음'], capture_output=True, text=True)
        self.assertIn(run.returncode, (0, 1, 2), run.stderr)
        self.assertTrue(run.stdout.strip(), run.stderr)
        path = Path(json.loads(run.stdout)['review'])
        return run, path, json.loads(path.read_text())

    def test_full_original_tail_and_original_score_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = self.fixture(root)
            original = {p:p.read_bytes() for p in root.iterdir()}
            run, path, result = self.review(root, source, {'1':'끝의 선택 1을 어떻게 할까요?', '2':None})
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(result['status'], 'supported')
            self.assertEqual(result['reader']['identity'], 'independent reviewer A')
            self.assertEqual(result['execution']['task_fingerprint'], 'executed-task')
            self.assertEqual(result['execution']['judge_version'], 'executed-judge')
            self.assertEqual(result['assessment']['discovery'], 'complete')
            self.assertEqual(result['source']['required_discovery_topics'], [1])
            self.assertEqual(result['source']['discovery_exclusions'], {'2':'기존 계약'})
            self.assertGreater(result['originals'][0]['reply_chars'], 12000)
            self.assertEqual(result['matches']['1'][0]['turn'], 1)
            self.assertIn('reviews', path.parts)
            for p, contents in original.items(): self.assertEqual(p.read_bytes(), contents)
            self.assertEqual(len(list(root.glob('*.json'))), 2)
            self.assertEqual(len(list(root.rglob('*.meta.json'))), 1)
            _, second, _ = self.review(root, source, {'1':None,'2':None})
            self.assertNotEqual(path, second)
            self.assertEqual(json.loads(path.read_text())['assessment']['discovery'], 'complete')

    def test_correction_reads_all_static_turns(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = self.fixture(root, static=2)
            run, _, result = self.review(root, source, {'1':'끝의 선택 2을 어떻게 할까요?', '2':None})
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(result['originals']), 2)
            self.assertEqual(result['matches']['1'][0]['turn'], 2)

    def test_fabricated_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = self.fixture(root)
            run, _, result = self.review(root, source, {'1':'원문에 없는 질문', '2':None})
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(result['status'], 'rejected')
            self.assertEqual(result['assessment']['discovery'], 'unverified')

    def test_missing_or_corrupt_log_never_uses_summary_reply(self):
        for corruption in (None, b'not json\n', b'{}\n[bad\n', b'\xff'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = self.fixture(root)
                log = root / 'kit-codex-1.t1.jsonl'
                if corruption is None: log.unlink()
                else: log.write_bytes(corruption)
                run, _, result = self.review(root, source, {'1':'잘린 요약','2':None})
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(result['status'], 'unverified')
                self.assertEqual(result['assessment']['discovery'], 'unverified')

    def test_partial_or_malformed_independent_judgment_is_unverified(self):
        for quotes in ({'1':None}, [], {'1':False,'2':None}, {'1':'','2':None}):
            with self.subTest(quotes=quotes), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = self.fixture(root)
                run, _, result = self.review(root, source, quotes)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(result['assessment']['discovery'], 'unverified')

    def test_missing_exclusion_basis_is_not_supplied_by_current_task(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = self.fixture(root)
            data = json.loads(source.read_text()); data['discovery_exclusions'] = {}
            source.write_text(json.dumps(data))
            run, _, result = self.review(root, source, {'1':'끝의 선택 1을 어떻게 할까요?', '2':None})
            self.assertEqual(run.returncode, 2)
            self.assertEqual(result['status'], 'unverified')

    def test_all_static_logs_are_preserved_even_if_one_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = self.fixture(root, static=2)
            (root / 'kit-codex-1.t1.jsonl').unlink()
            run, _, result = self.review(root, source, {'1':'끝의 선택 2을 어떻게 할까요?', '2':None})
            self.assertEqual(run.returncode, 2)
            self.assertEqual([item['readable'] for item in result['originals']], [False, True])
            self.assertTrue(result['originals'][1]['sha256'])

    def test_missing_policy_or_execution_identity_is_not_recreated_from_current_task(self):
        for key in ('policy_topics', 'task_fingerprint', 'judge_version'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = self.fixture(root)
                data = json.loads(source.read_text()); data.pop(key); source.write_text(json.dumps(data))
                run, _, result = self.review(root, source, {'1':'끝의 선택 1을 어떻게 할까요?','2':None})
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(result['status'], 'unverified')


if __name__ == '__main__':
    unittest.main()
