import copy,sys,unittest,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals/goalflow'))
from table import process_state
from conversation import product_snapshot, turn_writes, decision_contract
class DecisionTurns(unittest.TestCase):
 def data(self):
  return {'static_turns':2,'decision_turns':[2],'turns':[
   {'turn':1,'rc':0,'product_changes':['todo.py'],'turn_changes':['todo.py'],'product_touched':['todo.py']},
   {'turn':2,'rc':0,'product_changes':['todo.py'],'turn_changes':[],'product_touched':[]},
   {'turn':3,'rc':0,'product_changes':['todo.py'],'turn_changes':['todo.py'],'product_touched':['todo.py']},
   {'turn':4,'rc':0,'product_changes':['todo.py'],'turn_changes':[],'product_touched':[]}]}
 def test_allowed_change_not_retroactive_violation(self):self.assertEqual(process_state(self.data()),'ok')
 def test_edit_while_waiting(self):
  d=self.data();d['turns'][1]['turn_changes']=['todo.py'];self.assertEqual(process_state(d),'violation')
 def test_reverted_edit_while_waiting(self):
  d=self.data();d['turns'][1]['product_touched']=['todo.py'];self.assertEqual(process_state(d),'violation')
 def test_missing_turn_evidence_is_not_pass(self):
  d=self.data();del d['turns'][1]['turn_changes'];self.assertEqual(process_state(d),'review')
 def test_legacy_keeps_original_interpretation(self):
  d=self.data();del d['decision_turns'];self.assertEqual(process_state(d),'violation')
 def test_new_file_from_allowed_turn_is_observed_next_turn(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);subprocess.run(['git','init','-q'],cwd=p,check=True)
   (p/'new.py').write_text('first');before=product_snapshot(p)
   (p/'new.py').write_text('second');after=product_snapshot(p)
   self.assertNotEqual(before,after)
   self.assertEqual(turn_writes({str('new.py'):False},p,'unused',files=before),['new.py'])
   (p/'new.py').unlink();self.assertNotIn('new.py',product_snapshot(p))
 def test_task_owns_decision_timing(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);self.assertEqual(decision_contract(p,2),[1,2])
   (p/'turns.json').write_text('{"decision_turns":[2],"reason":"정정 뒤 정책 미정"}')
   self.assertEqual(decision_contract(p,2),[2])
   (p/'turns.json').write_text('{"decision_turns":[3],"reason":"bad"}')
   with self.assertRaises(ValueError):decision_contract(p,2)
if __name__=='__main__':unittest.main()
