"""유료 행동 평가 전에 쓸 문서 검사와 전체 자체 검사가 같은 한도를 적용한다."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECK = Path(__file__).resolve().parents[1] / 'evals/document_budget.py'


class DocumentBudget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skills = self.root / '.agents/skills'
        (self.skills / 'wf-verify').mkdir(parents=True)
        (self.root / 'AGENTS.md').write_text('<!-- agent-workflow-kit:begin -->\n작업\n<!-- agent-workflow-kit:end -->\n' + 'project' * 2000)
        (self.skills / 'wf-verify/verify.py').write_text('VERIFIER_PROMPT = "검토 근거"\n')
        self.skill = self.skills / 'wf-verify/SKILL.md'

    def run_check(self):
        return subprocess.run([sys.executable, '-I', str(CHECK), str(self.root)], capture_output=True, text=True)

    def test_existing_byte_limit_rejects_the_observed_failure(self):
        self.skill.write_bytes(b'x' * 4517)
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('4517B > 4500B', result.stdout)

    def test_project_section_does_not_spend_the_kits_budget(self):
        self.skill.write_bytes(b'x' * 4441)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('설치 문서 전체', result.stdout)

    def test_total_includes_each_installed_document_and_reviewer_prompt(self):
        self.skill.write_bytes(b'x' * 4000)
        for number in range(8):
            (self.skills / f'reference-{number}.md').write_bytes(b'x' * 4000)
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('설치 문서 전체', result.stdout)


if __name__ == '__main__':
    unittest.main()
