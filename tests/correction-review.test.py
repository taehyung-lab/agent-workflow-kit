"""후속 사용자 정정이 실제 검토 입력과 필수 판정까지 전달되는지 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFY = Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify"
SCENE = "등록 권한만 있는 카드를 이름만 바꿔 저장"
BEFORE = "등록만 전송"
AFTER = "등록과 조회 전송"
CORRECTION = "등록 권한만 있는 카드를 이름만 바꿔 저장해도 등록과 조회를 함께 보내 주세요."


class CorrectionReview(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work = self.root / "work/card"
        self.file = self.root / "request"
        self.file.write_text(SCENE + "하면 등록만 보내 주세요.")
        self.row = dict(id="Q1", expect=SCENE, state="확정", chosen=BEFORE, source=[1],
                        decided_by={"kind": "요청", "quote": self.file.read_text()})
        self.git("init", "-q")
        self.git("-c", "user.name=test", "-c", "user.email=t@test", "commit", "--allow-empty", "-qm", "base")
        self.plan = {"targets": [{"name": "card", "path": str(self.root), "base": "HEAD"}],
                     "requirements": [self.row], "checks": [{"id": "card", "target": "card",
                     "requirements": ["Q1"], "argv": [sys.executable, "-c", "print('card')"]}]}

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def cli(self, tool, *args):
        result = subprocess.run([sys.executable, VERIFY / tool, *args], cwd=self.root, capture_output=True, text=True)
        return json.loads(result.stdout)

    def record(self):
        path = self.root / "plan.json"
        path.write_text(json.dumps(self.plan))
        return self.cli("work.py", "record", self.work, "--request", self.file, "--plan", path)

    def correct(self, quote=CORRECTION):
        self.file.write_text(quote)
        self.row.update(chosen=AFTER, source=[2], decided_by={"kind": "정정", "quote": quote})

    def test_representative_record_requires_a_verdict_on_unprompted_correction(self):
        self.assertEqual(self.record()["state"], "recorded")
        self.correct()
        second = self.record()
        self.assertEqual(second.get("state"), "recorded", second)
        self.assertEqual(self.cli("work.py", "check", self.work)["completion"], "review-missing")
        prepared = self.cli("work.py", "review", self.work)
        self.assertEqual(prepared["state"], "ready", prepared)
        self.assert_correction_condition(prepared)

    def test_plan_with_only_expect_shows_both_result_sentences(self):
        self.row.pop("chosen")
        self.row["expect"] = SCENE + " 시 " + BEFORE
        self.record()
        self.correct()
        self.row.pop("chosen")
        self.row["expect"] = SCENE + " 시 " + AFTER
        self.record()
        self.cli("work.py", "check", self.work)
        self.assert_correction_condition(self.cli("work.py", "review", self.work))

    def test_forged_quote_or_general_approval_cannot_change_the_plan(self):
        self.record()
        self.correct()
        self.file.write_text("진행해주세요")
        result = self.record()
        self.assertNotEqual(result.get("state"), "recorded", result)
        self.row["decided_by"]["quote"] = self.file.read_text()
        result = self.record()
        self.assertNotEqual(result.get("state"), "recorded", result)
        self.correct()
        self.plan["review_required"] = False
        result = self.record()
        self.assertIn("독립 검토", result["reason"])

    def test_separate_handoff_paths_compare_first_result_with_later_correction(self):
        folder = self.root / "work/ask"
        folder.mkdir(parents=True)
        self.row.update(cell=["등록 권한", "이름 저장"], results=[BEFORE, AFTER])
        axes = {"states": [{"name": "등록 권한", "where": "card"}],
                "commands": [{"name": "이름 저장", "where": "save"}]}
        first = folder / "request1.txt"
        first.write_bytes(self.file.read_bytes())
        sent = folder / "sent.txt"
        sent.write_text("카드 규칙을 확인했습니다.")
        args = ["--request", str(first)]
        for index in (1, 2):
            if index == 2:
                self.correct()
                args.extend(["--request", str(self.file), "--sent", str(sent)])
            table = json.dumps({"axes": axes, "situations": [self.row]})
            reader = folder / f"reader-{index}.json"
            final = folder / f"final-{index}.json"
            for path in (reader, final):
                path.write_text(table)
            cmd = [sys.executable, VERIFY.parent / "wf-ask/situations.py", final,
                   "--reader", reader, "--handoff", "--base", "HEAD", *args]
            p = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        prepared = self.cli("verify.py", "prepare", "--request", first, "--request", self.file,
                            "--output", self.file)
        self.assertEqual(prepared["state"], "ready", prepared)
        self.assert_correction_condition(prepared)

        manual_map = self.root / "card.md"
        for criteria in ("요청 원문: " + first.read_text(), "등록 권한을 확인한다."):
            manual_map.write_text("## 기준\n" + criteria + "\n")
            mapped = self.cli("verify.py", "prepare", "--map", manual_map, "--request", first,
                              "--request", self.file, "--output", self.file)
            self.assertEqual(mapped["state"], "ready", mapped)
            self.assert_correction_condition(mapped)

    def assert_correction_condition(self, prepared):
        prompt = Path(prepared["prompt_file"]).read_text()
        pending = json.loads((Path(prepared["kept"]) / "pending.json").read_text())
        condition = next((line for line in prompt.splitlines() if "후속 정정" in line
                          and line.split(" ")[0] in pending["required"] and SCENE in line), "")
        for part in (BEFORE, AFTER, CORRECTION, "2번", "미충족"):
            self.assertIn(part, condition)


if __name__ == "__main__":
    unittest.main()
