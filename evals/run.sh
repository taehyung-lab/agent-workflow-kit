#!/usr/bin/env bash
# 키트 문장의 행동 효과를 새 세션으로 잰다. 본체는 run.py 다(옵션·동작 설명도 그 파일 머리에 있다).
#
# 사용: bash evals/run.sh <사례[,사례…]> <키트 커밋·태그> <claude|codex> [반복 수]
#   예: bash evals/run.sh weight-accounting v1.0.0 claude 2
#       bash evals/run.sh recommend-from-context v3.7.0..HEAD codex 2   (두 커밋 비교, 끝에 report.py --compare)
# 결과 요약: python3 -I evals/report.py evals/results
exec python3 -I "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/run.py" "$@"
