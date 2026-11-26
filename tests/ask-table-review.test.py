"""독립 검토 입력이 요구 확인의 독자 표(work/ask/reader.json)를 기준으로 삼는지 본다.

2026-11-26 접근권한 재현(f2·k1): 독자는 '이름만 고쳐 저장하면 등록만 보낸다(1.5)'로 정했는데, 구현자가 최종 표를
'조회도 보낸다'로 바꾸고 그 결과로 검사를 고쳤다. 검토자는 구현자가 고른 증거만 받아 통과시켰다.
→ 바뀐 줄은 검토자의 필수 조건이 되고, '진행해주세요' 같은 일반 승인으로 바뀐 줄은 검토 전에 돌려보낸다.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VERIFY = Path(__file__).resolve().parent.parent / ".agents/skills/wf-verify/verify.py"


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class AskTableReviewTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        git(self.root, "init", "-q")
        (self.root / "app.py").write_text("SAVE = ['CREATE']\n")
        git(self.root, "add", "-A"); git(self.root, "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-qm", "base")
        self.base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (self.root / "app.py").write_text("SAVE = ['CREATE', 'READ']\n")
        (self.root / "work/ask").mkdir(parents=True)
        (self.root / "work/req1.txt").write_text("3차인증카드 규칙도 1.5와 같게 넣어주세요.\n")
        (self.root / "work/req2.txt").write_text("진행해주세요\n")
        row = {"id": "Q10", "cell": ["등록만 저장된 권한", "저장"], "expect": "이름만 고쳐 저장", "results": ["등록만", "등록과 조회"],
               "state": "확정", "chosen": "등록만", "source": [1],
               "decided_by": {"kind": "기준", "quote": "3차인증카드 규칙도 1.5와 같게 넣어주세요.", "observed": {"where": "v1.5 submit", "value": "['create']"}}}
        self.reader = {"axes": {}, "situations": [row]}
        (self.root / "work/ask/reader.json").write_text(json.dumps(self.reader, ensure_ascii=False))

    def prepare(self, final_row):
        (self.root / "work/ask/situations.json").write_text(json.dumps({"axes": {}, "situations": [final_row]}, ensure_ascii=False))
        r = subprocess.run([sys.executable, str(VERIFY), "prepare", "--request", "work/req1.txt", "--request", "work/req2.txt", "--base", self.base],
                           cwd=self.root, capture_output=True, text=True)
        return r, json.loads(r.stdout.strip().splitlines()[-1])

    def test_generic_approval_flip_is_returned_before_review(self):
        flipped = dict(self.reader["situations"][0], chosen="등록과 조회", source=[2], decided_by={"kind": "답", "quote": "진행해주세요"})
        r, result = self.prepare(flipped)
        self.assertEqual(result.get("state"), "returned", r.stdout + r.stderr)
        self.assertIn("일반 승인", result.get("reason", ""))

    def test_reader_result_becomes_required_condition(self):
        r, result = self.prepare(self.reader["situations"][0])
        self.assertEqual(result.get("state"), "ready", r.stdout + r.stderr)
        self.assertIn("R1", result.get("required", []) or json.loads((Path(result["kept"]) / "pending.json").read_text())["required"])
        prompt = Path(result["prompt_file"]).read_text()
        self.assertIn("독자 결과 \"등록만\"", prompt)


if __name__ == "__main__":
    unittest.main()
