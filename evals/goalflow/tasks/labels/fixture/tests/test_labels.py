import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LabelsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data.json"
        shutil.copy(ROOT / "data.json", self.data)

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(ROOT / "labels.py"), *map(str, args)],
                           env={**os.environ, "LABELS_DATA": str(self.data)},
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_new_and_add(self):
        s = self.cli("new")
        self.assertEqual(s["status"], "draft")
        s = self.cli("add", s["id"], "A1", 2)
        self.assertEqual((s["used"], s["items"][0]["quantity"]), (2, 2))

    def test_remove_existing(self):
        s = self.cli("remove", 2, "A1", 1)
        self.assertEqual(s["used"], 1)

    def test_large(self):
        s = self.cli("new")
        self.assertEqual(self.cli("add", s["id"], "B1", 2)["used"], 4)


if __name__ == "__main__":
    unittest.main()
