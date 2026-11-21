"""맥락 도구의 commit: 커밋 메시지 본문을 줄이지 않고 낸다.

저장 실행(대출 ③, 2026-11-21): 에이전트가 `rtk git log -1 --format=%B` 로 커밋을 읽었고, 출력 요약 래퍼가 본문(11월 운영팀
요청)을 지워 "최근 커밋에는 변경 이유가 없다"고 보고했다. 키트의 원문 읽기는 git 을 직접 부르는 이 도구로 한다.
"""
import subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / '.agents/skills/wf-context/context.py'


class CommitMessageTest(unittest.TestCase):
    def test_full_message_and_files(self):
        with tempfile.TemporaryDirectory() as d:
            git = lambda *a: subprocess.run(['git', '-C', d, '-c', 'user.name=dev-b', '-c', 'user.email=b@invalid', *a], check=True,
                                            capture_output=True)
            git('init', '-q')
            (Path(d) / 'loan.py').write_text('LOAN_DAYS = 21\n')
            git('add', '.'); git('commit', '-qm', 'feat: 대출 기한을 21일로 연장', '-m', '11월 운영팀 요청: 이용 안내 개편에 맞춘다.')
            out = subprocess.run([sys.executable, '-I', str(TOOL), 'commit', 'HEAD', d], capture_output=True, text=True).stdout
        self.assertIn('feat: 대출 기한을 21일로 연장', out)
        self.assertIn('11월 운영팀 요청: 이용 안내 개편에 맞춘다.', out)
        self.assertIn('바뀐 파일: loan.py', out)

    def test_unknown_commit(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['git', '-C', d, 'init', '-q'], check=True)
            out = subprocess.run([sys.executable, '-I', str(TOOL), 'commit', 'nope', d], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn('커밋을 찾지 못했다', out.stdout)


if __name__ == '__main__':
    unittest.main()
