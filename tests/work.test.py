"""작업 기록의 공개 명령으로 원문·검사·증거 만료를 확인한다."""
import json, subprocess, tempfile, unittest
from pathlib import Path
TOOL = Path(__file__).resolve().parents[1] / '.agents/skills/wf-verify/work.py'
class WorkTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name); self.repo=self.root/'repo'; self.repo.mkdir()
  for args in [('init','-q'),('config','user.name','test'),('config','user.email','test@invalid')]: self.git(*args)
  (self.repo/'app.txt').write_text('before'); self.git('add','.');self.git('commit','-qm','start')
  self.work=self.root/'work'; self.req=self.root/'request.txt'; self.req.write_bytes('원문 그대로\n후속 줄\n'.encode())
  self.plan=self.root/'plan.json'
  self.data={'targets':[{'name':'app','path':str(self.repo),'base':self.git('rev-parse','HEAD').strip()}], 'requirements':[{'id':'R1','expect':'기대 동작','source':[1],'state':'확정'}], 'checks':[{'id':'C1','target':'app','requirements':['R1'],'argv':['python3','-c','print("ok")']} ]}
 def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.repo,text=True)
 def runwork(self,*args):
  r=subprocess.run(['python3',str(TOOL),*args,str(self.work)],cwd=self.repo,text=True,capture_output=True)
  try: out=json.loads(r.stdout)
  except ValueError: self.fail(r.stderr+r.stdout)
  return r.returncode,out
 def record(self):
  self.plan.write_text(json.dumps(self.data)); return self.runwork('record','--request',str(self.req),'--plan',str(self.plan))
 def test_record_and_check(self):
  rc,r=self.record();self.assertEqual(rc,0);self.assertEqual((self.work/'sources/0001.txt').read_bytes(),self.req.read_bytes())
  rc,r=self.runwork('check');self.assertEqual(r['check'],'PASS');self.assertEqual(r['completion'],'review-missing');self.assertNotEqual(rc,0)
 def test_failure(self):
  self.data['checks'][0]['argv']=['python3','-c','raise SystemExit(1)'];self.record()
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'check-failed')
 def test_missing_coverage(self):
  self.data['checks']=[];self.record();rc,r=self.runwork('check');self.assertEqual(r['completion'],'unverified')
 def test_waiting_never_executes(self):
  self.data['requirements'][0]['state']='미정';self.data['checks'][0]['argv']=['python3','-c','open("unexpected","w").write("bad")'];self.record()
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'waiting-user');self.assertFalse((self.repo/'unexpected').exists())
 def test_source_tamper(self):
  self.record();(self.work/'sources/0001.txt').write_text('changed');rc,r=self.runwork('check');self.assertEqual(r['completion'],'unverified')
 def test_check_mutation(self):
  self.data['checks'][0]['argv']=['python3','-c','open("app.txt","w").write("changed")'];self.record()
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'unverified')
 def test_unknown_source_rejected(self):
  self.data['requirements'][0]['source']=[99];rc,r=self.record();self.assertNotEqual(rc,0)
 def test_timeout(self):
  self.data['checks'][0].update(argv=['python3','-c','import time;time.sleep(5)'],timeout=0.05);self.record()
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'unverified')
 def test_review_and_stale_evidence(self):
  self.record();(self.repo/'app.txt').write_text('after');self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  self.assertIn('ok',Path(r['prompt_file']).read_text())
  answer=self.root/'answer.txt';answer.write_text(json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'원문과 실행 대조'}]}))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
  (self.repo/'app.txt').write_text('later')
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified')
 def test_followup_invalidates_check(self):
  self.record();self.runwork('check');self.req.write_text('후속 답')
  self.runwork('record','--request',str(self.req));rc,r=self.runwork('review');self.assertEqual(r['completion'],'unverified')
 def test_new_check_requires_new_review(self):
  self.record();(self.repo/'app.txt').write_text('after');self.runwork('check');self.runwork('review');self.runwork('check')
  answer=self.root/'answer.txt';answer.write_text(json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'검토'}]}))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified',r)
 def test_review_output_is_frozen(self):
  self.data['checks'][0]['argv']=['python3','-c','print("UNIQUE_" + "EXECUTION_PROOF")'];self.record();(self.repo/'app.txt').write_text('after');self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  self.assertIn('UNIQUE_EXECUTION_PROOF',Path(r['prompt_file']).read_text())
 def test_optional_review(self):
  self.data['review_required']=False;self.record();rc,r=self.runwork('check');self.assertEqual(r['completion'],'verified')
 def test_home_two_targets_keep_pins_and_expire_together(self):
  import shutil
  second=self.root/'second';shutil.copytree(self.repo,second)
  for root,version in [(self.repo,'team-v1'),(second,'team-v2')]:
   (root/'.agents').mkdir();(root/'.agents/agent-workflow-kit.version').write_text(version)
  self.data['targets'].append({'name':'other','path':str(second),'base':self.data['targets'][0]['base']})
  self.data['checks'].append({'id':'C2','target':'other','requirements':['R1'],'argv':['python3','-c','print("other")']})
  self.record();(second/'app.txt').write_text('after');self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  prompt=Path(r['prompt_file']).read_text();self.assertIn('other',prompt);self.assertIn('+after',prompt)
  self.assertEqual((self.repo/'.agents/agent-workflow-kit.version').read_text(),'team-v1')
  self.assertEqual((second/'.agents/agent-workflow-kit.version').read_text(),'team-v2')
  (second/'app.txt').write_text('later');rc,r=self.runwork('review');self.assertEqual(r['completion'],'unverified')
 def test_review_requirements_do_not_depend_on_markdown_table_syntax(self):
  self.data['requirements'][0]['expect']='이름 A | B를 그대로 보존\n두 번째 줄도 보존'
  self.record();(self.repo/'app.txt').write_text('after');self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  pending=json.loads((Path(r['kept'])/'pending.json').read_text())
  self.assertEqual(pending['required'],['R1'])
  self.assertFalse(any(f['role']=='map' for f in pending['inputs']['files']))
  prompt=Path(r['prompt_file']).read_text()
  self.assertIn('이름 A | B를 그대로 보존',prompt)
  # 읽기용 지도를 고쳐도 현재 검토가 받은 원문·요구·검사 근거는 바뀌지 않는다.
  (self.work/'work.md').write_text('읽기용 지도 레이아웃 변경')
  answer=self.root/'answer.txt';answer.write_text(json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'원문 대조'}]}))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
if __name__=='__main__':unittest.main()
