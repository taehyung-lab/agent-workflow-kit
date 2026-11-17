"""로컬 가짜 CLI로 승인된 실행 횟수와 합산 시간을 확인한다."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))
import session
import budget


class EvaluationBudgetTest(unittest.TestCase):
    def setup_budget(self, root, runs=2, seconds=3):
        approval = root / 'approval.txt'; approval.write_text('승인된 원문 시험 자료')
        ledger = root / 'budget.json'
        budget.create(ledger, approval, runs, seconds)
        return ledger, approval

    def execute(self, root, statement='print("fake")', limit=1):
        return session._run([sys.executable, '-c', statement], root / 'call', limit)

    def test_run_limit_rejects_before_model_and_survives_process_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger, _ = self.setup_budget(root, runs=1)
            environment = {**os.environ, 'EVALS_BUDGET_FILE':str(ledger)}
            script = "import sys;sys.path.insert(0,sys.argv[1]);import session;session.reserve_run(sys.argv[2])"
            first = subprocess.run([sys.executable, '-c', script, str(ROOT/'evals'), str(root/'one')], env=environment, capture_output=True)
            second = subprocess.run([sys.executable, '-c', script, str(ROOT/'evals'), str(root/'two')], env=environment, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(len(json.loads(ledger.read_text())['runs']), 1)
            self.assertFalse((root/'model-started').exists())

    def test_spent_time_survives_next_process_and_no_time_means_no_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger, _ = self.setup_budget(root, seconds=0.25)
            with patch.dict(os.environ, {'EVALS_BUDGET_FILE':str(ledger)}):
                self.assertEqual(self.execute(root, 'import time;time.sleep(2)', limit=1), 124)
            marker = root / 'model-started'
            script = "import sys;sys.path.insert(0,sys.argv[1]);import session;raise SystemExit(session._run([sys.executable,'-c',sys.argv[3]],sys.argv[2],1))"
            run = subprocess.run([sys.executable,'-c',script,str(ROOT/'evals'),str(root/'second'),f'open({str(marker)!r},"w").write("started")'], env={**os.environ,'EVALS_BUDGET_FILE':str(ledger)}, capture_output=True)
            self.assertEqual(run.returncode, 125)
            self.assertFalse(marker.exists())
            self.assertIn('budget', (root/'second.err').read_text().lower())

    def test_interrupted_unsettled_reservation_is_not_reset_on_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            code="import os,sys;sys.path.insert(0,sys.argv[1]);import budget;budget.reserve_time(1,os.environ)"
            environment={**os.environ,'EVALS_BUDGET_FILE':str(ledger)}
            first=subprocess.run([sys.executable,'-c',code,str(ROOT/'evals')],env=environment,capture_output=True)
            self.assertEqual(first.returncode,0,first.stderr)
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}):
                self.assertEqual(self.execute(root),125)
            data=json.loads(ledger.read_text())
            self.assertEqual(len(data['calls']),1)
            self.assertEqual(next(iter(data['calls'].values()))['status'],'running')

    def test_changed_approval_fixed_limits_or_corruption_are_rejected(self):
        for kind in ('approval','limits','corrupt'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root=Path(d); ledger, approval=self.setup_budget(root)
                if kind=='approval': approval.write_text('changed')
                elif kind=='limits':
                    data=json.loads(ledger.read_text());data['policy']['max_runs']=99;ledger.write_text(json.dumps(data))
                else: ledger.write_text('{broken')
                with patch.dict(os.environ, {'EVALS_BUDGET_FILE':str(ledger)}):
                    self.assertEqual(self.execute(root, f'open({str(root/"started")!r},"w").write("x")'),125)
                self.assertFalse((root/'started').exists())

    def test_parallel_calls_cannot_allocate_same_remaining_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); ledger,_=self.setup_budget(root, seconds=0.6)
            environment={**os.environ,'EVALS_BUDGET_FILE':str(ledger)}
            code="import sys;sys.path.insert(0,sys.argv[1]);import session;raise SystemExit(session._run([sys.executable,'-c',sys.argv[3]],sys.argv[2],3))"
            first=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'evals'),str(root/'first'),'import time;time.sleep(2)'],env=environment)
            try:
                for _ in range(200):
                    if json.loads(ledger.read_text())['calls']: break
                    time.sleep(.005)
                marker=root/'parallel-started'
                second=subprocess.run([sys.executable,'-c',code,str(ROOT/'evals'),str(root/'second'),f'open({str(marker)!r},"w").write("x")'],env=environment)
                self.assertEqual(second.returncode,125)
                self.assertFalse(marker.exists())
                self.assertEqual(first.wait(timeout=3),124)
            finally:
                if first.poll() is None: first.kill(); first.wait()

    def test_timeout_cleans_owned_process_group_and_keeps_raw_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); child=root/'child.pid'; later=root/'child-survived'
            code=("import subprocess,sys,time;print('raw evidence',flush=True);"
                  + f"p=subprocess.Popen([sys.executable,'-c',\"import time;time.sleep(.8);open({str(later)!r},'w').write('alive')\"]);"
                  + f"open({str(child)!r},'w').write(str(p.pid));time.sleep(5)")
            self.assertEqual(self.execute(root,code,limit=.2),124)
            time.sleep(.8)
            self.assertFalse(later.exists())
            self.assertIn('raw evidence',(root/'call.jsonl').read_text())
            self.assertIn('timeout',(root/'call.err').read_text().lower())
            self.assertEqual(session.runtime_stop(root/'call.jsonl',124)['reason'],'timeout')
            import run
            project=root/'project';project.mkdir();work=root/'work';work.mkdir()
            word,reason=run.judge(root,project,work,root/'call',124,{},'original')
            self.assertEqual(word,'UNVERIFIED',reason)

    def test_nested_cli_time_is_included_once_and_resume_does_not_add_top_level_run(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=2)
            nested=("import sys;sys.path.insert(0,"+repr(str(ROOT/'evals'))+");import session;"
                    + "session._run([sys.executable,'-c','import time;time.sleep(.1)'],"+repr(str(root/'nested'))+",1)")
            with patch.dict(os.environ, {'EVALS_BUDGET_FILE':str(ledger)}):
                session.reserve_run(root/'top')
                self.assertEqual(self.execute(root,nested,limit=1),0)
                self.assertEqual(session._review([sys.executable,'-c','print("review")'],root,root/'review.jsonl'),0)
            data=json.loads(ledger.read_text())
            self.assertEqual(len(data['runs']),1)
            self.assertEqual(len(data['calls']),2)
            self.assertTrue(all(call['seconds']>0 for call in data['calls'].values()))

    def test_classifier_shares_time_and_keeps_its_original_evidence_contract(self):
        sys.path.insert(0,str(ROOT/'evals/goalflow'))
        import asked
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=2)
            fake=root/'claude'
            fake.write_text('#!'+sys.executable+'\n'+"print('{\"quotes\":{\"1\":\"정확한 코드를 쓸까요?\"}}')\n")
            fake.chmod(0o755)
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger),'PATH':str(root)+os.pathsep+os.environ['PATH']}):
                quotes=asked.surfaced('정확한 코드를 쓸까요?','1. 코드',record_dir=root/'classifier')
            self.assertEqual(quotes,{1:'정확한 코드를 쓸까요?'})
            data=json.loads(ledger.read_text())
            self.assertEqual(len(data['calls']),1)
            self.assertEqual(len(data['runs']),0)
            evidence=next((root/'classifier').iterdir())
            self.assertEqual(json.loads((evidence/'execution.json').read_text())['exit_code'],0)
            self.assertIn('quotes',(evidence/'stdout.txt').read_text())

    def test_review_still_removes_implementation_session_markers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.dict(os.environ,{'AWK_SESSION_ID':'parent','CLAUDE_CODE_SESSION_ID':'parent','CODEX_THREAD_ID':'parent'}):
                rc=session._review([sys.executable,'-c',"import os;print([os.environ.get(k) for k in ('AWK_SESSION_ID','CLAUDE_CODE_SESSION_ID','CODEX_THREAD_ID')])"],root,root/'review')
            self.assertEqual(rc,0)
            self.assertEqual((root/'review').read_text().strip(),'[None, None, None]')

    def test_runner_stop_is_unverified_without_product_changes_and_review_with_changes(self):
        import run
        for changed in (False,True):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as d:
                root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
                project=root/'project';project.mkdir()
                work=root/'work';(work/'before-last').mkdir(parents=True)
                (project/'product.txt').write_text('changed' if changed else 'original')
                (work/'before-last/product.txt').write_text('original')
                out=root/'blocked'
                with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}):
                    budget.reserve_time(1,os.environ)
                    rc=session._run([sys.executable,'-c',f'open({str(root/"started")!r},"w").write("model")'],out,1)
                word,reason=run.judge(root,project,work,out,rc,{},'original')
                self.assertEqual(word,'REVIEW' if changed else 'UNVERIFIED',reason)
                self.assertFalse((root/'started').exists())
                self.assertTrue(Path(str(out)+'.stop.json').exists())
                self.assertIn('budget',reason.lower())

    def test_normal_model_text_with_budget_words_is_not_runtime_stop(self):
        import run
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);project=root/'project';project.mkdir();work=root/'work';work.mkdir()
            (root/'check.py').write_text('print("PASS normal budget discussion")')
            out=root/'normal'
            rc=session._run([sys.executable,'-c','print("budget timeout 125 are user words")'],out,1)
            word,reason=run.judge(root,project,work,out,rc,{},'original')
            self.assertEqual(word,'PASS',reason)
            self.assertFalse(Path(str(out)+'.stop.json').exists())
            rc=session._run([sys.executable,'-c','import sys;print(\"budget timeout 125\");sys.exit(125)'],out,1)
            word,reason=run.judge(root,project,work,out,rc,{},'original')
            self.assertEqual(word,'FAIL',reason)
            self.assertFalse(Path(str(out)+'.stop.json').exists())

    def test_budget_code_is_owned_by_both_judge_fingerprints(self):
        import caseinfo
        self.assertIn('evals/budget.py',caseinfo.JUDGE_FILES)
        with tempfile.TemporaryDirectory() as d:
            import shutil
            copy=Path(d)/'evals'
            shutil.copytree(ROOT/'evals',copy,ignore=shutil.ignore_patterns('results','samples','__pycache__'))
            with patch.object(caseinfo,'EVALS',copy):
                before=caseinfo.goalflow_fingerprints(copy/'goalflow/tasks/labels')
                code=copy/'budget.py';code.write_text(code.read_text()+'\n# changed execution budget\n')
                after=caseinfo.goalflow_fingerprints(copy/'goalflow/tasks/labels')
            self.assertNotEqual(before['judge_version'],after['judge_version'])
            self.assertEqual(before['task_fingerprint'],after['task_fingerprint'])

    def test_goalflow_runtime_stop_preserves_raw_oracle_and_earlier_discovery(self):
        import contextlib, io, re, runpy
        from types import SimpleNamespace
        sys.path.insert(0,str(ROOT/'evals/goalflow'))
        import asked, pins, turnwatch
        for stop_at in (1,2):
            with self.subTest(stop_at=stop_at),tempfile.TemporaryDirectory() as d:
                root=Path(d);ledger,_=self.setup_budget(root,seconds=5)
                launches=[]
                class Harness:
                    session_id='fake'
                    def __init__(self,project,**kwargs): self.count=0
                    def start(self,prompt,prefix):
                        self.count+=1
                        if self.count==stop_at: budget.reserve_time(10000,os.environ)
                        launches.append(self.count)
                        command="import json;print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'정확한 코드와 이름 정책을 어떻게 할까요?'}}))"
                        rc=session._run([sys.executable,'-c',command],prefix,1)
                        return SimpleNamespace(exit_code=rc,log=str(prefix)+'.jsonl')
                    resume=start
                    def instruction_context(self): return {}
                    def close(self,*args,**kwargs): pass
                class Watch:
                    def __init__(self,*args): pass
                    def stop(self): return {}
                with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger),'CMP_TASK':'labels','MOCK':'asked'}), \
                     patch.object(sys,'argv',['compare.py','none','codex','1',str(root/'results')]), \
                     patch.dict(session.HARNESSES,{'codex':Harness}), \
                     patch.object(pins,'check',return_value=None), \
                     patch.object(pins,'cli_version',return_value='fake'), \
                     patch.object(turnwatch,'Watch',Watch), \
                     patch.object(asked,'surfaced',side_effect=lambda text,topics,**kwargs:{int(n):'정확한 코드와 이름 정책을 어떻게 할까요?' for n in re.findall(r'^(\d+)\.',topics,re.M)}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(ROOT/'evals/goalflow/compare.py'),run_name='__main__')
                summary=json.loads((root/'results/none-codex-1.json').read_text())
                meta=json.loads((root/'results/none-codex-1.meta.json').read_text())
                self.assertEqual(len(launches),stop_at)
                self.assertEqual(summary['turns'][-1]['rc'],125)
                self.assertEqual(summary['turns'][-1]['runtime_stop']['reason'],'budget')
                self.assertEqual(meta['goalflow']['final_behavior'],'UNVERIFIED')
                self.assertEqual(meta['goalflow']['discovery'],'unverified' if stop_at==1 else 'complete')
                self.assertEqual(meta['goalflow']['failed'],summary['failed'])
                self.assertEqual(meta['goalflow']['n_cases'],summary['n_cases'])
                self.assertTrue((root/'results/none-codex-1.oracle.json').exists())
                self.assertFalse(meta['check_passed'])
                table_run=subprocess.run([sys.executable,'-I',str(ROOT/'evals/goalflow/table.py'),str(root/'results')],capture_output=True,text=True)
                self.assertEqual(table_run.returncode,0,table_run.stderr)
                self.assertIn('통제된 한도 중단',table_run.stdout)
                if stop_at==2: self.assertTrue(summary['discovered'])
                from table import result_meta
                summary['decision_turns']=[1]
                summary['turns'][0]['turn_changes']=['unauthorized.py']
                summary['turns'][0]['product_touched']=['unauthorized.py']
                violated=result_meta(summary)
                self.assertFalse(violated['check_passed'])
                self.assertIn('FAIL 답 전에',violated['check_output'])
                self.assertEqual(violated['goalflow']['process'],'violation')

    def test_general_run_once_records_budget_stop_without_running_model(self):
        import contextlib, io, run
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            case=root/'case';case.mkdir()
            (case/'prompt.txt').write_text('budget은 원래 사용자 낱말입니다')
            (case/'check.py').write_text('raise RuntimeError("must not judge product")')
            marker=root/'model-started'
            class Harness:
                project_trusted=False
                def __init__(self,*args,**kwargs): pass
                def start(self,prompt,prefix):
                    rc=session._run([sys.executable,'-c',f'open({str(marker)!r},"w").write("model")'],prefix,1)
                    return session.Turn(rc,str(prefix)+'.jsonl',str(prefix)+'.err','')
                def close(self,**kwargs): pass
                def version(self): return 'fake-cli'
            def checkout(commit,kit): kit.mkdir();(kit/'AGENTS.md').write_text('kit')
            def build(project,kit,prepare,**kwargs):
                project.mkdir();prepare(project);(project/'AGENTS.md').write_text('kit')
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger),'EVALS_VERIFY':'0'}), \
                 patch.dict(session.HARNESSES,{'fake':Harness}), \
                 patch.object(session,'kit_checkout',side_effect=checkout), \
                 patch.object(session,'build_project',side_effect=build), \
                 patch.object(session,'snapshot',return_value='base'), \
                 patch.object(run.pins,'model',return_value='fake-model'), \
                 contextlib.redirect_stdout(io.StringIO()):
                budget.reserve_time(1,os.environ)
                run.run_once('case',case,'ref','abcdefg','fake',1,root,{'verifier_tool':''})
            meta=json.loads((root/'case-abcdefg-fake-1.meta.json').read_text())
            self.assertTrue(meta['check_unverified'],meta)
            self.assertFalse(meta['check_passed'])
            self.assertEqual(meta['observed']['runtime_stop']['reason'],'budget')
            self.assertIn('통제된 한도 중단',meta['check_output'])
            self.assertFalse(marker.exists())
            self.assertTrue((root/'case-abcdefg-fake-1.t1.stop.json').exists())

    def test_cli_waits_for_group_registration_before_nested_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            entered=root/'cli-entered'
            command=("import json,os,sys;sys.path.insert(0,"+repr(str(ROOT/'evals'))+");import budget;"
                     +f"open({str(entered)!r},'w').write('started');"
                     +"lease=budget.reserve_time(.5,os.environ);print(json.dumps({'nested':lease['nested']}))")
            attach=budget.attach
            observed=[]
            def delayed(lease,pid):
                time.sleep(.2)
                observed.append(entered.exists())
                attach(lease,pid)
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}),patch.object(budget,'attach',side_effect=delayed):
                rc=session._run([sys.executable,'-c',command],root/'nested-race',1)
            self.assertEqual(rc,0,(root/'nested-race.err').read_text())
            self.assertEqual(observed,[False])
            self.assertTrue(json.loads((root/'nested-race.jsonl').read_text())['nested'])
            calls=json.loads(ledger.read_text())['calls']
            self.assertEqual(len(calls),1)
            self.assertEqual(next(iter(calls.values()))['status'],'finished')

    def test_expired_group_registration_never_executes_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            entered=root/'cli-entered';attach=budget.attach
            def delayed(lease,pid): time.sleep(.2);attach(lease,pid)
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}),patch.object(budget,'attach',side_effect=delayed):
                rc=session._run([sys.executable,'-c',f'open({str(entered)!r},"w").write("started")'],root/'expired-registration',.05)
            self.assertEqual(rc,124)
            self.assertFalse(entered.exists())
            self.assertEqual(session.runtime_stop(root/'expired-registration.jsonl',124)['reason'],'timeout')

    def test_detached_group_cannot_reuse_parent_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            child=("import os,sys;sys.path.insert(0,"+repr(str(ROOT/'evals'))+");import budget;"
                   +"\ntry: budget.reserve_time(.5,os.environ)\nexcept budget.BudgetError: sys.exit(125)")
            parent="import subprocess,sys;raise SystemExit(subprocess.run([sys.executable,'-c',"+repr(child)+"],start_new_session=True).returncode)"
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}):
                rc=session._run([sys.executable,'-c',parent],root/'detached',1)
            self.assertEqual(rc,125)
            self.assertEqual(len(json.loads(ledger.read_text())['calls']),1)

    def test_failed_registration_does_not_release_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            entered=root/'cli-entered'
            def fail(lease,pid):
                time.sleep(.1)
                raise budget.BudgetError('budget: registration failed')
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger)}),patch.object(budget,'attach',side_effect=fail):
                with self.assertRaises(budget.BudgetError):
                    session._run([sys.executable,'-c',f'open({str(entered)!r},"w").write("started")'],root/'failed-registration',1)
            self.assertFalse(entered.exists())
            self.assertIn('registration failed',(root/'failed-registration.err').read_text())
            call=next(iter(json.loads(ledger.read_text())['calls'].values()))
            self.assertEqual(call['status'],'finished')
            self.assertEqual(call['exit_code'],125)

    def test_parent_exit_closes_gate_without_permitting_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=1)
            entered=root/'cli-entered'
            driver=("import os,sys;sys.path.insert(0,"+repr(str(ROOT/'evals'))+");import budget,session;"
                    +"budget.attach=lambda lease,pid:os._exit(42);"
                    +"session._run([sys.executable,'-c',"+repr(f'open({str(entered)!r},"w").write("started")')+"],"+repr(str(root/'parent-exit'))+",1)")
            run=subprocess.run([sys.executable,'-c',driver],env={**os.environ,'EVALS_BUDGET_FILE':str(ledger)},capture_output=True)
            self.assertEqual(run.returncode,42,run.stderr)
            time.sleep(.1)
            self.assertFalse(entered.exists())
            call=next(iter(json.loads(ledger.read_text())['calls'].values()))
            self.assertEqual(call['status'],'running')

    def test_gate_isolated_start_preserves_real_cli_environment_and_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ledger,_=self.setup_budget(root,seconds=2)
            modules=root/'modules';modules.mkdir()
            trap=root/'gate-imported-sitecustomize'
            (modules/'sitecustomize.py').write_text(f"open({str(trap)!r},'a').write('loaded\\n')\n")
            # 실제 CLI도 -I로 실행하여 gate가 불필요한 sitecustomize를 읽는지만 확인한다.
            script=root/'real_cli.py'
            script.write_text("import json,os,sys;print(json.dumps({'args':sys.argv[1:],'pythonpath':os.environ.get('PYTHONPATH'),'value':os.environ.get('GATE_TEST_VALUE')}))")
            args=['a b','원래 요청','--model','fixed-model']
            with patch.dict(os.environ,{'EVALS_BUDGET_FILE':str(ledger),'PYTHONPATH':str(modules),'GATE_TEST_VALUE':'original environment'}):
                rc=session._run([sys.executable,'-I',str(script),*args],root/'isolated-gate',1,cwd=root)
            self.assertEqual(rc,0,(root/'isolated-gate.err').read_text())
            self.assertFalse(trap.exists())
            output=json.loads((root/'isolated-gate.jsonl').read_text())
            self.assertEqual(output['args'],args)
            self.assertEqual(output['pythonpath'],str(modules))
            self.assertEqual(output['value'],'original environment')


if __name__=='__main__': unittest.main()
