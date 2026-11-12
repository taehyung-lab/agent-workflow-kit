"""실행 결과의 저장·재판정 계약을 공개 명령으로 확인한다(모델 없음)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ResultTest(unittest.TestCase):
    def make_project(self, root):
        project = root / "sample.files"
        (project / "scripts").mkdir(parents=True)
        (project / "scripts/calc.py").write_text("print(5)\n")
        (root / "sample.jsonl").write_text("")

    def initial(self, root, review=None, observed=None, **overrides):
        run = {"case": "weight-disposable", "kit_ref": "fixture", "kit_commit": "fixture", "harness": "fake", "run": 1,
               "harness_version": "", "exit_code": 0, "seconds": 1, "agents_md_bytes": 1, "check": "PASS", "check_output": "PASS fixture",
               "input": "original", "user_turns": 1, "planned_turns": 1, "observed": observed or {}, "verifier": "ok" if review is not None else "off",
               "verify_reason": "", "verify_rounds": 1, "verifier_exit_code": None, "review": review or {},
               "baseline_changed": False, "verifier_tool": "", "review_required": False, "lang": "", "judge_version": "",
               "codex_project_trusted": False, "claude_project_settings": "", "global_instructions": {}}
        run.update(overrides)
        path = root / "sample.meta.json"
        result = subprocess.run([sys.executable, "-I", str(HERE / "result.py"), str(path)],
                                input=json.dumps(run), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(path.read_text())

    def rejudge(self, root):
        result = subprocess.run([sys.executable, "-I", str(HERE / "rejudge.py"), str(root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((root / "sample.meta.json").read_text())

    def test_current_result_preserves_open_decisions_through_rejudge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.make_project(root)
            before = self.initial(root, {"open_decisions": ["Q2"], "unconfirmed": []})
            self.assertEqual(before["completion"], "waiting-user")
            after = self.rejudge(root)
            self.assertEqual(after["completion"], "waiting-user")
            self.assertEqual(after["completion_inputs"]["open_decisions"], ["Q2"])
            self.assertEqual(after["rejudge_history"][-1]["completion_inputs"], before["completion_inputs"])

    def test_observed_review_preserves_facts_through_rejudge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.make_project(root)
            log = root / "sample.jsonl"
            review = {"state": "ok", "completion": "unverified", "open_decisions": [], "unconfirmed": ["F1"]}
            log.write_text(json.dumps({"type": "item.completed", "item": {
                "type": "command_execution", "command": "python3 .agents/skills/wf-verify/verify.py finish --round work/review",
                "aggregated_output": json.dumps(review), "exit_code": 0, "status": "completed"}}))
            output = subprocess.run([sys.executable, "-I", str(HERE / "observe.py"), str(log)],
                                    capture_output=True, text=True, check=True)
            before = self.initial(root, observed=json.loads(output.stdout))
            self.assertEqual(before["completion_inputs"]["unconfirmed"], ["F1"])
            self.assertEqual(before["completion"], "unverified")
            after = self.rejudge(root)
            self.assertEqual(after["completion"], "unverified")

    def test_known_results_keep_their_reason_after_rejudge(self):
        cases = [
            (None, {}, "verified"),
            (None, {"review_required": True}, "review-missing"),
            ({"open_decisions": [], "unconfirmed": []}, {}, "verified"),
            ({"open_decisions": [], "unconfirmed": ["F1"]}, {}, "unverified"),
            ({"open_decisions": ["Q1"], "unconfirmed": []}, {}, "waiting-user"),
            ({"open_decisions": [], "unconfirmed": []}, {"verifier": "returned"}, "returned"),
            ({"open_decisions": [], "unconfirmed": []}, {"verifier": "incomplete"}, "incomplete"),
        ]
        for review, overrides, expected in cases:
            with self.subTest(expected=expected, overrides=overrides), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.make_project(root)
                before = self.initial(root, review, **overrides)
                transcript = (root / "sample.jsonl").read_bytes()
                product = (root / "sample.files/scripts/calc.py").read_bytes()
                self.assertEqual(before["completion"], expected)
                self.assertFalse(before["completion_inputs_missing"])
                after = self.rejudge(root)
                self.assertEqual(after["completion"], expected)
                self.assertEqual(after["completion_inputs"], before["completion_inputs"])
                self.assertEqual((root / "sample.jsonl").read_bytes(), transcript)
                self.assertEqual((root / "sample.files/scripts/calc.py").read_bytes(), product)

    def test_failed_check_is_visible_even_while_waiting(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.make_project(root)
            self.initial(root, {"open_decisions": ["Q2"], "unconfirmed": []})
            (root / "sample.files/scripts/calc.py").unlink()
            after = self.rejudge(root)
            self.assertEqual(after["completion"], "check-failed")
            self.assertEqual(after["rejudge_history"][-1]["completion"], "waiting-user")
            (root / "sample.files/scripts/calc.py").write_text("print(5)\n")
            restored = self.rejudge(root)
            self.assertEqual(restored["completion"], "waiting-user")
            self.assertEqual([h["completion"] for h in restored["rejudge_history"]],
                             ["waiting-user", "check-failed"])

    def test_missing_historical_inputs_never_become_known_on_rejudge(self):
        for previous in ("verified", "unverified", "check-failed"):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.make_project(root)
                before = self.initial(root, {"open_decisions": [], "unconfirmed": []})
                before.pop("completion_inputs")
                before.pop("completion_inputs_missing")
                before["completion"] = previous
                (root / "sample.meta.json").write_text(json.dumps(before))
                after = self.rejudge(root)
                self.assertEqual(after["completion"], "unverified")
                self.assertTrue(after["completion_inputs_missing"])
                again = self.rejudge(root)
                self.assertEqual(again["completion"], "unverified")
                self.assertIsNone(again["rejudge_history"][-1]["completion_inputs"])

    def test_incomplete_review_output_is_not_an_empty_decision_list(self):
        for review in ({}, {"open_decisions": []}, {"open_decisions": "Q2", "unconfirmed": []}):
            with self.subTest(review=review), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.make_project(root)
                before = self.initial(root, review)
                self.assertEqual(before["completion"], "unverified")
                self.assertTrue(before["completion_inputs_missing"])
                self.assertEqual(self.rejudge(root)["completion"], "unverified")

    def test_rejudge_does_not_complete_legacy_waiting_result(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            project = root / "sample.files"
            (project / "scripts").mkdir(parents=True)
            (project / "scripts/calc.py").write_text("print(5)\n")
            (root / "sample.jsonl").write_text("")
            path = root / "sample.meta.json"
            before = {"case": "weight-disposable", "exit_code": 0,
                      "check_passed": True, "check_output": "PASS fixture",
                      "verifier": "ok", "review_state": "ok", "review_required": False,
                      "completion": "waiting-user", "input": "original"}
            path.write_text(json.dumps(before))
            result = subprocess.run([sys.executable, "-I", str(HERE / "rejudge.py"), d],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            after = json.loads(path.read_text())
            self.assertEqual(after["completion"], "waiting-user")
            self.assertEqual(after["rejudge_history"][-1]["completion"], "waiting-user")


if __name__ == "__main__":
    unittest.main()
