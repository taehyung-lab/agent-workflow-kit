"""회의실 예약 과제의 외부 판정: 끝난 프로젝트의 공개 명령(rooms.py)만 실행해 받아들임·거절과 저장된 예약을 본다.

  python3 -I evals/goalflow/tasks/rooms/oracle.py <프로젝트>

given 은 요청과 docs/operations.md 가 글자 그대로 정한 것, decision 은 answer.txt 의 사용자 답이 정한 것이다.
거절은 0 이 아닌 종료 코드와 "자료가 바뀌지 않음"으로 본다(안내 문구는 보지 않는다).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskcheck import Judge

j = Judge(sys.argv[1], "rooms.py", "ROOMS_DATA")
DAY = "2026-12-01"
KEYS = ("id", "member", "room", "date", "start", "end", "status")


def day(room, date=DAY):
    return {b["id"]: b for b in j.ok("list", room, date)}


def refused_unchanged(room, *args):
    before = day(room)
    j.refused(*args)
    after = day(room)
    assert {k: [v[x] for x in KEYS] for k, v in after.items()} == {k: [v[x] for x in KEYS] for k, v in before.items()}, {"args": args, "want": "거절한 요청은 자료를 바꾸지 않는다"}


def overlap_confirmed_refused():
    refused_unchanged("나무", "book", "가온", "나무", DAY, "13:30", "14:30")


def inside_and_around_refused():
    refused_unchanged("나무", "book", "가온", "나무", DAY, "13:15", "13:45")
    refused_unchanged("나무", "book", "가온", "나무", DAY, "12:00", "15:00")


def touching_allowed():
    assert j.ok("book", "가온", "나무", DAY, "14:00", "14:30")["status"] == "confirmed"
    assert j.ok("book", "가온", "나무", DAY, "12:00", "13:00")["status"] == "confirmed"


def other_room_or_day_allowed():
    j.ok("book", "가온", "바다", DAY, "13:00", "14:00")
    j.ok("book", "가온", "나무", "2026-12-02", "13:00", "14:00")


def cancelled_does_not_block():
    j.ok("book", "가온", "나무", DAY, "16:30", "17:30")


def old_time_format_compared_by_clock():
    refused_unchanged("나무", "book", "가온", "나무", DAY, "10:00", "11:00")
    j.ok("book", "가온", "나무", DAY, "8:00", "9:30")


def move_within_own_slot_allowed():
    r = j.ok("move", 2, "13:30", "14:30")
    assert (r["start"], r["end"]) == ("13:30", "14:30"), r


def move_into_confirmed_refused():
    refused_unchanged("나무", "move", 2, "10:00", "11:00")


def list_keys_kept():
    b = day("나무")
    assert sorted(b) == [1, 2, 3, 4] and all(k in b[1] for k in KEYS), b
    assert [b[1][k] for k in KEYS] == [1, "민서", "나무", DAY, "9:30", "10:30", "confirmed"], b[1]
    assert [b[4]["status"], b[3]["status"]] == ["cancelled", "held"], b


def hold_does_not_block_new():
    assert j.ok("book", "가온", "나무", DAY, "15:30", "16:30")["status"] == "confirmed"


def hold_over_confirmed_allowed():
    assert j.ok("book", "가온", "나무", DAY, "13:30", "14:30", "--hold")["status"] == "held"


def confirm_hold_over_confirmed_refused():
    r = j.ok("book", "가온", "나무", DAY, "13:30", "14:30", "--hold")
    refused_unchanged("나무", "confirm", r["id"])
    assert j.ok("confirm", 3)["status"] == "confirmed"


def existing_overlap_left_alone():
    b = day("바다")
    assert [(b[i]["start"], b[i]["end"], b[i]["status"]) for i in (5, 6)] == [("10:00", "12:00", "confirmed"), ("11:00", "12:30", "confirmed")], b
    j.ok("book", "가온", "바다", DAY, "12:30", "13:00")
    refused_unchanged("바다", "move", 6, "11:30", "12:30")
    assert j.ok("move", 6, "12:00", "12:30")["start"] == "12:00"


j.check("overlap-with-confirmed-refused", "given", overlap_confirmed_refused)
j.check("contained-and-containing-refused", "given", inside_and_around_refused)
j.check("touching-times-allowed", "given", touching_allowed)
j.check("other-room-or-day-allowed", "given", other_room_or_day_allowed)
j.check("cancelled-booking-does-not-block", "given", cancelled_does_not_block)
j.check("old-time-format-compared-by-clock", "given", old_time_format_compared_by_clock)
j.check("move-within-own-slot-allowed", "given", move_within_own_slot_allowed)
j.check("move-into-confirmed-refused", "given", move_into_confirmed_refused)
j.check("list-keys-and-existing-bookings-kept", "given", list_keys_kept)
j.check("public-tests-pass", "given", j.public_tests)
j.check("hold-does-not-block-new-booking", "decision", hold_does_not_block_new)
j.check("hold-over-confirmed-allowed", "decision", hold_over_confirmed_allowed)
j.check("confirming-hold-over-confirmed-refused", "decision", confirm_hold_over_confirmed_refused)
j.check("existing-overlap-left-alone-but-moves-checked", "decision", existing_overlap_left_alone)
j.finish()
