import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service

with tempfile.TemporaryDirectory() as t:
    db = str(Path(t) / "probe.db")
    service.init(db)
    gate = threading.Barrier(2)

    def run(args):
        gate.wait(timeout=5)
        return service.confirm(db, *args)

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        outputs = list(pool.map(run, [("a", "alice", "morning"), ("b", "bob", "morning")]))
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT count(*) FROM enrollments WHERE workshop='morning'").fetchone()[0]
    print(json.dumps({"concurrent_results": outputs, "stored_count": count, "capacity": 1}, ensure_ascii=False))
    print(json.dumps({"retry": service.confirm(db, "a", "alice", "morning"), "lookup": service.status(db, "a", "alice")}, ensure_ascii=False))
