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
        prompt = Path(prepared["prompt_file"]).read_text()
        for index in (1, 2):
            self.assertIn(f"UR{index} 사용자 원문 {index}번", prompt)
        target = Path(prepared["kept"]) / "target"
        historical = subprocess.check_output(["git", "-C", target, "show", "refs/tags/v1.5:app.py"], text=True)
        self.assertEqual(historical, "SAVE = ['CREATE']\n")
        self.assertNotEqual(historical, (target / "app.py").read_text())
        git(target, "tag", "-f", "v1.5", "HEAD")
        finish = subprocess.run([sys.executable, str(VERIFY), "finish", "--round", prepared["kept"], "--check", "PASS"],
                                input="", cwd=self.root, capture_output=True, text=True)
        self.assertIn("refs/tags/v1.5", json.loads(finish.stdout)["reason"])

    def test_multiturn_review_identifies_missing_discovery_evidence(self):
        (self.root / "work/ask/reader.json").unlink()
        run = subprocess.run([sys.executable, str(VERIFY), "prepare", "--request", "work/req1.txt",
                              "--request", "work/req2.txt", "--base", self.base],
                             cwd=self.root, capture_output=True, text=True, check=True)
        prompt = Path(json.loads(run.stdout)["prompt_file"]).read_text()
        self.assertIn("전달된 표 없음", prompt)
        self.assertIn("고정된 비교 태그: 없음", prompt)
        self.assertIn("근거를 찾지 못하면 해당 동작은 미확인", prompt)

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
        git(self.root, "tag", "v1.5")
        cmd.extend(["--reference-tag", "v1.5"])
        subprocess.run(cmd, cwd=self.root, capture_output=True, check=True)
        _, prepared = self.prepare(row)
        target = Path(prepared["kept"]) / "target"
        self.assertEqual(subprocess.check_output(["git", "-C", target, "rev-parse", "v1.5"], text=True).strip(), self.base)
        git(self.root, "tag", "-d", "v1.5")
        _, missing = self.prepare(row)
        self.assertEqual(missing["state"], "unverified")
        git(self.root, "tag", "v1.5", self.base)
        message = self.root / "work/reply.txt"
        message.write_text("승인된 작업 전에 서버 소스 경로를 알려주세요.")
        (folder / "situations.json").write_text(json.dumps(reader))
        followed = cmd + ["--request", "work/req2.txt"]
        missing_reply = subprocess.run(followed, cwd=self.root, capture_output=True)
        self.assertNotEqual(missing_reply.returncode, 0)
        subprocess.run(followed + ["--sent", str(message)], cwd=self.root, capture_output=True, check=True)
        _, prepared = self.prepare(row)
        prompt = Path(prepared["prompt_file"]).read_text()
        self.assertIn(message.read_text(), prompt)
        self.assertIn("MQ1", prompt)
        message.write_text("알려주신 대로 구현했습니다.")
        _, changed_message = self.prepare(row)
        self.assertEqual(changed_message["state"], "unverified")
        message.write_text("승인된 작업 전에 서버 소스 경로를 알려주세요.")
        row["chosen"] = "등록과 조회"
        for name in ("reader", "situations"):
            (folder / (name + ".json")).write_text(json.dumps(reader))
        retry = subprocess.run(cmd, cwd=self.root, capture_output=True)
        self.assertNotEqual(retry.returncode, 0)
        _, result = self.prepare(row)
        self.assertEqual(result["state"], "unverified")
        self.assertIn("최초 독자 표", result["reason"])

    def handoff(self, rows, turns, *extra):
        first = self.reader["situations"][0]
        axes = {"states": [{"name": first["cell"][0], "where": "fixture"}],
                "commands": [{"name": first["cell"][1], "where": "save"}]}
        table = self.root / "work/ask/situations.json"
        table.write_text(json.dumps({"axes": axes, "situations": rows}))
        command = [sys.executable, str(VERIFY.parents[1] / "wf-ask/situations.py"), str(table), "--handoff"]
        for turn in range(1, turns + 1):
            command.extend(["--request", f"work/req{turn}.txt"])
            if turn < turns:
                message = self.root / f"work/sent{turn}.txt"
                message.touch()
                command.extend(["--sent", str(message)])
        return subprocess.run([*command, *extra], cwd=self.root, capture_output=True, text=True)

    def test_next_handoff_keeps_previously_settled_row(self):
        row = self.reader["situations"][0]
        row["observed"] = row["decided_by"]["observed"]
        first = self.handoff([row], 1)
        self.assertEqual(first.returncode, 0, first.stdout)
        missing = self.handoff([dict(row, id="Q11")], 2)
        self.assertEqual(missing.returncode, 3, missing.stdout)
        self.assertIn("Q10", missing.stdout)
        flipped = self.handoff([dict(row, chosen="등록과 조회")], 2)
        self.assertEqual(flipped.returncode, 3, flipped.stdout)
        self.assertFalse((self.root / "work/req1.txt.expectations/0002.json").exists())
        preserved = self.handoff([row, dict(row, id="Q11")], 2)
        self.assertEqual(preserved.returncode, 0, preserved.stdout)

    def test_new_handoff_uses_original_requests_and_unique_row_ids(self):
        row = self.reader["situations"][0]
        row["observed"] = row["decided_by"]["observed"]
        duplicate = self.handoff([row, row], 1)
        self.assertEqual(duplicate.returncode, 3, duplicate.stdout)
        first = self.handoff([row], 1)
        self.assertEqual(first.returncode, 0, first.stdout)
        with (self.root / "work/req1.txt").open("a") as stream:
            stream.write("이 문장은 뒤에서 보탰습니다.")
        changed = self.handoff([row], 2)
        self.assertEqual(changed.returncode, 3, changed.stdout)
        self.assertIn("원문", changed.stdout)

    def test_explicit_cancellation_keeps_original_row_in_next_handoff(self):
        row = self.reader["situations"][0]
        row["observed"] = row["decided_by"]["observed"]
        first = self.handoff([row], 1)
        self.assertEqual(first.returncode, 0, first.stdout)
        quote = "이름만 고쳐 저장하는 변경 요청은 취소해 주세요."
        (self.root / "work/req2.txt").write_text(quote)
        corrected = dict(row, chosen="변경 요청 취소", results=[*row["results"], "변경 요청 취소"],
                         source=[2], decided_by={"kind": "정정", "quote": quote})
        reader = self.root / "work/ask/correction-reader.json"
        reader.write_text(json.dumps({"axes": {}, "situations": [corrected]}))
        accepted = self.handoff([corrected], 2, "--reader", str(reader))
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        snapshot = json.loads((self.root / "work/req1.txt.expectations/0002.json").read_text())
        self.assertEqual(snapshot["expected"][0]["chosen"], "변경 요청 취소")

    def test_reader_agreement_cannot_turn_unsolicited_input_into_an_answer(self):
        row = self.reader["situations"][0]
        row["observed"] = row["decided_by"]["observed"]
        self.assertEqual(self.handoff([row], 1).returncode, 0)
        quote = "등록과 조회를 모두 저장해 주세요."
        (self.root / "work/req2.txt").write_text(quote)
        changed = dict(row, chosen="등록과 조회", ask="조회도 저장할까요?", source=[2],
                       decided_by={"kind": "답", "quote": quote})
        reader = self.root / "work/ask/second-reader.json"
        reader.write_text(json.dumps({"axes": {}, "situations": [changed]}))
        before_question = self.handoff([changed], 2, "--reader", str(reader))
        self.assertEqual(before_question.returncode, 3, before_question.stdout)
        (self.root / "work/sent1.txt").write_text(changed["ask"])
        after_question = self.handoff([changed], 2, "--reader", str(reader))
        self.assertEqual(after_question.returncode, 0, after_question.stdout)

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
