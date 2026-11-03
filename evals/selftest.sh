#!/usr/bin/env bash
# 모델을 부르지 않고 evals 자체를 확인한다(CI 에서 실행).
# 사례마다 통과 표본은 통과, 실패 표본은 실패로 판정하는지 본다. 판정 검사가 위반을 실제로 잡는지 확인하는 단계다.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
pass=0; failed=0
ok() { pass=$((pass+1)); printf 'ok   %s\n' "$1"; }
ng() { failed=$((failed+1)); printf 'FAIL %s\n' "$1"; }
for dir in "$here"/cases/*/; do
  name=$(basename "$dir")
  for f in prompt.txt check.py samples/pass/transcript.jsonl samples/fail/transcript.jsonl; do
    [ -f "$dir$f" ] || ng "$name: $f 없음"
  done
  for sample in "$dir"/samples/*/; do
    sample=${sample%/}; kind=$(basename "$sample"); kind=${kind%%-*}
    project=$(mktemp -d); printf '# 샘플\n' > "$project/README.md"
    [ ! -d "$sample/files" ] || cp -R "$sample/files/." "$project/"
    # before/ 가 있는 표본은 마지막 턴 직전 상태를 흉내 낸다(없으면 비교하지 않음).
    before=""; [ ! -d "$sample/before" ] || before="$sample/before"
    EVALS_BEFORE_LAST_TURN=$before python3 -I "$dir/check.py" "$project" "$sample/transcript.jsonl" >/dev/null 2>&1; rc=$?
    case "$kind" in
      pass) [ $rc -eq 0 ] && ok "$name: 통과 표본($(basename "$sample"))을 통과로" || ng "$name: 통과 표본($(basename "$sample"))을 rc=$rc 로 판정" ;;
      review) [ $rc -eq 2 ] && ok "$name: 검토 표본($(basename "$sample"))을 검토 필요로" || ng "$name: 검토 표본($(basename "$sample"))을 rc=$rc 로 판정" ;;
      *) [ $rc -eq 1 ] && ok "$name: 실패 표본($(basename "$sample"))을 실패로" || ng "$name: 실패 표본($(basename "$sample"))을 rc=$rc 로 판정" ;;
    esac
    # observe.json 이 있는 표본은 관찰 사실(편집 흔적·독립 검증 주장·검증자 흔적)도 기대값과 맞는지 본다.
    if [ -f "$sample/observe.json" ]; then
      names=$( [ ! -f "$dir/observe.txt" ] || cat "$dir/observe.txt")
      got=$(python3 -I "$here/observe.py" "$sample/transcript.jsonl" $names 2>&1)
      python3 -I -c 'import json,sys; sys.exit(json.loads(sys.argv[1]) != json.load(open(sys.argv[2])))' "$got" "$sample/observe.json" 2>/dev/null \
        && ok "$name: 관찰($(basename "$sample")) 기대값과 같음" || ng "$name: 관찰($(basename "$sample")) 다름: $got"
    fi
    rm -rf "${project:?}"
  done
done
# 사례 규모: 실패 종류마다 사례를 늘리지 않는지 추세를 보려고 사례·표본 수와 바이트를 찍는다(판정에는 쓰지 않는다).
printf 'size cases=%s samples=%s bytes=%s\n' "$(ls -d "$here"/cases/*/ | wc -l | tr -d ' ')" "$(ls -d "$here"/cases/*/samples/*/ | wc -l | tr -d ' ')" "$(du -sk "$here/cases" | cut -f1)KiB"
# 실행기: 문법과, 잘못된 인자에서 모델을 부르지 않고 실패하는지
bash -n "$here/run.sh" && ok "run.sh 문법" || ng "run.sh 문법"
bash "$here/run.sh" no-such-case HEAD claude >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "없는 사례는 실행 전에 거절(rc=2)" || ng "없는 사례 처리(rc=$rc)"
bash "$here/run.sh" weight-disposable no-such-ref claude >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "없는 키트 커밋은 실행 전에 거절(rc=2)" || ng "없는 커밋 처리(rc=$rc)"
# 실행기 계약: 가짜 하네스(종료 코드 7, 파일 하나를 만듦)로 종료 코드를 그대로 돌려주는지와 끝난 프로젝트 파일·메타데이터를 남기는지 본다.
fake=$(mktemp -d); results=$(mktemp -d)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho "$*" >> "$FAKE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\necho made > made-by-fake.txt\nexit "${FAKE_RC:-7}"\n' > "$fake/claude"; chmod +x "$fake/claude"
FAKE_LOG=$fake/log EVALS_RESULTS=$results PATH="$fake:$PATH" bash "$here/run.sh" weight-disposable HEAD claude >/dev/null 2>&1; rc=$?
[ $rc -eq 7 ] && ok "하네스 종료 코드 7을 그대로 반환" || ng "하네스 종료 코드 반환(rc=$rc)"
snap=$(ls -d "$results"/weight-disposable-*-claude-1.files 2>/dev/null | tail -1)
[ -f "$snap/made-by-fake.txt" ] && ok "끝난 프로젝트 파일 보존" || ng "끝난 프로젝트 파일이 남지 않음"
grep -q '"exit_code": 7' "${snap%.files}.meta.json" 2>/dev/null && ok "메타데이터에 종료 코드 기록" || ng "메타데이터 종료 코드"
# 여러 턴: 두 번째 턴이 첫 턴의 세션 id 로 이어 가는지(가짜 하네스가 받은 인자로 확인)
: > "$fake/log"; FAKE_RC=0 FAKE_LOG=$fake/log EVALS_RESULTS=$results PATH="$fake:$PATH" bash "$here/run.sh" archive-after-correction HEAD claude >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(grep -c '' "$fake/log")" -eq 2 ] && sed -n 2p "$fake/log" | grep -q -- '--resume fake-sid' && ok "여러 턴: 두 번째 턴이 같은 세션을 이어 감" || ng "여러 턴 이어 가기(rc=$rc, 호출 $(grep -c '' "$fake/log")회)"
rm -rf "${fake:?}" "${results:?}"
# 승인 관문 훅(모델 없음): 승인 판별·턴마다 닫힘·쓰기 도구·셸 읽기 전용 판별·오류 시 막음
python3 -I "$here/gatetest.py" > "${TMPDIR:-/tmp}/gatetest.$$" 2>&1 && ok "승인 관문 시험 $(tail -1 "${TMPDIR:-/tmp}/gatetest.$$")" || { ng "승인 관문 시험"; grep -v '^ok' "${TMPDIR:-/tmp}/gatetest.$$"; }
rm -f "${TMPDIR:-/tmp}/gatetest.$$"
printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
