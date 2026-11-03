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
    # env.txt 가 있는 표본은 실행기가 판정 검사에 넘기는 환경(EVALS_GATE·EVALS_INPUT 등)을 흉내 낸다.
    envs=(); [ ! -f "$sample/env.txt" ] || while IFS= read -r kv; do [ -z "$kv" ] || envs+=("$kv"); done < "$sample/env.txt"
    env ${envs[@]+"${envs[@]}"} EVALS_BEFORE_LAST_TURN=$before python3 -I "$dir/check.py" "$project" "$sample/transcript.jsonl" >/dev/null 2>&1; rc=$?
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
# 외부 장애(모델 용량 부족)로 끝난 실행은 실패가 아니라 미확인으로 남고 분모에서 빠진다
cap=$(mktemp -d)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$fake/claude-cap"
mkdir "$cap/bin"; cp "$fake/claude-cap" "$cap/bin/claude"; chmod +x "$cap/bin/claude"
EVALS_RESULTS=$cap PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable HEAD claude > "$cap/out" 2>&1
grep -q 'check=UNVERIFIED' "$cap/out" && grep -q '"check_unverified": true' "$cap"/weight-disposable-*-claude-1.meta.json \
  && python3 -I "$here/report.py" "$cap" | grep -q ' 0/0 ' && ok "외부 장애는 미확인으로 남고 통과 분모에서 빠짐" || ng "외부 장애 분류: $(cat "$cap/out")"
# 장애 전에 제품 파일을 바꿨으면 지우지 않고 검토 필요로 남긴다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho changed > made-by-fake.txt\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r2 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable HEAD claude > "$cap/out2" 2>&1
grep -q 'check=FAIL.*REVIEW 외부 장애' "$cap/out2" && grep -q '"check_needs_review": true' "$cap"/r2/weight-disposable-*-claude-1.meta.json \
  && ok "장애 전 제품 변경은 검토 필요로 남김" || ng "장애 전 변경 처리: $(cat "$cap/out2")"
# 바꿨다가 되돌린 뒤 장애가 나도(최종 파일은 같아도) 편집 기록이 있으면 검토 필요로 남긴다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "accounts.py"}}]}}\x27\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r4 PATH="$cap/bin:$PATH" bash "$here/run.sh" account-after-correction HEAD claude > "$cap/out4" 2>&1
grep -q 'REVIEW 외부 장애.*편집 기록: accounts.py' "$cap/out4" && ok "되돌린 편집 뒤 장애도 검토 필요로 남김" || ng "되돌린 편집 뒤 장애: $(cat "$cap/out4")"
# 승인 대기 수는 승인이 아닌 사용자 턴(prompt)만 센다(도구 검사 줄은 세지 않고, 0회도 기록된다)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\nprintf \x27{"event": "prompt", "approved": false}\\n{"event": "pre", "approved": false, "denied": true}\\n{"event": "pre", "approved": false, "denied": false}\\n\x27 >> "$AWK_GATE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\nexit 0\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r5 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable HEAD claude > /dev/null 2>&1
grep -q '"unapproved_turns": 1,' "$cap"/r5/weight-disposable-*-claude-1.meta.json && ok "승인 대기는 사용자 턴만 셈" || ng "승인 대기 집계: $(grep unapproved "$cap"/r5/*.meta.json)"
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\nprintf \x27{"event": "prompt", "approved": true}\\n\x27 >> "$AWK_GATE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\nexit 0\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r6 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable HEAD claude > /dev/null 2>&1
grep -q '"unapproved_turns": 0,' "$cap"/r6/weight-disposable-*-claude-1.meta.json && ok "승인 대기 0회도 meta 에 남음" || ng "승인 대기 0회 meta 없음"
# 일반 답 속 낱말(at capacity)은 외부 장애로 보지 않는다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "result", "result": "서버가 at capacity 일 때를 처리했습니다"}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r3 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable HEAD claude > "$cap/out3" 2>&1
grep -q 'check=FAIL FAIL 하네스가 종료 코드 1' "$cap/out3" && ok "답 속 낱말은 외부 장애로 세지 않음" || ng "답 속 낱말 처리: $(cat "$cap/out3")"
rm -rf "${cap:?}"
# 여러 턴: 두 번째 턴이 첫 턴의 세션 id 로 이어 가는지(가짜 하네스가 받은 인자로 확인)
: > "$fake/log"; FAKE_RC=0 FAKE_LOG=$fake/log EVALS_RESULTS=$results PATH="$fake:$PATH" bash "$here/run.sh" archive-after-correction HEAD claude >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(grep -c '' "$fake/log")" -eq 2 ] && sed -n 2p "$fake/log" | grep -q -- '--resume fake-sid' && ok "여러 턴: 두 번째 턴이 같은 세션을 이어 감" || ng "여러 턴 이어 가기(rc=$rc, 호출 $(grep -c '' "$fake/log")회)"
rm -rf "${fake:?}" "${results:?}"
# 승인 관문 훅(모델 없음): 승인 판별·턴마다 닫힘·쓰기 도구·셸 읽기 전용 판별·오류 시 막음
python3 -I "$here/gatetest.py" > "${TMPDIR:-/tmp}/gatetest.$$" 2>&1 && ok "승인 관문 시험 $(tail -1 "${TMPDIR:-/tmp}/gatetest.$$")" || { ng "승인 관문 시험"; grep -v '^ok' "${TMPDIR:-/tmp}/gatetest.$$"; }
rm -f "${TMPDIR:-/tmp}/gatetest.$$"
printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
