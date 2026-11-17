"""비교 보고의 판단 규칙(report.decide) 시험. 모델을 부르지 않는다.

  python3 -I evals/reporttest.py

통과 수는 관찰이고 두 커밋의 차이는 따로 확인해야 하는 주장이다: 전부 뒤집힌 경우만 차이로 적는지 본다.
"""
import contextlib, io, json, sys, tempfile
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import compare, decide  # noqa: E402

checks = [
    ("1/3 대 0/3 은 차이가 아니다(말할 수 없음)", decide(1, 3, 0, 3).startswith("말할 수 없음")),
    ("2/3 대 3/3 도 차이가 아니다", decide(2, 3, 3, 3).startswith("말할 수 없음")),
    ("0/3 대 3/3 은 차이: 개선", decide(0, 3, 3, 3).startswith("차이: 개선")),
    ("3/3 대 0/3 은 차이: 퇴보", decide(3, 3, 0, 3).startswith("차이: 퇴보")),
    ("전부 뒤집혀도 한쪽이 1회뿐이면 말할 수 없음", decide(0, 1, 1, 1).startswith("말할 수 없음") and decide(0, 3, 1, 1).startswith("말할 수 없음")),
    ("양쪽 모두 통과는 회귀 확인용(우열을 가르지 못한다)", decide(3, 3, 2, 2).startswith("회귀 확인용")),
    ("양쪽 모두 실패는 재발", decide(0, 2, 0, 3).startswith("재발")),
    ("한쪽에 판정된 실행이 없으면 말할 수 없음", decide(0, 0, 3, 3).startswith("말할 수 없음") and decide(2, 2, 0, 0).startswith("말할 수 없음")),
    ("검토 필요는 사람 판독 대기로 따로 적는다", "사람 판독 대기 2" in decide(3, 3, 3, 3, pending=2) and "사람 판독 대기" not in decide(3, 3, 3, 3)),
]
# 실제 입력 → 결과 저장 → 공개 비교 경로. 사례 이름과 판정기는 그대로다.
from caseinfo import case_fingerprints
import result
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    case = root / 'same-case'; case.mkdir()
    prompt = case / 'prompt.txt'; prompt.write_text('기존 동작을 보존하세요')
    fingerprints = [case_fingerprints(case, [prompt], {})]
    prompt.write_text('새 동작을 구현하세요')
    fingerprints.append(case_fingerprints(case, [prompt], {}))
    for side, passed, fingerprint in zip(('aaaaaaa', 'bbbbbbb'), (False, True), fingerprints):
        for n in range(2):
            # 저장 경로가 입력 근거를 누락하지 않는지도 함께 확인한다.
            run = dict(case='same-case', kit_ref=side, kit_commit=side, harness='fake', run=n,
                       model='fixed', harness_version='fixed', exit_code=0, seconds=0, agents_md_bytes=0,
                       check='PASS' if passed else 'FAIL', check_output='raw', input='original',
                       user_turns=1, planned_turns=1, observed={}, verifier='off', verify_reason='',
                       verify_rounds=0, verifier_exit_code=None, review={}, baseline_changed=False,
                       verifier_tool='', review_required=False, lang='', judge_version='same',
                       codex_project_trusted=False, claude_project_settings='', global_instructions={},
                       **fingerprint)
            result.write_meta(root / f'{side}-{n}.meta.json', run)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        compare('aaaaaaa', 'bbbbbbb', [root])
    checks.append(('prompt만 바뀐 0/2→2/2는 개선이 아니라 과제 비교 불가',
                   '비교 불가' in out.getvalue() and '차이: 개선' not in out.getvalue()))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
