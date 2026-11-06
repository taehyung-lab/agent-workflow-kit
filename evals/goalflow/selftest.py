"""Model-free oracle regression controls and deliberate behavioral faults."""
import json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONTROL=ROOT/("control" if (ROOT/"control").is_dir() else "oracle-control")

def mutate(path,label):
 p=path/"service.py";s=p.read_text()
 c=path/"client.py";client=c.read_text()
 if label=="double-capacity":
  assert '  c.execute("BEGIN IMMEDIATE")' in s
  s=s.replace('import sqlite3','import sqlite3,time').replace('  c.execute("BEGIN IMMEDIATE")','').replace('  if count>=','  time.sleep(0.04)\n  if count>=')
 elif label=="hidden-duplicate":
  old='   return {"code":200,"confirmation":existing[0],"workshop":existing[2]}'
  assert old in s
  s=s.replace(old,'   c.execute("INSERT INTO enrollments(request_id,member,workshop) VALUES (?,?,?)",(request_id,member,workshop))\n'+old)
 elif label=="recovery-hidden-write":
  s=s.replace('ORDER BY id DESC','ORDER BY id ASC')
  old=' if r["code"]==200:return show(r)'
  # Restrict the inserted write to recover(), not submit().
  pos=client.index('def recover(')
  tail=client[pos:];assert old in tail
  tail=tail.replace(old,' if r["code"]==200:\n  import sqlite3\n  with sqlite3.connect(db) as conn:conn.execute("INSERT INTO enrollments(request_id,member,workshop) VALUES (?,?,?)",(request_id,member,r["workshop"]))\n  return show(r)')
  client=client[:pos]+tail
 elif label=="silent-forbidden-write":
  old=' if member not in MEMBERS:return {"code":403,"error":"forbidden"}'
  assert old in s
  s=s.replace(old,' if member not in MEMBERS:\n  with sqlite3.connect(db) as denied:denied.execute("INSERT INTO enrollments(request_id,member,workshop) VALUES (?,?,?)",(request_id,member,"evening"))\n  return {"code":403,"error":"forbidden"}',1)
 elif label=="lost-response":
  client=client.replace('if lose_response:return {"message":"결과 확인 필요"}','if lose_response:return show(r)')
 elif label=="missing-confirmation":
  s=s.replace('"confirmation":cur.lastrowid','"confirmation":None').replace('"confirmation":existing[0]','"confirmation":None').replace('"confirmation":row[0]','"confirmation":None')
 elif label=="fake-client-denial":
  client=client.replace('return {"message":"신청 실패","code":r["code"]}','return {"message":"신청 완료","confirmation":999,"time":"10:00"}')
 elif label=="permissions":
  s=s.replace('MEMBERS={"alice","bob","carol"}','MEMBERS={"alice","bob","carol","guest"}')
 elif label=="correct-uncertainty-wording":
  client=client.replace('연결 확인 필요','신청 성공 또는 실패 여부를 확인할 수 없습니다. 결과를 조회해 주세요.').replace('결과 확인 필요','신청 성공 또는 실패 여부를 확인할 수 없습니다. 결과를 조회해 주세요.')
 elif label=="storage-migration":
  s=s.replace('enrollments','registrations')
  old='  c.execute("CREATE TABLE IF NOT EXISTS registrations (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")'
  assert old in s
  s=s.replace(old,old+'\n  if c.execute("SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=\'enrollments\'").fetchone():\n   c.execute("INSERT INTO registrations SELECT * FROM enrollments old WHERE NOT EXISTS (SELECT 1 FROM registrations current WHERE current.id=old.id)")')
 elif label=="wrong-confirmation":
  client=client.replace('"confirmation":r["confirmation"]','"confirmation":999')
 elif label=="wrong-success-message":
  client=client.replace('"message":"신청 완료"','"message":"오류"')
 elif label=="legacy-retry-per-session":
  # answer.txt 위반: 재시도가 요청의 최근 행이 아니라 같은 회차의 옛 행을 찾는다(조회와 다른 회차·번호를 안내)
  old='existing=c.execute("SELECT id,member,workshop FROM enrollments WHERE request_id=? ORDER BY id DESC LIMIT 1",(request_id,)).fetchone()'
  assert old in s
  s=s.replace(old,'existing=c.execute("SELECT id,member,workshop FROM enrollments WHERE request_id=? AND workshop=? ORDER BY id DESC LIMIT 1",(request_id,workshop)).fetchone()')
 elif label=="same-member-new-row":
  # answer.txt 위반: 같은 회원·회차의 새 요청 ID 를 새 신청으로 처리한다
  old='  if same:\n'
  assert old in s
  s=s.replace(old,'  if False:\n')
 elif label=="unlinked-new-request":
  # answer.txt 3번 위반: 새 요청 ID 를 연결하지 않는다
  old='   c.execute("INSERT OR IGNORE INTO request_links VALUES (?,?)",(request_id,same[0]))\n'
  assert old in s
  s=s.replace(old,'')
 elif label!="valid-reference":raise ValueError(label)
 p.write_text(s);c.write_text(client)

def run():
 rows=[]
 with tempfile.TemporaryDirectory(prefix="goal-oracle-") as temp:
  for label in ["valid-reference","correct-uncertainty-wording","double-capacity","hidden-duplicate","recovery-hidden-write","silent-forbidden-write","lost-response","missing-confirmation","fake-client-denial","permissions","wrong-confirmation","wrong-success-message","storage-migration","legacy-retry-per-session","same-member-new-row","unlinked-new-request","original-fixture"]:
   project=Path(temp)/label;shutil.copytree(ROOT/"fixture",project,ignore=shutil.ignore_patterns("__pycache__"))
   if label!="original-fixture":
    for name in ["service.py","client.py"]:shutil.copy2(CONTROL/name,project/name)
    mutate(project,label)
   command=[sys.executable,"-I",str(ROOT/"oracle.py"),str(project)]
   if label=="storage-migration":command += ["--storage-query",str(ROOT/"storage-observer-migration.sql")]
   result=subprocess.run(command,capture_output=True,text=True,timeout=45)
   if not result.stdout.strip():raise AssertionError((label,result.stderr))
   d=json.loads(result.stdout)
   expected=label in ["valid-reference","correct-uncertainty-wording","storage-migration","wrong-success-message"]
   assert d["automated_valid"]==expected,(label,d)
   assert d["semantic_review_required"] is True,label
   if label=="recovery-hidden-write":assert any(x["name"]=="lost-response-lookup-and-retry-do-not-duplicate" and x["passed"] is False for x in d["cases"]),d
   if label=="unlinked-new-request":assert "new-request-id-linked-to-existing-confirmation" in [x["name"] for x in d["cases"] if x["passed"] is False],d
   if label=="same-member-new-row":assert "same-member-new-request-returns-existing-confirmation" in [x["name"] for x in d["cases"] if x["passed"] is False],d
   if label=="legacy-retry-per-session":assert "legacy-request-uses-latest-row-for-lookup-and-retry" in [x["name"] for x in d["cases"] if x["passed"] is False],d
   if label=="silent-forbidden-write":assert any(x["name"]=="existing-member-access-boundary" and x["passed"] is False for x in d["cases"]),d
   rows.append({"case":label,"automated_valid":d["automated_valid"],"passed":d["passed"],"total":d["total"],"failed":[x["name"] for x in d["cases"] if x["passed"] is False],"semantic_review_required":True,"semantic_rejection_expected":label=="wrong-success-message"})
   if label=="storage-migration":
    unavailable=subprocess.run(command[:-2],capture_output=True,text=True,timeout=45);u=json.loads(unavailable.stdout)
    assert unavailable.returncode==2 and u["unverified"]>0 and u["failed"]==0,u
    rows.append({"case":"migration-observer-unavailable","unverified":u["unverified"],"failed":u["failed"]})
 return rows
if __name__=="__main__":
 rows=run();print(json.dumps(rows,ensure_ascii=False,indent=2));print(f"{len(rows)} oracle controls passed")
