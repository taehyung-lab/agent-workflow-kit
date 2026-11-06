import sqlite3
import time

WORKSHOPS = {
    "morning": {"name": "실습 A", "time": "10:00", "capacity": 1},
    "evening": {"name": "실습 A", "time": "18:00", "capacity": 1},
}
MEMBERS = {"alice", "bob", "carol"}


def init(db):
    with sqlite3.connect(db, timeout=10) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS enrollments (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")


def confirm(db, request_id, member, workshop):
    if member not in MEMBERS:
        return {"code": 403, "error": "forbidden"}
    if workshop not in WORKSHOPS:
        return {"code": 404, "error": "not_found"}
    with sqlite3.connect(db, timeout=10) as conn:
        count = conn.execute("SELECT count(*) FROM enrollments WHERE workshop=?", (workshop,)).fetchone()[0]
        time.sleep(0.04)
        if count >= WORKSHOPS[workshop]["capacity"]:
            return {"code": 409, "error": "full"}
        cur = conn.execute("INSERT INTO enrollments(request_id,member,workshop) VALUES (?,?,?)", (request_id, member, workshop))
        return {"code": 200, "confirmation": cur.lastrowid, "workshop": workshop}


def status(db, request_id, member):
    if member not in MEMBERS:
        return {"code": 403, "error": "forbidden"}
    with sqlite3.connect(db, timeout=10) as conn:
        row = conn.execute("SELECT id,workshop FROM enrollments WHERE request_id=? AND member=? ORDER BY id DESC LIMIT 1", (request_id, member)).fetchone()
    if row is None:
        return {"code": 404, "error": "not_found"}
    return {"code": 200, "confirmation": row[0], "workshop": row[1]}
