"""평가 실행기가 쓰는 판정 함수. 실제 내용은 설치되는 독립 검증 실행기(.agents/skills/wf-verify/verify.py)에 있고,
이 파일은 그 함수를 그대로 내보낸다(일반 설치와 평가가 같은 판정 규칙을 쓰게 하려는 것이다).

검증자는 답 끝에 JSON 하나를 쓴다(.agents/skills/wf-verify/verifier-prompt.txt 의 형식):
  {"verdict": "OK" 또는 "RETURN", "conditions": [{"id": "C1", "result": "충족|미충족|미확인", "evidence": "..."}],
   "return_reason": "...", "out_of_scope": ["..."]}
판정(state): ok / returned / unverified(그 밖 전부, 완료 아님). out_of_scope 는 판정을 막지 않고 따로 남긴다.

사용:
  python3 -I evals/verdict.py judge <검증자 기록 .jsonl> [필수 조건 ID ...]   → 판정 JSON 한 줄
  python3 -I evals/verdict.py baseline <프로젝트>                              → 작업 지도들의 `## 기준` 절(검증자에게 넘길 합의 조건)
  python3 -I evals/verdict.py completion <검증 상태> <PASS|REVIEW|FAIL|UNVERIFIED> [waiting] → 전체 완료 판정
  python3 -I evals/verdict.py ids <파일>                                       → 파일에 적힌 조건 ID(표의 첫 칸 또는 줄 머리)
"""
import importlib.util, json, sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("awk_verify", Path(__file__).resolve().parents[1] / ".agents/skills/wf-verify/verify.py")
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)
last_json, judge, completion, baseline, ids, final_answer, run_result = (_verify.last_json, _verify.judge, _verify.completion, _verify.baseline,
                                                                         _verify.ids, _verify.final_answer, _verify.run_result)

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "judge":
        print(json.dumps(judge(final_answer(sys.argv[2]) if Path(sys.argv[2]).is_file() else "", sys.argv[3:]), ensure_ascii=False))
    elif cmd == "baseline":
        print(baseline(sys.argv[2]))
    elif cmd == "completion":
        print(completion(sys.argv[2], sys.argv[3], len(sys.argv) > 4 and sys.argv[4] == "waiting"))
    elif cmd == "ids":
        print(" ".join(ids(Path(sys.argv[2]).read_text(encoding="utf-8") if Path(sys.argv[2]).is_file() else "")))
