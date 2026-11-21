"""특정 턴의 실제 생성·반환을 원본으로 관찰한다. 모델을 실행하지 않는다."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))
sys.path.insert(0, str(ROOT / 'evals/goalflow'))
import observe
import session
import pins
import asked
import turnwatch
from transcript import agent_events


def event(kind, payload):
    return {'type': kind, 'payload': payload}


def codex_turn():
    return [event('event_msg', {'type': 'task_started', 'turn_id': 't1'}),
            event('response_item', {'type': 'function_call', 'name': 'spawn_agent', 'call_id': 'c1',
                  'arguments': json.dumps({'task_name': 'reader', 'message': 'PRIVATE_ENCRYPTED_INPUT'})}),
            event('response_item', {'type': 'function_call_output', 'call_id': 'c1',
                  'output': json.dumps({'task_name': '/root/reader'})}),
            event('response_item', {'type': 'agent_message', 'content': [{'type': 'input_text',
                  'text': 'Message Type: FINAL_ANSWER\nTask name: /root\nSender: /root/reader\nPayload:\nloan requires a decision'}]}),
            event('event_msg', {'type': 'task_complete', 'turn_id': 't1'})]


class AgentEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'run.t1.jsonl'
        self.write(self.log, [{'type': 'thread.started'}, {'type': 'turn.completed'}])
        self.rollout = self.root / 'run.rollout.jsonl'

    def write(self, path, events):
        path.write_text(''.join(json.dumps(e) + '\n' for e in events))

    def observed(self):
        return observe.agent_evidence(self.log, 'codex', 1, stage='requirements', rollout=self.rollout)

    def test_actual_rollouts_preserve_first_turn_spawn_result_and_plain_return(self):
        if not (ROOT / 'work/feature-completion/models/labels-baseline/kit-codex-1.rollout.jsonl').is_file():
            self.skipTest('local raw investigation artifacts are not installed')
        for side, lines in [('baseline', (33, 36, 78)), ('candidate', (36, 39, 98))]:
            with self.subTest(side=side):
                original = ROOT / f'work/feature-completion/models/labels-{side}/kit-codex-1.rollout.jsonl'
                # These are local investigation artifacts, not distributable fixtures.
                if not original.is_file():
                    continue
                result = observe.agent_evidence(self.log, 'codex', 1, stage='requirements', rollout=original)
                self.assertEqual(result['state'], 'observed', result)
                agent = next(a for a in result['agents'] if a.get('spawn_line') == lines[0])
                self.assertEqual(agent['result_line'], lines[1])
                self.assertEqual(agent['returns'][0]['line'], lines[2])
                self.assertIn('L1', agent['returns'][0]['text'])
                self.assertNotIn('message', agent)

    def test_first_turn_is_not_replaced_by_the_final_turn(self):
        self.write(self.rollout, codex_turn() + [event('event_msg', {'type': 'task_started', 'turn_id': 't2'}),
                   event('event_msg', {'type': 'task_complete', 'turn_id': 't2'})])
        result = self.observed()
        self.assertEqual(result['state'], 'observed', result)
        self.assertEqual(result['agents'][0]['state'], 'returned')
        self.assertNotIn('PRIVATE_ENCRYPTED_INPUT', json.dumps(result))
        inferred = observe.agent_evidence(self.log, 'codex', 1, stage='requirements')
        self.assertEqual(inferred, result)

    def test_missing_damaged_or_incomplete_source_is_unverified(self):
        self.assertEqual(self.observed()['state'], 'unverified')
        self.rollout.write_text('{broken\n')
        self.assertEqual(self.observed()['state'], 'unverified')
        self.write(self.rollout, codex_turn()[:-1])
        result = self.observed()
        self.assertEqual(result['state'], 'unverified')
        self.assertTrue(result['agents'])

    def test_complete_turn_without_spawn_is_none_and_empty_wait_is_not_spawn(self):
        self.write(self.rollout, [event('event_msg', {'type': 'task_started'}),
                   event('response_item', {'type': 'function_call', 'name': 'wait', 'call_id': 'w',
                         'arguments': '{"receiver_thread_ids": []}'}),
                   event('event_msg', {'type': 'task_complete'})])
        self.assertEqual(self.observed()['state'], 'none')

    def test_unreturned_spawn_is_not_complete_evidence(self):
        events = codex_turn(); events.pop(3)
        self.write(self.rollout, events)
        result = self.observed()
        self.assertEqual(result['state'], 'unverified')
        self.assertEqual(result['agents'][0]['state'], 'started')

    def test_claude_matches_actual_tool_use_and_tool_result(self):
        self.write(self.log, [
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'a1', 'name': 'Agent',
             'input': {'description': 'reader', 'prompt': 'PRIVATE_PROMPT'}}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a1', 'content': 'loan requires a decision'}]}},
            {'type': 'result', 'is_error': False, 'result': 'done'}])
        result = observe.agent_evidence(self.log, 'claude', 1, stage='requirements')
        self.assertEqual(result['state'], 'observed', result)
        self.assertEqual(result['agents'][0]['returns'][0]['text'], 'loan requires a decision')
        self.assertNotIn('PRIVATE_PROMPT', json.dumps(result))

    def test_claude_background_launch_is_not_a_final_worker_return(self):
        for tool in ('Agent', 'Task'):
            with self.subTest(tool=tool):
                self.write(self.log, [
                    {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'a1', 'name': tool,
                     'input': {'run_in_background': True, 'prompt': 'PRIVATE_PROMPT'}}]}},
                    {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a1',
                     'content': 'Async agent launched successfully. agentId: worker-1'}]}},
                    {'type': 'result', 'is_error': False, 'result': 'parent completed'}])
                result = agent_events(self.log, 'claude')
                self.assertEqual(result['state'], 'unverified', result)
                self.assertTrue(result['turn_complete'])
                self.assertEqual(result['agents'][0]['state'], 'started')
                self.assertEqual(result['agents'][0]['returns'], [])
                self.assertTrue(result['agents'][0]['run_in_background'])

    def test_claude_failures_and_unfinished_turns_remain_distinct(self):
        for background in (False, True):
            for failed in (False, True):
                with self.subTest(background=background, failed=failed):
                    events = [
                        {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'a1', 'name': 'Agent',
                         'input': {'run_in_background': background}}]}},
                        {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a1',
                         'is_error': failed, 'content': 'execution failed' if failed else 'worker reply or launch notice'}]}}]
                    self.write(self.log, events)
                    self.assertEqual(agent_events(self.log, 'claude')['state'], 'unverified')
                    if failed:
                        self.write(self.log, events + [{'type': 'result', 'is_error': False}])
                        result = agent_events(self.log, 'claude')
                        self.assertEqual(result['state'], 'observed', result)
                        self.assertEqual(result['agents'][0]['state'], 'failed')
                        self.assertEqual(result['agents'][0]['returns'], [])

    def test_claude_requires_unique_nonempty_call_ids_to_pair_results(self):
        def use(call_id, tool='Agent'):
            return {'type': 'assistant', 'message': {'content': [dict(type='tool_use', name=tool, input={}, **call_id)]}}
        def reply(call_id):
            return {'type': 'user', 'message': {'content': [dict(type='tool_result', content='unlinked answer', **call_id)]}}
        cases = [(str(value), [use({'id': value}), reply({'tool_use_id': value})]) for value in (None, '', '  ', 7)]
        cases += [('missing', [use({}), reply({})]),
                  ('duplicate calls', [use({'id': 'a1'}), reply({'tool_use_id': 'a1'}),
                                       use({'id': 'a1'}), reply({'tool_use_id': 'a1'})]),
                  ('duplicate results', [use({'id': 'a1'}), reply({'tool_use_id': 'a1'}), reply({'tool_use_id': 'a1'})]),
                  ('other tool collision', [use({'id': 'a1'}), use({'id': 'a1'}, 'Bash'), reply({'tool_use_id': 'a1'})])]
        for label, events in cases:
            with self.subTest(case=label):
                self.write(self.log, events + [{'type': 'result', 'is_error': False}])
                result = agent_events(self.log, 'claude')
                self.assertEqual(result['state'], 'unverified', result)
                self.assertFalse(any(a['returns'] for a in result['agents']))

    def test_compare_saves_source_once_before_observation_and_summary(self):
        owner = self
        class Harness:
            def __init__(self, project, **kwargs): self.session_id = 'fake'; self.closes = 0
            def start(self, prompt, prefix):
                log = Path(str(prefix) + '.jsonl')
                owner.write(log, [{'type': 'thread.started'}, {'type': 'turn.completed'}])
                return SimpleNamespace(exit_code=0, log=log)
            resume = start
            def instruction_context(self): return {'captured_before_close': True}
            def close(self, path):
                self.closes += 1
                owner.assertEqual(self.closes, 1, 'close twice would truncate the source')
                owner.write(Path(path), codex_turn())
        class Watch:
            def __init__(self, project): pass
            def stop(self): return {}
        with patch.dict(os.environ, {'CMP_TASK': 'labels', 'MOCK': 'all'}), \
             patch.object(sys, 'argv', ['compare.py', 'none', 'codex', '1', str(self.root/'results')]), \
             patch.dict(session.HARNESSES, {'codex': Harness}), \
             patch.object(pins, 'check', return_value=None), patch.object(pins, 'cli_version', return_value='fake'), \
             patch.object(turnwatch, 'Watch', Watch), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT/'evals/goalflow/compare.py'), run_name='__main__')
        summary = json.loads((self.root/'results/none-codex-1.json').read_text())
        self.assertEqual(summary['turns'][0]['agent_evidence']['state'], 'observed')
        self.assertEqual(summary['turns'][1]['agent_evidence']['state'], 'unverified')
        meta = json.loads((self.root/'results/none-codex-1.meta.json').read_text())
        self.assertEqual(meta['goalflow']['agent_evidence'][0]['state'], 'observed')


if __name__ == '__main__':
    unittest.main()
