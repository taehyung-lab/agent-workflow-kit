"""전체 검사 진입점이 미커밋 상태를 고정하고 원본 변경과 분리하는지 확인한다."""
import shutil, subprocess, tempfile, unittest
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / 'evals/selftest.sh'

class SnapshotTest(unittest.TestCase):
 def test_run_is_fixed_and_original_index_untouched(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); repo=root/'repo'; (repo/'evals').mkdir(parents=True)
   shutil.copy2(WRAPPER,repo/'evals/selftest.sh')
   def git(*args):
    return subprocess.check_output(['git',*args],cwd=repo)
   git('init','-q');git('config','user.name','test');git('config','user.email','test@invalid')
   (repo/'value').write_text('committed')
   (repo/'evals/selftest-run.sh').write_text(r'''#!/usr/bin/env bash
set -eu
# 원본을 바꿔도 이후 읽는 자료와 실행 코드는 최초 고정본이어야 한다.
printf changed > "$ORIGINAL/value"
printf 'exit 99\n' > "$ORIGINAL/evals/later.sh"
test "$(cat value)" = uncommitted
bash evals/later.sh
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
exit 7
''')
   (repo/'evals/later.sh').write_text('exit 0\n')
   git('add','.');git('commit','-qm','start')
   head=git('rev-parse','HEAD');index=(repo/'.git/index').read_bytes()
   (repo/'value').write_text('uncommitted')
   import os
   result=subprocess.run(['bash',str(repo/'evals/selftest.sh')],cwd=root,env={**os.environ,'ORIGINAL':str(repo)},capture_output=True,text=True,timeout=20)
   self.assertEqual(result.returncode,7,result.stdout+result.stderr)
   self.assertIn('시험 고정본:',result.stdout)
   self.assertEqual(git('rev-parse','HEAD'),head)
   self.assertEqual((repo/'.git/index').read_bytes(),index)
   self.assertEqual((repo/'value').read_text(),'changed')

if __name__=='__main__': unittest.main()
