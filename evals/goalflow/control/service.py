import sqlite3
WORKSHOPS={"morning":{"name":"실습 A","time":"10:00","capacity":1},"evening":{"name":"실습 A","time":"18:00","capacity":1}}
MEMBERS={"alice","bob","carol"}
def init(db):
 with sqlite3.connect(db,timeout=10) as c:
  c.execute("CREATE TABLE IF NOT EXISTS enrollments (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS request_links (request_id TEXT PRIMARY KEY, enrollment_id INTEGER)")
def confirm(db,request_id,member,workshop):
 if member not in MEMBERS:return {"code":403,"error":"forbidden"}
 if workshop not in WORKSHOPS:return {"code":404,"error":"not_found"}
 with sqlite3.connect(db,timeout=10) as c:
  c.execute("BEGIN IMMEDIATE")
  existing=c.execute("SELECT id,member,workshop FROM enrollments WHERE request_id=? ORDER BY id DESC LIMIT 1",(request_id,)).fetchone() or c.execute("SELECT e.id,e.member,e.workshop FROM request_links l JOIN enrollments e ON e.id=l.enrollment_id WHERE l.request_id=?",(request_id,)).fetchone()
  if existing:
   if existing[1:]!=(member,workshop):return {"code":409,"error":"request_conflict"}
   return {"code":200,"confirmation":existing[0],"workshop":existing[2]}
  same=c.execute("SELECT id,workshop FROM enrollments WHERE member=? AND workshop=? ORDER BY id DESC LIMIT 1",(member,workshop)).fetchone()
  if same:
   c.execute("INSERT OR IGNORE INTO request_links VALUES (?,?)",(request_id,same[0]))
   return {"code":200,"confirmation":same[0],"workshop":same[1]}
  count=c.execute("SELECT count(*) FROM enrollments WHERE workshop=?",(workshop,)).fetchone()[0]
  if count>=WORKSHOPS[workshop]["capacity"]:return {"code":409,"error":"full"}
  cur=c.execute("INSERT INTO enrollments(request_id,member,workshop) VALUES (?,?,?)",(request_id,member,workshop))
  return {"code":200,"confirmation":cur.lastrowid,"workshop":workshop}
def status(db,request_id,member):
 if member not in MEMBERS:return {"code":403,"error":"forbidden"}
 with sqlite3.connect(db,timeout=10) as c:
  row=c.execute("SELECT id,workshop FROM enrollments WHERE request_id=? AND member=? ORDER BY id DESC LIMIT 1",(request_id,member)).fetchone() or c.execute("SELECT e.id,e.workshop FROM request_links l JOIN enrollments e ON e.id=l.enrollment_id WHERE l.request_id=? AND e.member=?",(request_id,member)).fetchone()
 if not row:return {"code":404,"error":"not_found"}
 return {"code":200,"confirmation":row[0],"workshop":row[1]}
