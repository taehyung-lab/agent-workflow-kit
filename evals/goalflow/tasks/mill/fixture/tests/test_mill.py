import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MillTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data.json"
        shutil.copy(ROOT / "data.json", self.data)

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(ROOT / "mill.py"), *map(str, args)],
                           env={**os.environ, "MILL_DATA": str(self.data)}, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_new(self):
        job = self.cli("new", "c1", "wheat", 3)
        self.assertEqual((job["status"], job["flour"], job["bran"]), ("draft", 0, 0))
        self.assertEqual(self.cli("show", job["id"])["grams"], 3)

    def test_restock(self):
        row = self.cli("restock", "old", 3)
        self.assertEqual(row["grams"], 12)

    def test_cancel(self):
        self.assertEqual(self.cli("cancel", 7)["status"], "cancelled")

if __name__ == "__main__":
    unittest.main()
