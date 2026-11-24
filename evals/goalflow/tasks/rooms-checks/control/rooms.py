"""회의실 예약 명령줄 도구.

  python3 rooms.py book <회원> <회의실> <날짜> <시작> <끝> [--hold]   예약(--hold 는 임시 예약)
  python3 rooms.py confirm <예약번호>                                임시 예약을 확정으로
  python3 rooms.py move <예약번호> <시작> <끝>                       예약 시간 바꾸기
  python3 rooms.py cancel <예약번호>                                 예약 취소
  python3 rooms.py list <회의실> <날짜>                              그날 그 회의실의 예약(JSON)

자료 파일은 data.json 이다. 다른 파일을 쓰려면 환경 변수 ROOMS_DATA 에 경로를 준다.
"""
import json, os, sys
from pathlib import Path


def data_path():
    return Path(os.environ.get("ROOMS_DATA") or Path(__file__).with_name("data.json"))


def load():
    return json.loads(data_path().read_text(encoding="utf-8"))


def save(data):
    data_path().write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def find(data, booking_id):
    for booking in data["bookings"]:
        if booking["id"] == booking_id:
            return booking
    raise SystemExit(f"예약 {booking_id} 이 없습니다")


def minutes(text):
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def need_free(data, booking, start, end):
    """확정 예약끼리만 막는다. 끝과 시작이 같은 것은 겹침이 아니다. 자기 자신과 취소·임시 예약은 보지 않는다."""
    if minutes(start) >= minutes(end):
        raise SystemExit("끝 시각은 시작 시각보다 뒤여야 합니다")
    for other in data["bookings"]:
        if other["id"] != booking["id"] and other["status"] == "confirmed" and other["room"] == booking["room"] and other["date"] == booking["date"] \
                and minutes(start) < minutes(other["end"]) and minutes(other["start"]) < minutes(end):
            raise SystemExit(f"{other['start']}~{other['end']} 확정 예약과 시간이 겹칩니다")


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    command, args = argv[0], argv[1:]
    data = load()
    if command == "list":
        found = [b for b in data["bookings"] if b["room"] == args[0] and b["date"] == args[1]]
        print(json.dumps(found, ensure_ascii=False))
        return
    if command == "book":
        hold = "--hold" in args
        member, room, day, start, end = [a for a in args if a != "--hold"]
        booking = {"id": max([b["id"] for b in data["bookings"]], default=0) + 1, "member": member, "room": room,
                   "date": day, "start": start, "end": end, "status": "held" if hold else "confirmed"}
        if not hold:
            need_free(data, booking, start, end)
        data["bookings"].append(booking)
    else:
        booking = find(data, int(args[0]))
        if booking["status"] == "cancelled":
            raise SystemExit(f"예약 {booking['id']} 은 이미 취소됐습니다")
        if command == "confirm":
            if booking["status"] != "held":
                raise SystemExit(f"예약 {booking['id']} 은 임시 예약이 아닙니다")
            need_free(data, booking, booking["start"], booking["end"])
            booking["status"] = "confirmed"
        elif command == "move":
            if booking["status"] == "confirmed":
                need_free(data, booking, args[1], args[2])
            booking["start"], booking["end"] = args[1], args[2]
        elif command == "cancel":
            booking["status"] = "cancelled"
        else:
            raise SystemExit(__doc__)
    save(data)
    print(json.dumps(booking, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
