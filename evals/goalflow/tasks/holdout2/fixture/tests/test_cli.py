"""기존 조회 기능 공개 검사."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PublicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / '장부.json'
        self.path.write_bytes((ROOT / 'data.json').read_bytes())
    def tearDown(self):
        self.temp.cleanup()
    def run_cli(self, *args):
        p = subprocess.run([sys.executable, str(ROOT / 'cli.py'), *args],
            env={**os.environ, 'SUSEON_DATA': str(self.path)}, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)
    def test_list(self):
        code, rows = self.run_cli('목록')
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 12)
    def test_read(self):
        before = self.path.read_bytes()
        code, row = self.run_cli('조회', '10')
        self.assertEqual(code, 0)
        self.assertEqual(row['이력'][1]['동작'], '재수선')
        self.assertEqual(self.path.read_bytes(), before)
    def test_unknown(self):
        code, result = self.run_cli('조회', '999')
        self.assertNotEqual(code, 0)
        self.assertIn('오류', result)
    def test_number_error(self):
        code, result = self.run_cli('조회', '하나')
        self.assertNotEqual(code, 0)
        self.assertEqual(result['오류'], '의류 번호는 정수로 입력해 주세요')
