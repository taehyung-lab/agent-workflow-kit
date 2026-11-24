import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RoomsTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp()) / "data.json"
        shutil.copy(ROOT / "data.json", self.data)

    def run_cli(self, *args):
        p = subprocess.run([sys.executable, str(ROOT / "rooms.py"), *args], capture_output=True, text=True,
                           env={**os.environ, "ROOMS_DATA": str(self.data)})
        return p.returncode, (json.loads(p.stdout) if p.returncode == 0 else p.stderr)

    def test_book_on_empty_day(self):
        code, r = self.run_cli("book", "가온", "나무", "2026-12-02", "10:00", "11:00")
        self.assertEqual(code, 0)
        self.assertEqual((r["status"], r["start"], r["end"]), ("confirmed", "10:00", "11:00"))

    def test_morning_slot_overlapping_old_format_booking_refused(self):
        # 9:30~10:30 확정 예약(시 앞에 0 이 없는 옛 표기)과 겹친다.
        code, _ = self.run_cli("book", "가온", "나무", "2026-12-01", "10:00", "11:00")
        self.assertNotEqual(code, 0)

    def test_hold_does_not_block_new_booking(self):
        code, r = self.run_cli("book", "가온", "나무", "2026-12-01", "15:30", "16:30")
        self.assertEqual((code, r["status"]), (0, "confirmed"))

    def test_hold_then_confirm(self):
        _, r = self.run_cli("book", "가온", "나무", "2026-12-02", "10:00", "11:00", "--hold")
        self.assertEqual(r["status"], "held")
        code, r = self.run_cli("confirm", str(r["id"]))
        self.assertEqual((code, r["status"]), (0, "confirmed"))

    def test_cancelled_booking_cannot_move(self):
        code, _ = self.run_cli("move", "4", "17:00", "18:00")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
