"""모의 사용자 분류기 출력 읽기: 같은 답을 설명과 함께 두 번 낸 출력(2026-11-20 라벨 5회차 실제 출력 모양)은 하나로 읽고,
서로 다른 답이 여럿이거나 답이 없으면 형식 오류로 멈춘다."""
import sys, unittest
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'evals'), str(Path(__file__).resolve().parents[1] / 'evals/goalflow')]
from asked import parse_quotes

ANSWER = '{"quotes": {"1": "가", "2": null}}'


class ClassifierAnswerTest(unittest.TestCase):
    def test_same_answer_repeated_with_commentary(self):
        self.assertEqual(parse_quotes(ANSWER + '\n\nWait — the quotes must be verbatim. Corrected:\n\n' + ANSWER), {'1': '가', '2': None})

    def test_different_answers_stop(self):
        with self.assertRaisesRegex(RuntimeError, '서로 다른 답'):
            parse_quotes(ANSWER + '\n' + '{"quotes": {"1": null, "2": "나"}}')

    def test_same_topics_reworded_uses_verifiable_quote(self):
        reply = '1. **가나다 라:** 물었다'
        first = '{"quotes": {"1": "가나다 라마", "2": null}}'
        fixed = '{"quotes": {"1": "**가나다 라:** 물었다", "2": null}}'
        self.assertEqual(parse_quotes(first + '\nCorrection:\n' + fixed, reply), {'1': '**가나다 라:** 물었다', '2': None})

    def test_no_answer_stops(self):
        with self.assertRaisesRegex(RuntimeError, '판단 실패'):
            parse_quotes('설명만 있다')


if __name__ == '__main__':
    unittest.main()
