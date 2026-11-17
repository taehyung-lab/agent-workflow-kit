"""평가가 실제로 전달한 정책과 같은 기준으로 결론을 내리는지 확인한다."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch



ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))
sys.path.insert(0, str(ROOT / 'evals/goalflow'))
from conversation import MockUser
from report import compare
from selftest import summary
from table import result_meta
import asked
from types import SimpleNamespace
import caseinfo


class EvaluationContract(unittest.TestCase):
    def test_fixed_policy_is_delivered_even_when_not_discovered(self):
        user = MockUser(['라벨을 만들어 주세요'], '1. 이름 보존\n2. 대여 금지',
                        'topics', lambda text, topics: {1: '이름을 보존할까요?'})
        user.observe('이름을 보존할까요? 대여는 허용하겠습니다.')
        reply = user.prompt(2)
        self.assertIn('2. 대여 금지', reply)
        self.assertNotIn('추천안대로', reply)
        self.assertEqual(user.answered, {1, 2})
        self.assertEqual(user.discovered, {1})

    def test_no_question_does_not_delegate_hidden_policy(self):
        user = MockUser(['요청'], '1. 대여 금지', 'topics', lambda *args: {})
        user.observe('그대로 구현하겠습니다')
        self.assertIn('1. 대여 금지', user.prompt(2))
        self.assertNotIn('추천안대로', user.prompt(3))

    def test_discovery_failure_does_not_claim_unauthorized_implementation(self):
        data = summary('kit', conversation_contract='fixed-policy-v1',
                       policy_topics=[1, 2], discovered=[1], answered=[1, 2])
        result = result_meta(data)
        self.assertFalse(result['check_passed'])
        self.assertEqual(result['goalflow']['final_behavior'], 'PASS')
        self.assertEqual(result['goalflow']['process'], 'ok')
        self.assertEqual(result['goalflow']['discovery'], 'incomplete')
        self.assertIn('발견', result['check_output'])

    def test_discovery_is_not_required_in_the_explicit_implementation_control(self):
        data = summary('kit', mock='all', conversation_contract='fixed-policy-v1',
                       policy_topics=[1, 2], discovered=[], answered=[1, 2])
        result = result_meta(data)
        self.assertTrue(result['check_passed'])
        self.assertEqual(result['goalflow']['discovery'], 'not-measured')

    def test_fixed_policy_without_complete_evidence_is_not_a_pass(self):
        for over in ({'policy_topics': []}, {'discovered': [1, 9]}, {'answered': [1]}, {'discovered': None}):
            data = summary('kit', conversation_contract='fixed-policy-v1',
                           policy_topics=[1, 2], discovered=[1, 2], answered=[1, 2])
            data.update(over)
            with self.subTest(over=over):
                result = result_meta(data)
                self.assertFalse(result['check_passed'])
                self.assertTrue(result['check_needs_review'])

    def test_unknown_conversation_contract_is_not_a_historical_pass(self):
        for contract in ('fixed-policy-v2', None, ''):
            result = result_meta(summary('kit', conversation_contract=contract))
            self.assertFalse(result['check_passed'])
            self.assertTrue(result['check_needs_review'])

    def test_old_records_keep_their_original_contract(self):
        data = summary('kit')
        result = result_meta(data)
        self.assertTrue(result['check_passed'])
        self.assertEqual(result['goalflow']['discovery'], 'unmeasured')
        self.assertIsNone(result['task_fingerprint'])
        self.assertIsNone(result['judge_version'])

    def compare_output(self, common=None, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            for side, passed in [('aaaaaaa', False), ('bbbbbbb', True)]:
                for run in range(3):
                    row = dict(case='same-task', harness='claude', kit_commit=side,
                               check_passed=passed, model='model', harness_version='cli',
                               mock_user_model=None, global_instructions={}, judge_version='judge',
                               observed={})
                    row.update(common or {})
                    if side == 'bbbbbbb':
                        row.update(overrides)
                    Path(directory, f'{side}-{run}.meta.json').write_text(json.dumps(row))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                compare('aaaaaaa', 'bbbbbbb', [directory])
            return out.getvalue()

    def test_incomparable_results_never_claim_improvement(self):
        text = self.compare_output(model='other-model')
        self.assertIn('비교 불가', text)
        self.assertNotIn('차이: 개선', text)

    def test_missing_comparison_evidence_is_not_equality(self):
        text = self.compare_output(judge_version=None)
        self.assertIn('비교 불가', text)
        self.assertNotIn('차이: 개선', text)

    def test_blank_metadata_is_not_comparison_evidence(self):
        text = self.compare_output(common={'model': ''})
        self.assertIn('비교 불가', text)
        self.assertNotIn('차이: 개선', text)

    def test_different_explicit_prompt_overrides_cannot_claim_improvement(self):
        text = self.compare_output(common={'prompt_configuration': {'prefix_override': 'first'}},
                                   prompt_configuration={'prefix_override': 'second'})
        self.assertIn('비교 불가', text)
        self.assertNotIn('차이: 개선', text)

    def test_delegated_oracle_changes_invalidate_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            evals = Path(directory) / 'evals'
            shutil.copytree(ROOT / 'evals', evals, ignore=shutil.ignore_patterns('samples', 'results', '__pycache__'))
            with patch.object(caseinfo, 'EVALS', evals):
                task = evals / 'goalflow/tasks/archive-correction'
                before = caseinfo.goalflow_fingerprints(task)
                delegated = evals / 'goalflow/tasks/archive-ambiguity/oracle.py'
                delegated.write_text(delegated.read_text() + '\n# changed judge\n')
                after = caseinfo.goalflow_fingerprints(task)
            self.assertNotEqual(before['judge_version'], after['judge_version'])
            self.assertEqual(before['task_fingerprint'], after['task_fingerprint'])

    def test_skill_baseline_needs_its_installed_content_identity(self):
        text = self.compare_output(common={'goalflow': {'arm': 'skills', 'mock': 'all'}})
        self.assertIn('비교 불가', text)
        self.assertNotIn('차이: 개선', text)

    def test_malformed_classifier_output_is_reviewable_failure(self):
        output = '{"quotes":{"1":"policy?"}}\n{"quotes":{"1":null}}'
        with patch.object(asked.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stdout=output,stderr='')):
            with self.assertRaises(RuntimeError):
                asked.surfaced('policy?', '1. policy')

    def test_paraphrased_quote_is_unverified_not_a_missing_choice(self):
        reply = "기존 시트도 저장된 이름을 표시하도록 할까요?"
        output = json.dumps({"quotes": {"1": "기존 인쇄 시트도 저장된 이름을 표시하도록 할까요?"}}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(asked.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output, stderr='')):
            with self.assertRaises(RuntimeError):
                asked.surfaced(reply, '1. 기존 이름', record_dir=directory)
            record = next(Path(directory).iterdir())
            self.assertEqual((record / 'stdout.txt').read_text(), output)

    def test_missing_topic_is_not_an_explicit_null(self):
        for quotes in ({"1": None}, {"1": None, "2": False}, []):
            with self.subTest(quotes=quotes), patch.object(asked.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"quotes": quotes}), stderr='')):
                with self.assertRaises(RuntimeError):
                    asked.surfaced('policy?', '1. first\n2. second')

    def test_exact_quote_and_explicit_null_keep_their_distinct_meaning(self):
        output = json.dumps({"quotes": {"1": "정확한 코드로 고칠까요?", "2": None}}, ensure_ascii=False)
        with patch.object(asked.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output, stderr='')):
            self.assertEqual(asked.surfaced("**정확한 코드로 고칠까요?**", "1. 코드\n2. 이름"), {1: "정확한 코드로 고칠까요?"})

    def test_classifier_timeout_preserves_partial_raw_output(self):
        error = subprocess.TimeoutExpired(['claude'], 300, output=b'partial reply', stderr=b'partial error')
        with tempfile.TemporaryDirectory() as directory, patch.object(asked.subprocess, 'run', side_effect=error):
            with self.assertRaises(RuntimeError):
                asked.surfaced('policy?', '1. policy', record_dir=directory)
            record = next(Path(directory).iterdir())
            self.assertEqual((record / 'stdout.txt').read_bytes(), b'partial reply')
            self.assertEqual((record / 'stderr.txt').read_bytes(), b'partial error')
            self.assertEqual(json.loads((record / 'execution.json').read_text())['status'], 'timeout')

    def test_matching_conditions_can_describe_the_observed_difference(self):
        self.assertIn('차이: 개선', self.compare_output())

    def test_result_interpretation_does_not_import_session_execution(self):
        command = [sys.executable, '-c',
                   "import sys; sys.path.insert(0,'evals'); import result; assert 'session' not in sys.modules"]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == '__main__':
    unittest.main()
