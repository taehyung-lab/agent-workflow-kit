"""실제 가짜 CLI를 통해 두 평가 방식의 재개·격리·기록 보존을 확인한다."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
import subprocess
from session import HARNESSES
import run
from types import SimpleNamespace


class SessionContract(unittest.TestCase):
    def test_comparison_claude_does_not_inherit_parent_input(self):
        session = HARNESSES['claude']('/project', profile='comparison')
        with patch.object(session, '_turn') as turn:
            session.start('request', '/out')
            self.assertEqual(turn.call_args.kwargs.get('stdin'), subprocess.DEVNULL)
            session.session_id = 'session'
            session.resume('answer', '/out')
            self.assertEqual(turn.call_args.kwargs.get('stdin'), subprocess.DEVNULL)

    def test_repeat_comparison_respects_existing_run_offset(self):
        calls = []
        def fake(command, **kwargs):
            if 'env' in kwargs:
                calls.append(kwargs['env']['EVALS_RUN_OFFSET'])
            return SimpleNamespace(returncode=0)
        with patch.dict(os.environ, {'EVALS_RUN_OFFSET': '1'}), patch.object(run, 'resolve', side_effect=lambda r: r), patch.object(run.subprocess, 'run', side_effect=fake):
            run.compare('case', 'base..target', 'codex', 2)
        self.assertEqual(calls, ['1', '1', '2', '2'])

    def test_existing_result_is_rejected_before_checkout_or_model_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'case-abcdefg-codex-1.jsonl'
            evidence.write_text('previous raw evidence')
            with patch.object(run.session, 'kit_checkout', side_effect=RuntimeError('must not checkout')), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run.run_once('case', root, 'ref', 'abcdefg', 'codex', 1, str(root), {})
            self.assertEqual(evidence.read_text(), 'previous raw evidence')

    def test_comparison_uses_shared_start_resume_and_preserves_rollout(self):
        for name in ('claude', 'codex'):
            with self.subTest(harness=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = root / 'project'
                project.mkdir()
                fake = root / name
                fake.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
print(json.dumps({'session_id':'shared-id', 'thread_id':'shared-id'}))
print(json.dumps({'args':sys.argv[1:],'parent':os.environ.get('CODEX_THREAD_ID'),
                  'home':os.environ.get('HOME'),'codex_home':os.environ.get('CODEX_HOME')}))
if os.environ.get('CODEX_HOME'):
    p=Path(os.environ['CODEX_HOME'])/'sessions';p.mkdir(exist_ok=True)
    (p/'rollout-shared-id.jsonl').write_text('raw rollout')
''')
                fake.chmod(0o755)
                with patch.dict(os.environ, {'PATH':str(root)+os.pathsep+os.environ['PATH'],
                                             'CODEX_THREAD_ID':'parent-session'}):
                    session = HARNESSES[name](project, profile='comparison')
                    try:
                        first = session.start('first request', root / 'first')
                        second = session.resume('user answer', root / 'second')
                        self.assertEqual(first.session_id, 'shared-id')
                        self.assertEqual(second.exit_code, 0)
                        record = json.loads(Path(second.log).read_text().splitlines()[1])
                        self.assertIn('shared-id', record['args'])
                        self.assertIsNone(record['parent'])
                        self.assertTrue(Path(second.err).exists())
                        if name == 'claude':
                            self.assertIn('project', record['args'])
                            self.assertIn('80', record['args'])
                        else:
                            self.assertNotEqual(record['home'], str(Path.home()))
                    finally:
                        session.close(root / 'saved-rollout.jsonl')
                    if name == 'codex':
                        self.assertEqual((root / 'saved-rollout.jsonl').read_text(), 'raw rollout')
                        self.assertFalse(Path(record['codex_home']).exists())


if __name__ == '__main__':
    unittest.main()
