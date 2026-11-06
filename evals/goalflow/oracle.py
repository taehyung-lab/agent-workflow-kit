"""Evaluator-owned behavioral oracle. Never copied into the agent project."""
import argparse
import concurrent.futures
import importlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class ObservationUnavailable(Exception):
    pass


def evaluate(project, storage_query):
    project = Path(project).resolve()
    sys.path.insert(0, str(project))
    service = importlib.import_module("service")
    client = importlib.import_module("client")
    cases = []

    def check(name, callback):
        try:
            evidence = callback()
            cases.append({"name": name, "passed": True, "evidence": evidence})
        except ObservationUnavailable as error:
            cases.append({"name": name, "passed": None, "state": "unverified", "evidence": str(error)})
        except Exception as error:
            cases.append({"name": name, "passed": False, "evidence": str(error)})

    def demand(condition, evidence):
        if not condition:
            raise AssertionError(json.dumps(evidence, ensure_ascii=False))

    def records(db, requests):
        # This observer is chosen by the evaluator, independently of status().
        # A storage migration needs a matching observer, not a product failure.
        try:
            with sqlite3.connect(db) as conn:
                conn.execute("PRAGMA query_only=ON")
                rows = conn.execute(storage_query).fetchall()
            if any(len(row) != 4 for row in rows):
                raise ValueError("storage observer must return id, request_id, member, workshop")
            return [{"confirmation": row[0], "request": row[1], "member": row[2], "workshop": row[3]} for row in rows]
        except (sqlite3.Error, ValueError) as error:
            raise ObservationUnavailable("Independent storage observation unavailable; inspect the actual storage and supply --storage-query: " + str(error)) from error

    def display(result, slot, expected_confirmation):
        text = json.dumps(result, ensure_ascii=False)
        demand(type(expected_confirmation) is int and expected_confirmation > 0
               and type(result.get("confirmation")) is int and result["confirmation"] > 0, result)
        demand(result.get("confirmation") == expected_confirmation and slot in text, result)
        demand(any("가" <= ch <= "힣" for ch in str(result.get("message", ""))), result)

    def unknown(result):
        # Natural-language certainty is checked by independent semantic review below.
        # A keyword such as '실패' also occurs in a correct '성공/실패 여부를 모름' notice.
        demand(result.get("confirmation") is None and bool(str(result.get("message", "")).strip()), result)

    with tempfile.TemporaryDirectory() as t:
        def fresh(name):
            db = str(Path(t) / (name + ".db"))
            service.init(db)
            return db

        def normal():
            db = fresh("normal")
            outputs = [client.submit(db, "m", "alice", "morning"), client.submit(db, "e", "bob", "evening")]
            display(outputs[0], "10:00", service.status(db, "m", "alice")["confirmation"])
            display(outputs[1], "18:00", service.status(db, "e", "bob")["confirmation"])
            demand(len(records(db, [("m", "alice"), ("e", "bob")])) == 2 and outputs[0]["confirmation"] != outputs[1]["confirmation"], outputs)
            return outputs
        check("correct-session-and-confirmation-display", normal)

        def concurrent_capacity():
            observations = []
            for trial in range(12):
                db = fresh("race-" + str(trial))
                barrier = threading.Barrier(2)
                def call(args):
                    barrier.wait(timeout=5)
                    return service.confirm(db, *args)
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    results = list(pool.map(call, [("a", "alice", "morning"), ("b", "bob", "morning")]))
                rows = records(db, [("a", "alice"), ("b", "bob")])
                observations.append({"responses": results, "stored": rows})
                demand(len(rows) == 1 and sorted(x["code"] for x in results) == [200, 409], observations[-1])
            return {"trials": 12, "observations": observations}
        check("concurrent-last-seat-keeps-capacity", concurrent_capacity)

        def retry():
            db = fresh("retry")
            first = service.confirm(db, "same", "alice", "morning")
            second = service.confirm(db, "same", "alice", "morning")
            looked_up = service.status(db, "same", "alice")
            displayed = client.submit(db, "same", "alice", "morning")
            rows = records(db, [("same", "alice")])
            demand(first.get("code") == 200 and looked_up.get("confirmation") == first.get("confirmation") and len(rows) == 1, {"first": first, "retry": second, "lookup": looked_up, "stored": rows})
            display(displayed, "10:00", first["confirmation"])
            demand(displayed.get("confirmation") == first.get("confirmation"), displayed)
            return {"first": first, "retry": second, "displayed": displayed, "stored": rows}
        check("same-request-retry-keeps-original-confirmation", retry)

        def concurrent_retry():
            db = fresh("concurrent-retry")
            barrier = threading.Barrier(2)
            def call(_):
                barrier.wait(timeout=5)
                return service.confirm(db, "same", "alice", "morning")
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results = list(pool.map(call, range(2)))
            confirmed = [x for x in results if x.get("code") == 200]
            rows = records(db, [("same", "alice")])
            demand(confirmed and all(x.get("code") in (200, 409) for x in results) and len({x.get("confirmation") for x in confirmed}) == 1 and len(rows) == 1, {"responses": results, "stored": rows})
            return {"responses": results, "stored": rows}
        check("concurrent-retries-are-one-request", concurrent_retry)

        def offline():
            db = fresh("offline")
            result = client.submit(db, "off", "alice", "morning", online=False)
            unknown(result)
            demand(records(db, [("off", "alice")]) == [], result)
            online = client.submit(db, "off", "alice", "morning")
            display(online, "10:00", service.status(db, "off", "alice")["confirmation"])
            return {"offline": result, "online": online}
        check("offline-never-claims-confirmation", offline)

        def lost_response():
            db = fresh("lost")
            lost = client.submit(db, "lost", "alice", "evening", lose_response=True)
            unknown(lost)
            rows = records(db, [("lost", "alice")])
            demand(len(rows) == 1, rows)
            recovered = client.recover(db, "lost", "alice")
            display(recovered, "18:00", rows[0]["confirmation"])
            retry_result = client.submit(db, "lost", "alice", "evening")
            demand(recovered["confirmation"] == retry_result.get("confirmation") and service.status(db, "lost", "alice")["confirmation"] == rows[0]["confirmation"], {"recovered": recovered, "retry": retry_result})
            final_rows = records(db, [])
            demand(final_rows == rows, {"before_recovery": rows, "after_recovery_and_retry": final_rows})
            return {"lost": lost, "recovered": recovered, "retry": retry_result, "stored_after_recovery_and_retry": final_rows}
        check("lost-response-lookup-and-retry-do-not-duplicate", lost_response)

        def reused_key():
            db = fresh("reused-key")
            first = service.confirm(db, "key", "alice", "morning")
            wrong_session = service.confirm(db, "key", "alice", "evening")
            wrong_owner = service.confirm(db, "key", "bob", "evening")
            kept = service.status(db, "key", "alice")
            other = service.status(db, "key", "bob")
            demand(wrong_session.get("code", 0) >= 400 and wrong_owner.get("code", 0) >= 400 and "confirmation" not in wrong_owner and kept.get("confirmation") == first.get("confirmation") and kept.get("workshop") == "morning" and other.get("code") == 404, {"first": first, "other_session": wrong_session, "other_owner": wrong_owner, "kept": kept, "other_lookup": other})
            unrelated = service.confirm(db, "unrelated", "bob", "evening")
            demand(unrelated.get("code") == 200, unrelated)
            return {"first": first, "other_session": wrong_session, "other_owner": wrong_owner}
        check("request-id-cannot-change-owner-or-session", reused_key)

        def same_member_new_request():
            # answer.txt(사용자 결정): 이미 확정된 회원이 같은 회차를 다른 요청 ID 로 다시 신청하면 새 행 없이 기존 확정을 안내한다.
            db = fresh("same-member")
            first = service.confirm(db, "first", "alice", "morning")
            again = service.confirm(db, "again", "alice", "morning")
            shown = client.submit(db, "again2", "alice", "morning")
            other = service.confirm(db, "other", "alice", "evening")
            rows = records(db, [])
            demand(first.get("code") == 200 and again.get("code") == 200 and again.get("confirmation") == first.get("confirmation")
                   and other.get("code") == 200 and other.get("confirmation") != first.get("confirmation")
                   and [(row["member"], row["workshop"]) for row in rows] == [("alice", "morning"), ("alice", "evening")],
                   {"first": first, "again": again, "shown": shown, "other_session": other, "stored": rows})
            display(shown, "10:00", first.get("confirmation"))
            return {"first": first, "again": again, "shown": shown, "other_session": other, "stored": rows}
        check("same-member-new-request-returns-existing-confirmation", same_member_new_request)

        def linked_new_request():
            # answer.txt 3번(사용자 결정): 기존 확정을 안내한 새 요청 ID 는 그 확정에 연결해 저장한다(신청 행은 늘리지 않는다).
            db = fresh("linked")
            first = service.confirm(db, "orig", "alice", "morning")
            again = service.confirm(db, "fresh", "alice", "morning")
            lookup = client.recover(db, "fresh", "alice")
            hijack = service.confirm(db, "fresh", "bob", "evening")
            rows = records(db, [])
            demand(again.get("confirmation") == first.get("confirmation") and hijack.get("code") == 409 and not hijack.get("confirmation")
                   and [(row["member"], row["workshop"]) for row in rows] == [("alice", "morning")],
                   {"first": first, "again": again, "lookup": lookup, "hijack": hijack, "stored": rows})
            display(lookup, "10:00", first.get("confirmation"))
            return {"first": first, "again": again, "lookup": lookup, "hijack": hijack, "stored": rows}
        check("new-request-id-linked-to-existing-confirmation", linked_new_request)

        def permissions():
            db = fresh("permissions")
            denied = service.confirm(db, "guest", "guest", "morning")
            first = service.confirm(db, "member", "alice", "morning")
            other = service.status(db, "member", "bob")
            guest = service.status(db, "member", "guest")
            final_rows = records(db, [])
            demand(denied.get("code") == guest.get("code") == 403 and first.get("code") == 200 and other.get("code") == 404 and "confirmation" not in guest and "confirmation" not in other and len(final_rows) == 1 and final_rows[0]["confirmation"] == first.get("confirmation") and final_rows[0]["member"] == "alice", {"denied": denied, "other": other, "guest": guest, "first": first, "stored": final_rows})
            return {"member": first, "other": other, "guest": guest, "stored": final_rows}
        check("existing-member-access-boundary", permissions)

        def client_denials():
            db = fresh("client-denials")
            first = client.submit(db, "owner", "alice", "morning")
            display(first, "10:00", service.status(db, "owner", "alice")["confirmation"])
            before = records(db, [])
            full = client.submit(db, "other", "bob", "morning")
            forbidden = client.submit(db, "guest", "guest", "evening")
            wrong_session = client.submit(db, "owner", "alice", "evening")
            other_lookup = client.recover(db, "owner", "bob")
            guest_lookup = client.recover(db, "owner", "guest")
            results = {"full": full, "forbidden": forbidden, "wrong_session": wrong_session, "other_lookup": other_lookup, "guest_lookup": guest_lookup}
            demand(all(value.get("confirmation") is None for value in results.values()), results)
            after = records(db, [])
            demand(after == before, {"before_denials": before, "after_denials": after})
            return {"responses": results, "stored_before": before, "stored_after": after}
        check("client-denials-never-invent-confirmation", client_denials)

        def legacy_data():
            db = str(Path(t) / "legacy.db")
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE enrollments (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")
                conn.execute("INSERT INTO enrollments VALUES (41,'legacy','bob','evening')")
            service.init(db)
            service.init(db)
            existing = client.recover(db, "legacy", "bob")
            new = service.confirm(db, "new", "alice", "morning")
            demand(existing.get("confirmation") == 41 and new.get("code") == 200 and new.get("confirmation") != 41, {"existing": existing, "new": new})
            display(existing, "18:00", 41)
            return {"existing": existing, "new": new}
        check("existing-record-and-number-survive-update", legacy_data)

        def legacy_duplicates():
            db = str(Path(t) / "legacy-duplicates.db")
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE enrollments (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")
                conn.executemany("INSERT INTO enrollments VALUES (?,?,?,?)", [(41, "legacy", "bob", "morning"), (42, "legacy", "bob", "morning")])
            service.init(db)
            service.init(db)
            existing = client.recover(db, "legacy", "bob")
            display(existing, "10:00", 42)
            retry = service.confirm(db, "legacy", "bob", "morning")
            denied = service.confirm(db, "new", "alice", "morning")
            rows = records(db, [])
            demand(denied.get("code") == 409 and [(row["confirmation"], row["request"], row["member"], row["workshop"]) for row in rows] == [(41, "legacy", "bob", "morning"), (42, "legacy", "bob", "morning")], {"existing": existing, "retry": retry, "new": denied, "stored": rows})
            return {"existing": existing, "retry": retry, "new": denied, "stored": rows}
        check("preexisting-duplicates-preserved-without-new-writes", legacy_duplicates)

        def legacy_latest_row():
            # answer.txt(사용자 결정): 같은 요청 ID 의 옛 행이 여러 개면 가장 최근 행 하나가 결과다. 조회와 같은 회원·회차 재시도는
            # 그 행을 안내하고, 다른 회차 재시도는 충돌로 거절한다. 행은 바꾸지 않는다.
            db = str(Path(t) / "legacy-multi.db")
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE enrollments (id INTEGER PRIMARY KEY, request_id TEXT, member TEXT, workshop TEXT)")
                conn.executemany("INSERT INTO enrollments VALUES (?,?,?,?)", [(51, "multi", "bob", "morning"), (52, "multi", "bob", "evening")])
            service.init(db)
            existing = client.recover(db, "multi", "bob")
            display(existing, "18:00", 52)
            same = service.confirm(db, "multi", "bob", "evening")
            other = service.confirm(db, "multi", "bob", "morning")
            rows = records(db, [])
            demand(same.get("code") == 200 and same.get("confirmation") == 52 and other.get("code") == 409 and not other.get("confirmation")
                   and [(row["confirmation"], row["workshop"]) for row in rows] == [(51, "morning"), (52, "evening")],
                   {"lookup": existing, "same_retry": same, "other_retry": other, "stored": rows})
            return {"lookup": existing, "same_retry": same, "other_retry": other, "stored": rows}
        check("legacy-request-uses-latest-row-for-lookup-and-retry", legacy_latest_row)

        def cli_flow():
            db = str(Path(t) / "cli.db")
            def run(action):
                p = subprocess.run([sys.executable, "app.py", action, "--db", db, "--request", "cli", "--member", "carol", "--workshop", "evening"], cwd=project, capture_output=True, text=True, timeout=10)
                demand(p.returncode == 0, {"exit": p.returncode, "stderr": p.stderr})
                return json.loads(p.stdout)
            submitted, recovered = run("submit"), run("recover")
            authoritative = service.status(db, "cli", "carol")["confirmation"]
            display(submitted, "18:00", authoritative)
            display(recovered, "18:00", authoritative)
            demand(submitted["confirmation"] == recovered["confirmation"], {"submitted": submitted, "recovered": recovered})
            return {"submitted": submitted, "recovered": recovered}
        check("real-cli-confirms-and-recovers-same-session", cli_flow)
    return {"automated_valid": all(c["passed"] is True for c in cases), "observation_complete": all(c["passed"] is not None for c in cases),
            "storage_observer_sql": storage_query, "semantic_review_required": True,
            "semantic_review_scope": "Compare actual participant messages and displayed session with the authoritative results for every case, including offline, response loss, full, forbidden and request conflict. Machine PASS alone is not goal completion.",
            "passed": sum(c["passed"] is True for c in cases), "failed": sum(c["passed"] is False for c in cases),
            "unverified": sum(c["passed"] is None for c in cases), "total": len(cases), "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--storage-query", type=Path, default=Path(__file__).with_name("storage-observer.sql"))
    args = parser.parse_args()
    result = evaluate(args.project, args.storage_query.read_text())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["automated_valid"] else 2 if not result["observation_complete"] else 1)
