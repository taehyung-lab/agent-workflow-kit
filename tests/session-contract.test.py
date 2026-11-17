"""실제 가짜 CLI를 통해 두 평가 방식의 재개·격리·기록 보존을 확인한다."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
from session import HARNESSES


class SessionContract(unittest.TestCase):
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
