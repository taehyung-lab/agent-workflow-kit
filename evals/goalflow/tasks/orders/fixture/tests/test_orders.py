import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OrdersTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.data = Path(self.dir) / "data.json"
        shutil.copy(ROOT / "data.json", self.data)

    def run_cli(self, *args):
        p = subprocess.run([sys.executable, str(ROOT / "orders.py"), *args], capture_output=True, text=True,
                           env={**os.environ, "ORDERS_DATA": str(self.data)})
        return p.returncode, (json.loads(p.stdout) if p.returncode == 0 else p.stderr)

    def test_new_order_total_is_goods_plus_shipping(self):
        code, r = self.run_cli("new", "가람서점", "공책:12000", "펜:3000")
        self.assertEqual(code, 0)
        self.assertEqual((r["goods"], r["shipping"], r["total"]), (15000, 3000, 18000))

    def test_paid_order_cannot_change(self):
        code, _ = self.run_cli("add", "1", "봉투:1000")
        self.assertNotEqual(code, 0)

    def test_remove_item(self):
        code, r = self.run_cli("remove", "2", "종이컵")
        self.assertEqual(code, 0)
        self.assertEqual(r["goods"], 42000)


if __name__ == "__main__":
    unittest.main()
