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
  if 'prompt_file' in out:
   self.required=json.loads((Path(out['kept'])/'pending.json').read_text())['required']
  return r.returncode,out
 def review_answer(self,evidence):
  return json.dumps({'verdict':'OK','conditions':[{'id':rid,'result':'충족','evidence':evidence} for rid in self.required]})
 def record(self):
  self.plan.write_text(json.dumps(self.data)); return self.runwork('record','--request',str(self.req),'--plan',str(self.plan))
 def test_record_and_check(self):
  rc,r=self.record();self.assertEqual(rc,0);self.assertEqual((self.work/'sources/0001.txt').read_bytes(),self.req.read_bytes())
  rc,r=self.runwork('check');self.assertEqual(r['check'],'PASS');self.assertEqual(r['completion'],'review-missing');self.assertNotEqual(rc,0)
 def test_review_does_not_depend_on_cli_output_format(self):
  self.record();self.runwork('check')
  # A CLI may add a human-facing notice after its JSON. Internal review must
  # consume the structured result, not capture and parse that CLI output.
  runner='''import sys
sys.path.insert(0, sys.argv[1])
import work
prepare = work.verify.prepare
cli = work.verify.cli
def decorated(function):
 def call(*args, **kwargs):
  code = function(*args, **kwargs)
  print("CLI presentation changed")
  return code
 return call
work.verify.prepare = decorated(prepare)
work.verify.cli = decorated(cli)
sys.argv = ["work.py", "review", *sys.argv[2:]]
sys.exit(work.main())
'''
  def review(*args):
   run=subprocess.run(['python3','-c',runner,str(TOOL.parent),*args,str(self.work)],cwd=self.repo,text=True,capture_output=True)
   return run.returncode,json.loads(run.stdout)
  rc,prepared=review();self.assertEqual(rc,0,prepared)
  pending=json.loads((Path(prepared['kept'])/'pending.json').read_text());self.required=pending['required']
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('structured review result'))
  rc,result=review('--answer',str(answer));self.assertEqual(rc,0,result)
  self.assertEqual(result['completion'],'verified')
 def test_target_name_agrees_with_direct_map_review(self):
  self.data['targets'][0]['name']='payment.api';self.data['checks'][0]['target']='payment.api'
  mapfile=self.repo/'map.md'
  mapfile.write_text('## 맥락\n\n| 대상 | 경로 | 기준 커밋 |\n| --- | --- | --- |\n'
                     f'| payment.api | {self.repo} | HEAD |\n\n## 기준\n요청 원문: keep behavior\n')
  direct=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'prepare','--map',str(mapfile),'--output',str(self.req)],cwd=self.repo,text=True,capture_output=True)
  self.assertEqual(direct.returncode,0,direct.stderr+direct.stdout)
  rc,recorded=self.record();self.assertEqual(rc,0,recorded)
  self.runwork('check');rc,prepared=self.runwork('review');self.assertEqual(rc,0,prepared)
  self.assertTrue((Path(prepared['target_dir'])/'payment.api').is_dir())
 def test_failure(self):
  self.data['checks'][0]['argv']=['python3','-c','raise SystemExit(1)'];self.record()
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'check-failed')
 def test_check_failure_does_not_authorize_replacing_expected_result(self):
  self.data['checks'][0]['argv']=['python3','-c','raise SystemExit(1)']
  self.record()
  _,result=self.runwork('check')
  self.assertEqual(result['check'],'FAIL')
  self.data['requirements'][0]['expect']='구현이 실제로 한 일'
  self.plan.write_text(json.dumps(self.data))
  code,result=self.runwork('record','--plan',str(self.plan))
  self.assertNotEqual(code,0)
  self.assertIn('후속 사용자 원문',result['reason'])
 def test_unrelated_reply_does_not_change_an_approved_result(self):
  self.record()
  self.req.write_text('표시 이름은 한글로 해 주세요.')
  self.runwork('record','--request',str(self.req))
  self.data['requirements'][0].update(expect='구현이 한 일',source=[1,2])
  self.plan.write_text(json.dumps(self.data))
  code,result=self.runwork('record','--plan',str(self.plan))
  self.assertNotEqual(code,0)
  self.assertIn('--reply-to',result['reason'])
  self.req.write_text('R1은 처음과 다른 결과로 바꿔 주세요.')
  self.data['requirements'][0]['source']=[3]
  self.plan.write_text(json.dumps(self.data))
  code,result=self.runwork('record','--request',str(self.req),'--reply-to','R1','--plan',str(self.plan))
  self.assertEqual(code,0,result)
  self.data['review_required']=False
  self.plan.write_text(json.dumps(self.data))
  code,result=self.runwork('record','--plan',str(self.plan))
  self.assertNotEqual(code,0)
  self.assertIn('독립 검토',result['reason'])
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
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('원문과 실행 대조'))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
  (self.repo/'app.txt').write_text('later')
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified')
 def test_followup_invalidates_check(self):
  self.record();self.runwork('check');self.req.write_text('후속 답')
  self.runwork('record','--request',str(self.req));rc,r=self.runwork('review');self.assertEqual(r['completion'],'unverified')
 def test_new_check_requires_new_review(self):
  self.record();(self.repo/'app.txt').write_text('after');self.runwork('check');self.runwork('review');self.runwork('check')
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('검토'))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified',r)
 def test_review_output_is_frozen(self):
  self.data['checks'][0]['argv']=['python3','-c','print("UNIQUE_" + "EXECUTION_PROOF")'];self.record();(self.repo/'app.txt').write_text('after');self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  self.assertIn('UNIQUE_EXECUTION_PROOF',Path(r['prompt_file']).read_text())
 def test_large_review_keeps_complete_diff_and_expires_if_attachment_changes(self):
  self.record()
  (self.repo/'app.txt').write_text('실제 변경\n' * 10000 + 'LAST_CHANGE_MARKER\n')
  self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  pending=json.loads((Path(r['kept'])/'pending.json').read_text())
  attachments=[f for f in pending['inputs']['files'] if f['role']=='diff']
  self.assertEqual(len(attachments),1)
  attachment=Path(attachments[0]['path'])
  self.assertIn('LAST_CHANGE_MARKER',attachment.read_text())
  self.assertIn(str(attachment),Path(r['prompt_file']).read_text())
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('전체 변경 파일의 마지막 변경까지 대조'))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
  attachment.write_text('검토한 변경의 일부를 제거')
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified',r)
 def test_missing_attachment_can_be_corrected_and_retried(self):
  self.record();extra=self.root/'extra.txt';extra.write_text('evidence')
  rc,r=self.runwork('record','--evidence',str(extra),'--evidence',str(self.root/'missing'))
  self.assertNotEqual(rc,0)
  self.assertFalse((self.work/'evidence/0001.txt').exists())
  rc,r=self.runwork('record','--evidence',str(extra));self.assertEqual(rc,0,r)
 def test_review_keeps_failed_run_criteria_and_supplement(self):
  self.data['checks'][0]['argv']=['python3','-c','print("BEFORE_FAILURE");raise SystemExit(1)'];self.record();self.runwork('check')
  self.data['checks'][0]['argv']=['python3','-c','print("AFTER_SUCCESS")'];self.plan.write_text(json.dumps(self.data))
  self.runwork('record','--plan',str(self.plan))
  extra=self.root/'extra.txt';extra.write_bytes(b'INDEPENDENT_OBSERVATION\r\n')
  rc,r=self.runwork('record','--evidence',str(extra));self.assertEqual(rc,0,r)
  self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  prompt=Path(r['prompt_file']).read_text()
  for marker in ['BEFORE_FAILURE','AFTER_SUCCESS','INDEPENDENT_OBSERVATION','raise SystemExit(1)']:
   self.assertIn(marker,prompt)
  self.assertEqual((self.work/'evidence/0001.txt').read_bytes(),extra.read_bytes())
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('과거 실패와 현재 성공을 별도로 대조'))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
  (self.work/'evidence/0001.txt').write_text('changed')
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'unverified',r)
 def test_historical_log_tamper_blocks_review_and_finish(self):
  self.record();self.runwork('check')
  first=json.loads((self.work/'journal.jsonl').read_text().splitlines()[-1])
  self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('전후 근거 대조'))
  kept=r['kept']
  Path(first['results'][0]['output']).write_text('changed')
  direct=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'finish','--round',kept,'--check','PASS'],cwd=self.repo,input=answer.read_text(),text=True,capture_output=True)
  self.assertEqual(json.loads(direct.stdout)['completion'],'unverified')
  for args in [('review',),('review','--answer',str(answer))]:
   rc,r=self.runwork(*args);self.assertEqual(r['completion'],'unverified',r)
 def test_single_target_uses_its_own_review_rules(self):
  (self.repo/'AGENTS.md').write_text('대상 고정 규칙')
  rules=self.repo/'.agents/skills/wf-verify/SKILL.md';rules.parent.mkdir(parents=True);rules.write_text('대상 검토자 기준')
  self.record();self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  frozen=Path(r['target_dir'])/'app'
  prompt=Path(r['prompt_file']).read_text()
  self.assertIn(str(frozen/'AGENTS.md'),prompt)
  self.assertIn(str(frozen/'.agents/skills/wf-verify/SKILL.md'),prompt)
  self.assertNotIn('여러 저장소 작업이다',prompt)
  self.assertNotIn('그 폴더의 것을 쓰지 않는다',prompt)
  direct=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'prepare','--request',str(self.req),'--output',str(self.req)],cwd=self.repo,text=True,capture_output=True)
  self.assertEqual(direct.returncode,0,direct.stderr+direct.stdout)
  prepared=json.loads(direct.stdout);direct_prompt=Path(prepared['prompt_file']).read_text()
  self.assertIn(str(Path(prepared['target_dir'])/'.agents/skills/wf-verify/SKILL.md'),direct_prompt)
  self.assertIn('단일 저장소 작업이다',direct_prompt)
 def test_target_review_cannot_be_omitted_or_failed(self):
  self.record();self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  pending=json.loads((Path(r['kept'])/'pending.json').read_text())
  internal=set(pending['required'])-{'R1'}
  self.assertEqual(len(internal),1)
  answer=self.root/'answer.txt'
  answer.write_text(json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'요청 결과 확인'}]}))
  rc,result=self.runwork('review','--answer',str(answer));self.assertEqual(result['completion'],'unverified')
  for state in ['미확인','미충족']:
   conditions=[{'id':'R1','result':'충족','evidence':'요청 결과 확인'}]+[{'id':rid,'result':state,'evidence':'대상 필수 검토 누락 또는 실패'} for rid in internal]
   answer.write_text(json.dumps({'verdict':'OK','conditions':conditions}))
   rc,result=self.runwork('review','--answer',str(answer));self.assertNotEqual(result['completion'],'verified')
 def test_optional_review(self):
  self.data['review_required']=False;self.record();rc,r=self.runwork('check');self.assertEqual(r['completion'],'verified')
 def test_home_two_targets_keep_pins_and_expire_together(self):
  import shutil
  second=self.root/'second';shutil.copytree(self.repo,second)
  for root,version in [(self.repo,'team-v1'),(second,'team-v2')]:
   (root/'.agents').mkdir();(root/'.agents/agent-workflow-kit.version').write_text(version)
   (root/'AGENTS.md').write_text('프로젝트 규칙 '+version)
   rules=root/'.agents/skills/wf-verify/SKILL.md';rules.parent.mkdir(parents=True);rules.write_text('검토 기준 '+version)
  self.data['targets'].append({'name':'other','path':str(second),'base':self.data['targets'][0]['base']})
  self.data['checks'].append({'id':'C2','target':'other','requirements':['R1'],'argv':['python3','-c','print("other")']})
  self.record();(second/'app.txt').write_text('after');self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  prompt=Path(r['prompt_file']).read_text();self.assertIn('other',prompt);self.assertIn('+after',prompt)
  for name in ['app','other']:
   self.assertIn(str(Path(r['target_dir'])/name/'.agents/skills/wf-verify/SKILL.md'),prompt)
  self.assertEqual(set(self.required),{'R1','TV1','TV2'})
  self.assertEqual((self.repo/'.agents/agent-workflow-kit.version').read_text(),'team-v1')
  self.assertEqual((second/'.agents/agent-workflow-kit.version').read_text(),'team-v2')
  (second/'app.txt').write_text('later');rc,r=self.runwork('review');self.assertEqual(r['completion'],'unverified')
 def test_ignored_pinned_rules_are_frozen_and_used(self):
  (self.repo/'.gitignore').write_text('.agents/\n')
  rules=self.repo/'.agents/skills/wf-verify/SKILL.md';rules.parent.mkdir(parents=True);rules.write_text('별도 역할의 검토가 필수')
  (self.repo/'.agents/agent-workflow-kit.version').write_text('team-old')
  self.record();self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  frozen=Path(r['target_dir'])/'app'
  self.assertEqual((frozen/'.agents/agent-workflow-kit.version').read_text(),'team-old')
  self.assertEqual((frozen/'.agents/skills/wf-verify/SKILL.md').read_text(),rules.read_text())
  prompt=Path(r['prompt_file']).read_text()
  self.assertIn(str(frozen/'.agents/skills/wf-verify/SKILL.md'),prompt)
  self.assertNotIn('설치 키트가 없으면',prompt)
 def test_linked_rule_directory_is_frozen_without_writing_source(self):
  outside=self.root/'shared-rules';rules=outside/'skills/wf-verify/SKILL.md';rules.parent.mkdir(parents=True)
  rules.write_text('共有 검토 기준');(outside/'agent-workflow-kit.version').write_text('team-shared')
  (self.repo/'.agents').symlink_to(outside,target_is_directory=True)
  self.record();self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  frozen=Path(r['target_dir'])/'app/.agents'
  self.assertFalse(frozen.is_symlink())
  self.assertEqual((frozen/'skills/wf-verify/SKILL.md').read_text(),rules.read_text())
  (frozen/'skills/wf-verify/SKILL.md').write_text('검토 사본만 변경')
  self.assertEqual(rules.read_text(),'共有 검토 기준')
 def test_direct_review_also_requires_internal_review(self):
  prepared=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'prepare','--request',str(self.req),'--output',str(self.req)],cwd=self.repo,text=True,capture_output=True)
  self.assertEqual(prepared.returncode,0,prepared.stderr+prepared.stdout)
  r=json.loads(prepared.stdout);pending=json.loads((Path(r['kept'])/'pending.json').read_text())
  self.assertIn('TV1',pending['required'])
  answer=json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'요청 결과만 확인'}]})
  finish=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'finish','--round',r['kept'],'--check','PASS'],cwd=self.repo,input=answer,text=True,capture_output=True)
  self.assertEqual(json.loads(finish.stdout)['completion'],'unverified')
 def test_pinned_review_rules_change_expires_evidence(self):
  rules=self.repo/'.agents/skills/wf-verify/SKILL.md';rules.parent.mkdir(parents=True)
  rules.write_text('현재 대상 검토 기준');(self.repo/'.agents/agent-workflow-kit.version').write_text('team-v1')
  self.record();self.runwork('check');rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  rules.write_text('바뀐 대상 검토 기준')
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('변경 전 기준으로 대조'))
  rc,result=self.runwork('review','--answer',str(answer));self.assertEqual(result['completion'],'unverified')
 def test_review_requirements_do_not_depend_on_markdown_table_syntax(self):
  self.data['requirements'][0]['expect']='이름 A | B를 그대로 보존\n두 번째 줄도 보존'
  self.record();(self.repo/'app.txt').write_text('after');self.runwork('check')
  rc,r=self.runwork('review');self.assertEqual(rc,0,r)
  pending=json.loads((Path(r['kept'])/'pending.json').read_text())
  self.assertEqual(pending['required'],['R1','TV1'])
  self.assertFalse(any(f['role']=='map' for f in pending['inputs']['files']))
  prompt=Path(r['prompt_file']).read_text()
  self.assertIn('이름 A | B를 그대로 보존',prompt)
  # 읽기용 지도를 고쳐도 현재 검토가 받은 원문·요구·검사 근거는 바뀌지 않는다.
  (self.work/'work.md').write_text('읽기용 지도 레이아웃 변경')
  answer=self.root/'answer.txt';answer.write_text(self.review_answer('원문 대조'))
  rc,r=self.runwork('review','--answer',str(answer));self.assertEqual(r['completion'],'verified',r)
 def test_reader_question_survives_plan_replacement(self):
  self.record()
  findings=self.root/'reader.json';findings.write_text(json.dumps([{'id':'Q1','expect':'기존 인쇄명 유지 또는 갱신','source':[1],'state':'미정'}]))
  rc,r=self.runwork('record','--findings',str(findings));self.assertEqual(rc,0,r)
  self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--plan',str(self.plan));self.assertNotEqual(rc,0,r)
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'waiting-user')
 def test_pending_choice_cannot_close_with_same_source(self):
  self.data['requirements'][0]['state']='미정';self.record()
  self.data['requirements'][0]['state']='확정';self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--plan',str(self.plan));self.assertNotEqual(rc,0,r)
  # 같은 원문을 다시 붙여 번호만 늘려도 답이 생긴 것은 아니다.
  rc,r=self.runwork('record','--request',str(self.req),'--plan',str(self.plan));self.assertNotEqual(rc,0,r)
 def test_reply_resolves_pending_without_second_approval(self):
  self.data['requirements'][0]['state']='미정';self.record()
  self.req.write_text('기존 인쇄 이름을 유지해 주세요.')
  self.data['requirements'][0].update(state='확정',source=[2],expect='기존 인쇄 이름 유지')
  self.data['review_required']=False
  rc,r=self.record();self.assertEqual(rc,0,r)
  rc,r=self.runwork('check');self.assertEqual(r['completion'],'verified',r)
 def test_findings_expire_old_check_and_review(self):
  self.record();self.runwork('check')
  findings=self.root/'reader.json';findings.write_text(json.dumps([{'id':'Q1','expect':'기존 인쇄명 처리','source':[1],'state':'미정'}]))
  rc,r=self.runwork('record','--findings',str(findings));self.assertEqual(rc,0,r)
  rc,r=self.runwork('review');self.assertEqual(r['completion'],'unverified',r)
 def test_identical_user_replies_to_different_questions_are_distinct(self):
  self.data['requirements'][0]['state']='미정';self.record()
  self.req.write_text('추천대로 해주세요')
  self.data['requirements'][0].update(state='확정',source=[2]);self.record()
  findings=self.root/'reader.json';findings.write_text(json.dumps([{'id':'Q1','expect':'다음 선택','source':[1],'state':'미정'}]))
  self.runwork('record','--findings',str(findings))
  self.data['requirements'].append({'id':'Q1','expect':'추천한 다음 결과','source':[3],'state':'확정'})
  self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--request',str(self.req),'--reply-to','Q1','--plan',str(self.plan))
  self.assertEqual(rc,0,r)
 def test_old_reply_cannot_resolve_reopened_question(self):
  self.data['requirements'][0]['state']='미정';self.record()
  self.req.write_text('추천대로 해주세요')
  self.data['requirements'][0].update(state='확정',source=[2]);self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--request',str(self.req),'--reply-to','R1','--plan',str(self.plan));self.assertEqual(rc,0,r)
  self.data['requirements'][0]['state']='미정';self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--plan',str(self.plan));self.assertEqual(rc,0,r)
  self.data['requirements'][0]['state']='확정';self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--plan',str(self.plan));self.assertNotEqual(rc,0,r)
  self.data['requirements'][0]['source']=[3];self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--request',str(self.req),'--reply-to','R1','--plan',str(self.plan));self.assertEqual(rc,0,r)
 def test_reused_review_for_other_plan_cannot_resolve_question(self):
  self.data['requirements'][0]['state']='미정';self.record()
  self.data['requirements'][0]['state']='확정';self.plan.write_text(json.dumps(self.data))
  rc,r=self.runwork('record','--plan',str(self.plan),'--resolution-review',str(self.root/'missing'))
  self.assertNotEqual(rc,0,r)
 def test_independent_contract_review_resolves_without_reasking_user(self):
  self.req.write_bytes('전환해도 최초 발급에서 300초 기한을 유지한다.\r\n'.encode())
  self.data['requirements'][0].update(state='미정',expect='전환 후 기한 유지 여부')
  self.record()
  self.data['requirements'][0].update(state='확정',expect='전환해도 최초 300초 기한 유지')
  self.plan.write_text(json.dumps(self.data))
  command=['python3',str(TOOL.with_name('verify.py')),'prepare',
    '--request',str(self.work/'sources/0001.txt'),'--output',str(self.plan),
    '--conditions',str(self.work/'resolution-context.md')]
  prepared=subprocess.run(command,cwd=self.repo,text=True,capture_output=True)
  self.assertEqual(prepared.returncode,0,prepared.stderr+prepared.stdout)
  kept=json.loads(prepared.stdout)['kept']
  answer=json.dumps({'verdict':'OK','conditions':[{'id':'R1','result':'충족','evidence':'원문이 최초 발급에서 300초 유지라고 명시'},{'id': 'TV1', 'result': '충족', 'evidence': '대상 기준·현재 버전·검사 대조'}]})
  finish=subprocess.run(['python3',str(TOOL.with_name('verify.py')),'finish','--round',kept,'--check','PASS'],
    cwd=self.repo,input=answer,text=True,capture_output=True)
  self.assertEqual(finish.returncode,0,finish.stdout+finish.stderr)
  self.req.write_text('앞선 답을 바꿉니다. 전환마다 기한을 새로 시작해 주세요.')
  rc,r=self.runwork('record','--request',str(self.req),'--plan',str(self.plan),'--resolution-review',kept)
  self.assertNotEqual(rc,0,r)
  rc,r=self.runwork('record','--plan',str(self.plan),'--resolution-review',kept)
  self.assertEqual(rc,0,r)
  rc,r=self.runwork('check');self.assertEqual(r['check'],'PASS',r)
if __name__=='__main__':unittest.main()
