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

    def prepare(self, final_row, *extra):
        (self.root / "work/ask/situations.json").write_text(json.dumps({"axes": {}, "situations": [final_row]}, ensure_ascii=False))
        r = subprocess.run([sys.executable, str(VERIFY), "prepare", "--request", "work/req1.txt", "--request", "work/req2.txt", "--base", self.base, *extra],
                           cwd=self.root, capture_output=True, text=True)
        return r, json.loads(r.stdout.strip().splitlines()[-1])

    def test_reviewer_can_read_designated_version_and_detect_a_moved_tag(self):
        git(self.root, "tag", "v1.5")
        result, prepared = self.prepare(self.reader["situations"][0], "--reference-tag", "v1.5")
        self.assertEqual(result.returncode, 0, result.stdout)
        target = Path(prepared["kept"]) / "target"
        historical = subprocess.check_output(["git", "-C", target, "show", "refs/tags/v1.5:app.py"], text=True)
        self.assertEqual(historical, "SAVE = ['CREATE']\n")
        self.assertNotEqual(historical, (target / "app.py").read_text())
        git(target, "tag", "-f", "v1.5", "HEAD")
        finish = subprocess.run([sys.executable, str(VERIFY), "finish", "--round", prepared["kept"], "--check", "PASS"],
                                input="", cwd=self.root, capture_output=True, text=True)
        self.assertIn("refs/tags/v1.5", json.loads(finish.stdout)["reason"])

    def test_missing_designated_version_stops_review(self):
        _, prepared = self.prepare(self.reader["situations"][0], "--reference-tag", "v1.5")
        self.assertEqual(prepared["state"], "unverified")

    def test_unrelated_request_does_not_inherit_permissions(self):
        self.prepare(self.reader["situations"][0])
        (self.root / "work/ping.txt").write_text("화면 활동의 연장도 복구해 주세요.")
        run = subprocess.run([sys.executable, str(VERIFY), "prepare", "--request", "work/ping.txt", "--base", self.base],
                             cwd=self.root, capture_output=True, text=True, check=True)
        prompt = Path(json.loads(run.stdout)["prompt_file"]).read_text()
        self.assertNotIn('독자 결과 "등록만"', prompt)

    def test_missing_final_table_of_matching_request_blocks_review(self):
        run = subprocess.run([sys.executable, str(VERIFY), "prepare", "--request", "work/req1.txt", "--base", self.base],
                             cwd=self.root, capture_output=True, text=True)
        self.assertEqual(json.loads(run.stdout)["state"], "unverified")

    def test_handoff_keeps_initial_expectation_when_both_working_tables_change(self):
        reader = self.reader
        row = reader["situations"][0]
        row["observed"] = row["decided_by"]["observed"]
        reader["axes"] = {"states": [{"name": row["cell"][0], "where": "fixture"}],
                          "commands": [{"name": row["cell"][1], "where": "save"}]}
        folder = self.root / "work/ask"
        for name in ("reader", "situations"):
            (folder / (name + ".json")).write_text(json.dumps(reader))
        ask = VERIFY.parents[1] / "wf-ask/situations.py"
        cmd = [sys.executable, str(ask), "work/ask/situations.json", "--reader", "work/ask/reader.json",
               "--request", "work/req1.txt", "--handoff", "--base", self.base]
        subprocess.run(cmd, cwd=self.root, capture_output=True, check=True)
        row["chosen"] = "등록과 조회"
        for name in ("reader", "situations"):
            (folder / (name + ".json")).write_text(json.dumps(reader))
        retry = subprocess.run(cmd, cwd=self.root, capture_output=True)
        self.assertNotEqual(retry.returncode, 0)
        _, result = self.prepare(row)
        self.assertEqual(result["state"], "unverified")
        self.assertIn("최초 독자 표", result["reason"])

    def test_legacy_map_owns_its_quoted_request(self):
        self.prepare(self.reader["situations"][0])
        request = (self.root / "work/req1.txt").read_text().strip()
        (self.root / "map.md").write_text(f"## 기준\n요청 원문: {request}\n")
        run = subprocess.run([sys.executable, str(VERIFY), "prepare", "--map", "map.md", "--base", self.base],
                             cwd=self.root, capture_output=True, text=True)
        result = json.loads(run.stdout)
        if result["state"] != "ready":
            self.fail(result)
        self.assertIn('독자 결과 "등록만"', Path(result["prompt_file"]).read_text())

    def test_short_reference_quote_is_not_a_task_identifier(self):
        self.reader["situations"][0]["decided_by"]["quote"] = "1.5와 같게"
        (self.root / "work/ask/reader.json").write_text(json.dumps(self.reader))
        (self.root / "work/req1.txt").write_text("날짜 표시도 1.5와 같게 만들어 주세요.")
        _,result=self.prepare(self.reader["situations"][0])
        self.assertEqual(result["state"], "unverified")

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
