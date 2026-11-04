#!/usr/bin/env bash
# 모델을 부르지 않고 evals 자체를 확인한다(CI 에서 실행).
# 사례마다 통과 표본은 통과, 실패 표본은 실패로 판정하는지 본다. 판정 검사가 위반을 실제로 잡는지 확인하는 단계다.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
pass=0; failed=0
ok() { pass=$((pass+1)); printf 'ok   %s\n' "$1"; }
ng() { failed=$((failed+1)); printf 'FAIL %s\n' "$1"; }
# 실행기(run.sh)를 거치는 시험이 설치할 키트: 커밋하지 않은 변경까지 담은 작업 트리 스냅숏 커밋(브랜치·HEAD 는 바꾸지 않는다).
# HEAD 를 그대로 쓰면 작업 트리에서 고친 것이 시험에 들어가지 않아, 고치기 전 코드로 통과한 결과를 보게 된다.
kitdir=$(cd -- "$here/.." && pwd -P); tmpidx=$(mktemp -u)
tree=$(GIT_INDEX_FILE=$tmpidx git -C "$kitdir" add -A >/dev/null 2>&1 && GIT_INDEX_FILE=$tmpidx git -C "$kitdir" write-tree); rm -f "$tmpidx"
[ -n "$tree" ] || { printf 'FAIL 작업 트리 스냅숏을 만들지 못했다\n'; exit 1; }
if [ "$tree" = "$(git -C "$kitdir" rev-parse 'HEAD^{tree}')" ]; then REF=HEAD; else
  REF=$(git -C "$kitdir" -c user.name=selftest -c user.email=selftest@invalid commit-tree "$tree" -p HEAD -m selftest-worktree); fi
printf '시험 대상 키트: %s\n' "$( [ "$REF" = HEAD ] && echo "HEAD $(git -C "$kitdir" rev-parse --short HEAD)" || echo "작업 트리 스냅숏 ${REF:0:7}(미커밋 변경 포함)")"
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
    # 기대값에 적힌 항목은 모두 같아야 한다. 측정값(first_reply_chars 등)처럼 기대값에 없는 항목은 비교하지 않는다.
    if [ -f "$sample/observe.json" ]; then
      names=$( [ ! -f "$dir/observe.txt" ] || cat "$dir/observe.txt")
      got=$(python3 -I "$here/observe.py" "$sample/transcript.jsonl" $names 2>&1)
      python3 -I -c 'import json,sys; g=json.loads(sys.argv[1]); w=json.load(open(sys.argv[2])); sys.exit(any(g.get(k, KeyError) != v for k, v in w.items()))' "$got" "$sample/observe.json" 2>/dev/null \
        && ok "$name: 관찰($(basename "$sample")) 기대값과 같음" || ng "$name: 관찰($(basename "$sample")) 다름: $got"
    fi
    rm -rf "${project:?}"
  done
done
# 사례 규모: 실패 종류마다 사례를 늘리지 않는지 추세를 보려고 사례·표본 수와 바이트를 찍는다(판정에는 쓰지 않는다).
printf 'size cases=%s samples=%s bytes=%s\n' "$(ls -d "$here"/cases/*/ | wc -l | tr -d ' ')" "$(ls -d "$here"/cases/*/samples/*/ | wc -l | tr -d ' ')" "$(du -sk "$here/cases" | cut -f1)KiB"
# 실행기: 문법과, 잘못된 인자에서 모델을 부르지 않고 실패하는지
bash -n "$here/run.sh" && ok "run.sh 문법" || ng "run.sh 문법"
bash "$here/run.sh" no-such-case "$REF" claude >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "없는 사례는 실행 전에 거절(rc=2)" || ng "없는 사례 처리(rc=$rc)"
bash "$here/run.sh" weight-disposable no-such-ref claude >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "없는 키트 커밋은 실행 전에 거절(rc=2)" || ng "없는 커밋 처리(rc=$rc)"
# 실행기 계약: 가짜 하네스(종료 코드 7, 파일 하나를 만듦)로 종료 코드를 그대로 돌려주는지와 끝난 프로젝트 파일·메타데이터를 남기는지 본다.
fake=$(mktemp -d); results=$(mktemp -d)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho "$*" >> "$FAKE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\necho made > made-by-fake.txt\nexit "${FAKE_RC:-7}"\n' > "$fake/claude"; chmod +x "$fake/claude"
FAKE_LOG=$fake/log EVALS_RESULTS=$results PATH="$fake:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude >/dev/null 2>&1; rc=$?
[ $rc -eq 7 ] && ok "하네스 종료 코드 7을 그대로 반환" || ng "하네스 종료 코드 반환(rc=$rc)"
snap=$(ls -d "$results"/weight-disposable-*-claude-1.files 2>/dev/null | tail -1)
[ -f "$snap/made-by-fake.txt" ] && ok "끝난 프로젝트 파일 보존" || ng "끝난 프로젝트 파일이 남지 않음"
grep -q '"exit_code": 7' "${snap%.files}.meta.json" 2>/dev/null && ok "메타데이터에 종료 코드 기록" || ng "메타데이터 종료 코드"
# 외부 장애(모델 용량 부족)로 끝난 실행은 실패가 아니라 미확인으로 남고 분모에서 빠진다
cap=$(mktemp -d)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$fake/claude-cap"
mkdir "$cap/bin"; cp "$fake/claude-cap" "$cap/bin/claude"; chmod +x "$cap/bin/claude"
EVALS_RESULTS=$cap PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > "$cap/out" 2>&1
grep -q 'check=UNVERIFIED' "$cap/out" && grep -q '"check_unverified": true' "$cap"/weight-disposable-*-claude-1.meta.json \
  && python3 -I "$here/report.py" "$cap" | grep -q ' 0/0 ' && ok "외부 장애는 미확인으로 남고 통과 분모에서 빠짐" || ng "외부 장애 분류: $(cat "$cap/out")"
# 장애 전에 제품 파일을 바꿨으면 지우지 않고 검토 필요로 남긴다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho changed > made-by-fake.txt\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r2 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > "$cap/out2" 2>&1
grep -q 'check=REVIEW REVIEW 외부 장애' "$cap/out2" && grep -q '"check_needs_review": true' "$cap"/r2/weight-disposable-*-claude-1.meta.json \
  && ok "장애 전 제품 변경은 검토 필요로 남김" || ng "장애 전 변경 처리: $(cat "$cap/out2")"
# 바꿨다가 되돌린 뒤 장애가 나도(최종 파일은 같아도) 편집 기록이 있으면 검토 필요로 남긴다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "accounts.py"}}]}}\x27\necho \x27{"type": "error", "message": "Selected model is at capacity."}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r4 PATH="$cap/bin:$PATH" bash "$here/run.sh" account-after-correction "$REF" claude > "$cap/out4" 2>&1
grep -q 'REVIEW 외부 장애.*편집 기록: accounts.py' "$cap/out4" && ok "되돌린 편집 뒤 장애도 검토 필요로 남김" || ng "되돌린 편집 뒤 장애: $(cat "$cap/out4")"
# 승인 대기 수는 승인이 아닌 사용자 턴(prompt)만 센다(도구 검사 줄은 세지 않고, 0회도 기록된다)
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\nprintf \x27{"event": "prompt", "approved": false}\\n{"event": "pre", "approved": false, "denied": true}\\n{"event": "pre", "approved": false, "denied": false}\\n{"event": "prompt", "approved": false}\\n\x27 >> "$AWK_GATE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\nexit 0\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r5 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > /dev/null 2>&1
grep -q '"unapproved_turns": 1,' "$cap"/r5/weight-disposable-*-claude-1.meta.json && ok "승인 대기는 사용자 턴만 셈(뒤따르는 실행기 반환 턴의 prompt 기록은 세지 않음)" || ng "승인 대기 집계: $(grep unapproved "$cap"/r5/*.meta.json)"
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\nprintf \x27{"event": "prompt", "approved": true}\\n\x27 >> "$AWK_GATE_LOG"\necho \x27{"session_id": "fake-sid"}\x27\nexit 0\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r6 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > /dev/null 2>&1
grep -q '"unapproved_turns": 0,' "$cap"/r6/weight-disposable-*-claude-1.meta.json && ok "승인 대기 0회도 meta 에 남음" || ng "승인 대기 0회 meta 없음"
# 일반 답 속 낱말(at capacity)은 외부 장애로 보지 않는다
printf '#!/bin/sh\n[ "$1" = --version ] && { echo fake 0; exit 0; }\necho \x27{"type": "result", "result": "서버가 at capacity 일 때를 처리했습니다"}\x27\nexit 1\n' > "$cap/bin/claude"
EVALS_RESULTS=$cap/r3 PATH="$cap/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > "$cap/out3" 2>&1
grep -q 'check=FAIL FAIL 하네스가 종료 코드 1' "$cap/out3" && ok "답 속 낱말은 외부 장애로 세지 않음" || ng "답 속 낱말 처리: $(cat "$cap/out3")"
rm -rf "${cap:?}"
# 여러 턴: 두 번째 턴이 첫 턴의 세션 id 로 이어 가는지(가짜 하네스가 받은 인자로 확인)
: > "$fake/log"; FAKE_RC=0 FAKE_LOG=$fake/log EVALS_RESULTS=$results PATH="$fake:$PATH" bash "$here/run.sh" archive-after-correction "$REF" claude >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(grep -c '' "$fake/log")" -eq 2 ] && sed -n 2p "$fake/log" | grep -q -- '--resume fake-sid' && ok "여러 턴: 두 번째 턴이 같은 세션을 이어 감" || ng "여러 턴 이어 가기(rc=$rc, 호출 $(grep -c '' "$fake/log")회)"
rm -rf "${fake:?}" "${results:?}"
# 독립 검증 루프(가짜 하네스): 검증자 입력의 독립성, 정해진 결과 형식만 통과, 반환 → 교정 → 새 버전 재검증, 한도 = 미완료, 수정 = 무효
vf=$(mktemp -d); mkdir "$vf/bin"
cat > "$vf/bin/claude" <<'FAKE'
#!/bin/sh
[ "$1" = --version ] && { echo fake 0; exit 0; }
case "$2" in
  *"당신은 별도 검증자다"*)
    n=$(cat "$FAKE_DIR/vn" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_DIR/vn"
    printf '%s' "$2" > "$FAKE_DIR/vprompt.$n"
    [ -z "${FAKE_VWRITE:-}" ] || echo changed >> README.md
    [ -z "${FAKE_VARTIFACT:-}" ] || echo cache > made-by-check.cache
    line=$(sed -n "${n}p" "$FAKE_DIR/verdicts")
    printf '{"type": "result", "result": %s}\n' "$line"
    exit "${FAKE_VRC:-0}";;
  *) echo call >> "$FAKE_DIR/impl"; echo "${AWK_GATE_PROMPT_FROM:-user}" >> "$FAKE_DIR/from"; echo '{"session_id": "fake-sid"}'
     # 승인 턴·교정 턴의 답은 구현 뒤 자기평가(검증자에게 가면 안 됨), 첫 턴 답은 사용자가 승인할 계획이다.
     case "$2" in *"승인합니다"*|*"별도 검증자가"*) echo '{"type": "result", "result": "IMPL-ANSWER-MARKER 다 했습니다"}';;
       *) [ -n "${FAKE_NOPLAN:-}" ] || echo '{"type": "result", "result": "PLAN-MARKER 추천안: calc.py 로 두 수의 합. 승인해 주시겠어요?"}';; esac
     echo "turn" >> made-by-impl.txt
     # 사례 판정(weight-disposable)이 통과하는 결과물. FAKE_BREAK 면 만들지 않아 결정적 검사가 실패한다.
     [ -n "${FAKE_BREAK:-}" ] || { mkdir -p scripts; printf 'import sys\nprint(int(sys.argv[1]) + int(sys.argv[2]))\n' > scripts/calc.py; }
     [ -z "${FAKE_MAP:-}" ] || { mkdir -p work/t; printf '# t\n\n## 기준\n\n| ID | 결과 |\n| --- | --- |\n| C1 | 출력 |\n| C9 | 기존 보장 |\n\n## 증거\n\nSELF-ASSESS-MARKER 전부 충족\n' > work/t/work.md; }
     # 교정 턴(검증자 반환)에서 지도 기준을 바꾸는 구현자: 승인된 기준이 아니므로 재검증 기준이 되면 안 된다.
     case "$2" in *"별도 검증자가 다음 사유로"*) [ -z "${FAKE_REMAP:-}" ] || printf '# t\n\n## 기준\n\n| ID | 결과 |\n| --- | --- |\n| C1 | 출력 |\n| C7 | 바꾼 기준 |\n' > work/t/work.md;; esac
     exit 0;;
esac
FAKE
chmod +x "$vf/bin/claude"
OKV='"설명.\n{\"verdict\": \"OK\", \"conditions\": [{\"id\": \"C1\", \"result\": \"충족\", \"evidence\": \"python3 x 실행 결과 1\"}], \"out_of_scope\": []}"'
RETV='"{\"verdict\": \"RETURN\", \"conditions\": [{\"id\": \"C1\", \"result\": \"미충족\", \"evidence\": \"출력 없음\"}], \"return_reason\": \"C1 미충족\"}"'
vrun() {  # vrun <이름> <판정 줄...>: 가짜 검증자가 차례로 낼 답을 받아 weight-disposable 을 승인 턴 포함·EVALS_VERIFY=1 로 돈다
  d="$vf/$1"; shift; mkdir -p "$d"; : > "$d/verdicts"; for v in "$@"; do printf '%s\n' "$v" >> "$d/verdicts"; done
  FAKE_DIR=$d EVALS_VERIFY=1 EVALS_APPROVE=1 EVALS_RESULTS=$d/r PATH="$vf/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" claude > "$d/out" 2>&1; echo $? > "$d/rc"
  meta=$(ls "$d"/r/*.meta.json 2>/dev/null | head -1)
}
mget() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m.get(sys.argv[2]))' "$meta" "$1" 2>/dev/null; }
vrun empty '""'
[ "$(mget verifier)" = unverified ] && [ "$(mget completion)" = unverified ] && ok "검증: 빈 답은 미확인이고 완료가 아님" || ng "검증 빈 답: $(mget verifier)/$(mget completion)"
vrun prose '"좋아 보입니다. 모든 조건을 충족합니다."'
[ "$(mget verifier)" = unverified ] && ok "검증: 형식 없는 칭찬은 미확인" || ng "검증 형식 없음: $(mget verifier)"
vrun okunmet '"{\"verdict\": \"OK\", \"conditions\": [{\"id\": \"C1\", \"result\": \"미확인\", \"evidence\": \"못 돌림\"}]}"'
[ "$(mget verifier)" = unverified ] && ok "검증: OK 인데 미확인 조건이 있으면 미확인" || ng "검증 OK+미확인: $(mget verifier)"
vrun noevidence '"{\"verdict\": \"OK\", \"conditions\": [{\"id\": \"C1\", \"result\": \"충족\", \"evidence\": \"\"}]}"'
[ "$(mget verifier)" = unverified ] && ok "검증: 근거 없는 충족은 미확인" || ng "검증 근거 없음: $(mget verifier)"
vrun ok "$OKV"
[ "$(mget verifier)" = ok ] && [ "$(mget completion)" = verified ] && [ "$(mget verify_rounds)" = 1 ] && ok "검증: 형식대로 모두 충족이면 완료" || ng "검증 OK: $(mget verifier)/$(mget completion)"
python3 -I "$here/report.py" "$vf/ok/r" | awk 'NR==2{exit !($(NF-5)==1 && $(NF-4)==0 && $(NF-3)==0 && $(NF-2)==0)}' && ok "보고: 검증 완료를 단계 통과·답 대기와 따로 셈" || ng "보고 검증 완료 열: $(python3 -I "$here/report.py" "$vf/ok/r")"
! grep -q IMPL-ANSWER-MARKER "$vf/ok/vprompt.1" && grep -q '사용자 원문 1' "$vf/ok/vprompt.1" && grep -q 'made-by-impl.txt' "$vf/ok/vprompt.1" \
  && grep -q 'PLAN-MARKER' "$vf/ok/vprompt.1" \
  && ok "검증: 검증자는 원문·승인 원문이 가리키는 계획·작업 시작부터의 변경을 받고 구현 뒤 답(자기평가)은 받지 않음" || ng "검증 입력 독립성"
FAKE_NOPLAN=1 vrun noplan "$OKV"
grep -q '추출 실패' "$vf/noplan/vprompt.1" && ok "검증: 승인 직전 계획을 추출하지 못하면 성공처럼 비우지 않고 추출 실패를 적음" || ng "검증 계획 추출 실패 표시"
vrun again "$RETV" "$OKV"
[ "$(mget verifier)" = ok ] && [ "$(mget verify_rounds)" = 2 ] && [ "$(grep -c '' "$vf/again/impl")" = 3 ] && grep -q 'made-by-impl.txt' "$vf/again/vprompt.2" \
  && [ "$(grep -c turn "$vf/again/vprompt.2")" -gt "$(grep -c turn "$vf/again/vprompt.1")" ] \
  && ok "검증: RETURN → 구현자 교정 턴 → 새 버전을 다시 판정" || ng "검증 재검증: $(mget verifier) rounds=$(mget verify_rounds)"
[ "$(tr '\n' ' ' < "$vf/again/from")" = "user user runner " ] && ok "검증 반환 턴에만 실행기 발신 구분(AWK_GATE_PROMPT_FROM=runner)을 넘김" || ng "반환 턴 발신 구분: $(tr '\n' ' ' < "$vf/again/from")"
vrun limit "$RETV" "$RETV" "$RETV"
[ "$(mget verifier)" = incomplete ] && [ "$(mget verify_rounds)" = 2 ] && [ "$(mget completion)" = incomplete ] && ok "검증: 재검증 한도에 닿으면 미완료(성공 아님)" || ng "검증 한도: $(mget verifier) rounds=$(mget verify_rounds)"
FAKE_VWRITE=1 vrun touched "$OKV"
[ "$(mget verifier)" = unverified ] && grep -q '추적 파일' "$meta" && ok "검증: 검증자가 추적 파일을 바꾸면 그 판정은 미확인" || ng "검증 수정 무효: $(mget verifier)"
FAKE_VARTIFACT=1 vrun artifact "$OKV"
[ "$(mget verifier)" = ok ] && ok "검증: 검사가 만든 새 파일(산출물·캐시)은 판정을 무효로 만들지 않음" || ng "검증 산출물: $(mget verifier) $(mget verify_reason)"
FAKE_VRC=5 vrun crash "$OKV"
[ "$(mget verifier)" = unverified ] && [ "$(mget verifier_exit_code)" = 5 ] && [ "$(mget exit_code)" = 0 ] && [ "$(cat "$vf/crash/rc")" = 0 ] \
  && ok "검증: 검증자 종료 코드 5 는 보존되고 미확인, 구현자 종료 코드는 그대로" || ng "검증자 오류: $(mget verifier) vrc=$(mget verifier_exit_code) rc=$(mget exit_code)"
vrun oos '"{\"verdict\": \"OK\", \"conditions\": [{\"id\": \"C1\", \"result\": \"충족\", \"evidence\": \"실행 결과\"}], \"out_of_scope\": [\"새 요구: 음수 입력 처리\"]}"'
[ "$(mget verifier)" = ok ] && grep -q '음수 입력' "$meta" && ok "검증: 범위 밖 반례는 완료를 막지 않고 따로 남음" || ng "검증 범위 밖: $(mget verifier)"
FAKE_MAP=1 vrun map "$OKV"
grep -q 'C9 | 기존 보장' "$vf/map/vprompt.1" && ! grep -q SELF-ASSESS-MARKER "$vf/map/vprompt.1" && [ "$(mget verifier)" = unverified ] && grep -q 'C9' "$meta" \
  && ok "검증: 작업 지도의 기준만 넘기고(증거·자기평가 제외) 그 ID 를 필수 조건으로 요구" || ng "검증 지도 기준: $(mget verifier) $(mget verify_reason)"
# 답 맨 끝의 최종 결과 JSON 만 판정으로 읽는다: 끊긴 최종 JSON·뒤에 붙은 글에서 앞선 OK 로 통과하지 않음, 코드 울타리·설명 뒤 JSON 은 지원
python3 -I - "$here" <<'PY' && ok "검증 형식: 끊긴 최종 JSON 은 미확인(앞선 OK 로 대체 안 함), 울타리·설명+최종 JSON 은 읽음" || ng "검증 형식: 최종 JSON 판정"
import sys; sys.path.insert(0, sys.argv[1]); from verdict import judge
ok = '{"verdict": "OK", "conditions": [{"id": "C1", "result": "충족", "evidence": "실행 결과 1"}]}'
assert judge("예시 " + ok + ' 최종: {"verdict": "RETURN"')["state"] == "unverified"
assert judge("예시 " + ok + ' 최종: {"verdict": "OK", "conditions": [')["state"] == "unverified"
assert judge("판정 설명입니다.\n```json\n" + ok + "\n```\n")["state"] == "ok"
assert judge("설명.\n" + ok)["state"] == "ok"
assert judge('예시 {"verdict": "RETURN", "return_reason": "x"} 최종 ' + ok)["state"] == "ok"
# 답 맨 끝이 최종 JSON 이어야 한다: 완결 OK 뒤에 키까지 끊긴 객체·추가 글이 붙으면 앞선 OK 를 쓰지 않는다
assert judge(ok + '\n{"verdi')["state"] == "unverified"
assert judge("```json\n" + ok + '\n```\n{"verdi')["state"] == "unverified"
assert judge(ok + "\n이상입니다.")["state"] == "unverified"
assert judge(ok + '\n{"note": 1}')["state"] == "unverified"
PY
# 검증 실행 관찰(observe.verify_run) 반례 표본(독립 리뷰 7c39b22 의 18개): 앞선 OK 뒤의 오류·빈 출력·끊긴 JSON, 실행기 파일·저장된 결과 읽기,
# 결과 없는 실행은 ok 로 이어 쓰지 않는다. 두 하네스 기록 형식 모두.
python3 -I - "$here" <<'PY' && ok "검증 실행 관찰: 반례 18개(두 하네스 × 9)에서 앞선 OK·저장 결과·읽기를 실행 판정으로 쓰지 않음" || ng "검증 실행 관찰 반례"
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1]); from observe import verify_run
V = "python3 .agents/skills/wf-verify/verify.py"
ok = json.dumps({"state": "ok", "completion": "verified"}); waiting = json.dumps({"state": "ok", "completion": "waiting-user"})
cases = {"current-ok": [(V, ok, 0)], "waiting": [(V, waiting, 0)], "error-after-ok": [(V, ok, 1)], "malformed-after-ok": [(V, ok + '\n{"state":', 0)],
         "empty-after-ok": [(V, ok, 0), (V, "", 0)], "invalid-after-ok": [(V, ok, 0), (V, '{"state":', 0)],
         "read-mixed": [("cat .agents/skills/wf-verify/verify.py old-result.json", "import json\n" + ok, 0)], "read-result": [("cat old-result.json", ok, 0)],
         "unknown": [(V, None, None)]}
bad = []
with tempfile.TemporaryDirectory() as d:
    for harness in ("claude", "codex"):
        for name, commands in cases.items():
            events = []
            for i, (command, output, code) in enumerate(commands):
                if harness == "codex":
                    events.append({"type": "item.completed", "item": {"id": str(i), "type": "command_execution", "command": command, "aggregated_output": output, "exit_code": code}})
                else:
                    events.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": str(i), "name": "Bash", "input": {"command": command}}]}})
                    if output is not None:
                        events.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": str(i), "content": (f"Exit code {code}\n" if code else "") + output, "is_error": bool(code)}]}})
            path = Path(d) / "t.jsonl"; path.write_text("\n".join(map(json.dumps, events)))
            state, _, completion = verify_run(path)
            want = (state == "ok" and completion == ("waiting-user" if name == "waiting" else "verified")) if name in ("waiting", "current-ok") else (state != "ok" and completion != "verified")
            if not want:
                bad.append(f"{harness}/{name}: {state}/{completion}")
print("\n".join(bad)); sys.exit(1 if bad else 0)
PY
python3 -I - "$here" <<'PY' && ok "완료 분류: verified 만 완료, 사용자 답 대기·구현 실패·검증 실패·미확인을 서로 구별" || ng "완료 분류"
import sys; sys.path.insert(0, sys.argv[1]); from verdict import completion as c
assert c("ok", "PASS") == "verified" and c("ok", "REVIEW", True) == "waiting-user" and c("ok", "FAIL", True) == "waiting-user"
assert c("ok", "FAIL") == "check-failed" and c("ok", "UNVERIFIED") == "unverified"
assert c("returned", "FAIL", True) == "waiting-user" and c("off", "FAIL", True) == "waiting-user"
assert c("incomplete", "FAIL") == "incomplete" and c("returned", "PASS") == "returned" and c("unverified", "PASS") == "unverified" and c("off", "PASS") == "not-verified"
PY
FAKE_BREAK=1 vrun checkfail "$OKV"
[ "$(mget verifier)" = ok ] && [ "$(mget completion)" = check-failed ] && [ "$(mget check_passed)" = False ] \
  && ok "검증: 검증자가 OK 여도 결정적 행동 검사가 실패하면 완료(verified)로 세지 않음" || ng "검증 OK+검사 실패: $(mget verifier)/$(mget completion)"
# 다시 판정해도 최초 실행과 같은 완료 규칙: 검증 OK·검사 PASS 였던 실행의 결과물이 깨진 뒤 rejudge → check-failed, 이전 완료는 이력에
rm -f "$vf/ok/r"/*.files/scripts/calc.py; python3 -I "$here/rejudge.py" "$vf/ok/r" >/dev/null 2>&1; meta=$(ls "$vf/ok/r"/*.meta.json | head -1)
[ "$(mget completion)" = check-failed ] && python3 -I -c 'import json,sys; h=json.load(open(sys.argv[1]))["rejudge_history"][-1]; sys.exit(h["completion"] != "verified")' "$meta" \
  && ok "재판정: 새 판정 FAIL 이면 completion 도 같은 규칙으로 check-failed, 이전 completion 은 이력에 보존" || ng "재판정 완료: $(mget completion)"
FAKE_MAP=1 FAKE_REMAP=1 vrun remap "$RETV" "$OKV"
grep -q 'C9 | 기존 보장' "$vf/remap/vprompt.2" && grep -q '승인 뒤 작업 지도의 기준을 바꿨다' "$vf/remap/vprompt.2" && ! grep -q '승인 뒤 작업 지도의 기준을 바꿨다' "$vf/remap/vprompt.1" \
  && [ "$(mget baseline_changed_after_approval)" = True ] && grep -q 'C9' "$meta" \
  && ok "검증: 재검증은 구현자가 고친 지도가 아니라 처음 고정한 기준(C9 유지)으로 하고, 기준 변경을 알림" || ng "검증 기준 고정: $(mget verifier) $(mget verify_reason)"
# 필수 조건 누락: 사례가 필수 조건을 정하면 그 ID 가 모두 있어야 한다
cp -R "$here/cases/weight-disposable" "$here/cases/zz-selftest-required"; printf 'C1 결과 출력\nC2 기존 보장\n' > "$here/cases/zz-selftest-required/verify-conditions.txt"
d="$vf/required"; mkdir -p "$d"; printf '%s\n' "$OKV" > "$d/verdicts"
FAKE_DIR=$d EVALS_VERIFY=1 EVALS_RESULTS=$d/r PATH="$vf/bin:$PATH" bash "$here/run.sh" zz-selftest-required "$REF" claude > "$d/out" 2>&1; meta=$(ls "$d"/r/*.meta.json | head -1)
rm -rf "$here/cases/zz-selftest-required"
[ "$(mget verifier)" = unverified ] && grep -q 'C2' "$meta" && grep -q 'C2 기존 보장' "$d/vprompt.1" && ok "검증: 필수 조건(C2) 결과가 빠지면 미확인" || ng "검증 필수 조건: $(mget verifier) $(mget verify_reason)"
# 판정 검사 자체의 오류(예외)는 실패가 아니라 미확인이다
cp -R "$here/cases/weight-disposable" "$here/cases/zz-selftest-crash"; printf 'raise RuntimeError("판정기 고장")\n' > "$here/cases/zz-selftest-crash/check.py"
d="$vf/crashcheck"; mkdir -p "$d"; : > "$d/verdicts"
FAKE_DIR=$d EVALS_RESULTS=$d/r PATH="$vf/bin:$PATH" bash "$here/run.sh" zz-selftest-crash "$REF" claude > "$d/out" 2>&1; meta=$(ls "$d"/r/*.meta.json | head -1)
rm -rf "$here/cases/zz-selftest-crash"
grep -q 'check=UNVERIFIED' "$d/out" && [ "$(mget check_unverified)" = True ] && ok "판정 검사 오류는 실패가 아니라 미확인" || ng "판정 검사 오류: $(cat "$d/out")"
# Codex 검증 분기: 임시 홈을 지운 뒤에도 검증자의 실패 종료 코드가 남는다
cat > "$vf/bin/codex" <<'FAKE'
#!/bin/sh
[ "$1" = --version ] && { echo fake 0; exit 0; }
for a in "$@"; do case "$a" in *"당신은 별도 검증자다"*) echo '{"type": "item.completed", "item": {"type": "agent_message", "text": ""}}'; exit 9;; esac; done
echo '{"type": "thread.started", "thread_id": "fake-thread"}'; echo '{"type": "item.completed", "item": {"type": "agent_message", "text": "IMPL"}}'; exit 0
FAKE
chmod +x "$vf/bin/codex"; d="$vf/codex"; mkdir -p "$d"
EVALS_VERIFY=1 EVALS_RESULTS=$d/r PATH="$vf/bin:$PATH" bash "$here/run.sh" weight-disposable "$REF" codex > "$d/out" 2>&1; meta=$(ls "$d"/r/*.meta.json | head -1)
[ "$(mget verifier)" = unverified ] && [ "$(mget verifier_exit_code)" = 9 ] && ok "검증(Codex): 검증자 종료 코드 9 가 정리 뒤에도 보존" || ng "Codex 검증 종료 코드: $(mget verifier) vrc=$(mget verifier_exit_code)"
grep -q '"judge_version": "[0-9a-f]\{12\}"' "$meta" && grep -q '"stage": "original-input"' "$meta" && ok "meta 에 판정기 지문·단계가 남음" || ng "meta 판정기 지문·단계"
rm -rf "${vf:?}"
# 승인 관문 훅(모델 없음): 승인 판별·턴마다 닫힘·수정 도구 차단·셸 미차단·턴 끝 변경 알림·오류 시 막음
python3 -I "$here/gatetest.py" > "${TMPDIR:-/tmp}/gatetest.$$" 2>&1 && ok "승인 관문 시험 $(tail -1 "${TMPDIR:-/tmp}/gatetest.$$")" || { ng "승인 관문 시험"; grep -v '^ok' "${TMPDIR:-/tmp}/gatetest.$$"; }
rm -f "${TMPDIR:-/tmp}/gatetest.$$"
# 일반 설치 흐름(모델 없음): 실제 install.sh 설치본의 관문 훅·독립 검증 실행기를 가짜 하네스로 호출(반환·교정·재검증·한도·미확인·대기)
python3 -I "$here/flowtest.py" > "${TMPDIR:-/tmp}/flowtest.$$" 2>&1 && ok "일반 설치 흐름 시험 $(tail -1 "${TMPDIR:-/tmp}/flowtest.$$")" || { ng "일반 설치 흐름 시험"; grep -v '^ok' "${TMPDIR:-/tmp}/flowtest.$$"; }
rm -f "${TMPDIR:-/tmp}/flowtest.$$"
# 표준 쓰기 경계(모델 없음): 실제 codex sandbox -P :workspace 안에서 task·status·verify 가 .git 을 쓰지 않고 동작하는지.
# codex 가 없는 환경은 미실행으로 따로 적고 통과로 세지 않는다(종료 3).
python3 -I "$here/sandboxtest.py" > "${TMPDIR:-/tmp}/sandboxtest.$$" 2>&1; rc=$?
case $rc in
  0) ok "표준 쓰기 경계 시험 $(tail -1 "${TMPDIR:-/tmp}/sandboxtest.$$")" ;;
  3) printf 'SKIP %s\n' "$(tail -1 "${TMPDIR:-/tmp}/sandboxtest.$$")"; unrun=1 ;;
  *) ng "표준 쓰기 경계 시험"; grep -v '^ok' "${TMPDIR:-/tmp}/sandboxtest.$$" ;;
esac
rm -f "${TMPDIR:-/tmp}/sandboxtest.$$"
printf '%d passed, %d failed%s\n' "$pass" "$failed" "${unrun:+, 1 미실행(표준 쓰기 경계 시험)}"
[ "$failed" -eq 0 ]
