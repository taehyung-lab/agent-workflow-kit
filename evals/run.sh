#!/usr/bin/env bash
# 키트 문장의 행동 효과를 새 세션으로 잰다.
# 사례 하나를, 지정한 키트 커밋을 설치한 격리 프로젝트에서 Claude·Codex 새 세션에 주고
# 원시 기록·메타데이터·판정을 evals/results/ 아래에 남긴다. 답이나 예상 결과는 세션에 주지 않는다.
#
# 사용: bash evals/run.sh <사례> <키트 커밋·태그> <claude|codex> [반복 수]
#   예: bash evals/run.sh weight-accounting v1.0.0 claude 2
#       bash evals/run.sh weight-accounting HEAD codex
# 여러 턴 사례는 prompt2.txt … 를 두면 같은 세션을 이어 가며 차례로 보낸다.
# 결과 요약: python3 -I evals/report.py evals/results
# EVALS_VERIFY=1 이면 모든 턴 뒤에 실행기가 별도 검증 세션(같은 하네스의 새 세션)을 판정 대상의 복사본에서 띄운다.
# 검증 라운드는 설치되는 독립 검증 실행기(.agents/skills/wf-verify/verify.py, 일반 작업도 같은 것을 쓴다)가 맡는다.
# 검증자는 사용자 원문 그대로(승인 턴 포함)·승인 원문이 가리키는 계획(승인 바로 앞 답)·승인 때의 작업 지도 `## 기준`·필수 조건·대상 버전·작업 시작부터의 변경(diff)·실행 방법만 받는다.
# 구현자의 답·지도의 증거(자기평가)는 넘기지 않는다. 판정은 정해진 결과 형식(JSON)으로만 읽는다:
#   ok → 완료, returned → 구현자에게 돌려보내고 새 버전을 다시 판정(EVALS_VERIFY_ROUNDS 번까지, 기본 2), 그 밖(빈 답·형식 오류·
#   조건 누락·OK 인데 미충족)·검증자 하네스 오류·검증자가 추적 파일을 바꿈 → 미확인. 한도에 닿으면 미완료. 미확인·미완료는 완료가 아니다.
# EVALS_LANG=<언어> 는 사례의 setup.sh 에 넘겨 같은 사례를 다른 제품 언어로 만든다(사례가 지원할 때). meta 의 lang 에 남는다.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
kit=$(cd -- "$here/.." && pwd -P)
fail() { printf 'evals: %s\n' "$*" >&2; exit 2; }
[ "$#" -ge 3 ] || fail '사용: bash evals/run.sh <사례> <키트 커밋·태그> <claude|codex> [반복 수]'
case_name=$1 ref=$2 harness=$3 times=${4:-1}
case_dir="$here/cases/$case_name"
[ -f "$case_dir/prompt.txt" ] && [ -f "$case_dir/check.py" ] || fail "사례가 없거나 prompt.txt·check.py 가 빠졌다: $case_dir"
commit=$(git -C "$kit" rev-parse --verify -q "$ref^{commit}") || fail "키트에 없는 커밋·태그: $ref"
case "$harness" in claude|codex) command -v "$harness" >/dev/null || fail "$harness 명령이 없다";; *) fail "하네스는 claude 또는 codex";; esac

# 비교가 같은 조건인지 판단할 수 있게, 세션에 함께 들어오는 전역 지침의 지문을 남긴다(내용은 남기지 않는다).
fingerprint() { [ -f "$1" ] && shasum -a 256 "$1" | cut -c1-12 || echo none; }
# 전역 스킬은 폴더 전체의 SKILL.md 내용으로 지문을 만든다(스킬이 하나 바뀌어도 지문이 달라진다).
skills_fingerprint() { find -L "$HOME/.agents/skills" "$HOME/.claude/skills" -name SKILL.md 2>/dev/null | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-12; }
out_root=${EVALS_RESULTS:-"$here/results/$(date +%Y%m%d)"}
# 이후 턴은 프로젝트 폴더로 옮겨 실행하므로 결과 폴더는 절대 경로로 바꿔 둔다(상대 경로면 2턴 기록을 쓰지 못한다).
mkdir -p "$out_root" && out_root=$(cd -- "$out_root" && pwd -P)
status=0
for i in $(seq 1 "$times"); do
  work=$(mktemp -d)
  # 지정한 커밋의 키트를 깨끗한 checkout 으로 만들어 install.sh 로 설치한다(설치기가 미커밋 키트를 거절하므로).
  git clone -q "$kit" "$work/kit" && git -C "$work/kit" checkout -q "$commit" || fail "키트 checkout 실패: $commit"
  mkdir "$work/project" && (cd "$work/project" && git init -q && printf '# 샘플\n' > README.md \
    && { [ ! -f "$case_dir/setup.sh" ] || EVALS_LANG=${EVALS_LANG:-} bash "$case_dir/setup.sh"; } \
    && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm fixture) || fail "사례 준비 실패"
  bash "$work/kit/install.sh" "$work/project" >/dev/null 2>&1 || fail "키트 설치 실패: $commit"
  (cd "$work/project" && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm kit)
  # 설치 뒤 준비(선택): 설치된 상태를 바꿔야 하는 사례(예: 키트 본문을 읽을 수 없게, 다른 저장소를 옆에 두기)가 쓴다.
  # 설치 커밋 뒤에 실행하므로 그 변경은 세션이 보는 작업 트리에만 남는다. EVALS_KIT 는 설치에 쓴 키트 checkout 이다.
  [ ! -f "$case_dir/after-install.sh" ] || (cd "$work/project" && EVALS_KIT="$work/kit" bash "$case_dir/after-install.sh") \
    || fail "설치 뒤 준비 실패: $case_dir/after-install.sh"

  name="$case_name${EVALS_LANG:+-$EVALS_LANG}-$(printf %.7s "$commit")-$harness-$i"
  out="$out_root/$name"
  # 사례의 턴: prompt.txt 가 첫 턴, prompt2.txt·prompt3.txt … 가 같은 세션을 이어 가는 다음 턴이다.
  # 턴마다 원시 기록을 .tN.jsonl 로 남기고, 판정용 .jsonl 은 모든 턴을 순서대로 이은 것이다(마지막 답 = 마지막 턴의 답).
  turns=("$case_dir/prompt.txt")
  for n in 2 3 4 5 6 7 8 9; do [ ! -f "$case_dir/prompt$n.txt" ] || turns+=("$case_dir/prompt$n.txt"); done
  # EVALS_APPROVE=1 이면 사례의 approve.txt(사용자 승인 턴)를 마지막 턴으로 더한다. 원래 입력과 승인 추가 입력은 meta 의 input 으로 구분된다.
  input=original
  if [ "${EVALS_APPROVE:-0}" = 1 ] && [ -f "$case_dir/approve.txt" ]; then turns+=("$case_dir/approve.txt"); input=with-approval; fi
  start=$(date +%s); rc=0; sid=""; : > "$out.jsonl"; : > "$out.err"
  # Codex 는 전역 지침을 CODEX_HOME 에서 읽는다. 실제 설정을 복사한 임시 홈을 쓰고, 세션을 이어 가도록 모든 턴이 끝날 때까지 둔다.
  # EVALS_CODEX_NETWORK=1 이면 Codex 작업 공간에 네트워크를 허용한다(세션 안에서 다른 세션을 띄우는 후보를 시험할 때).
  net=(); [ "${EVALS_CODEX_NETWORK:-0}" != 1 ] || net=(-c sandbox_workspace_write.network_access=true)
  # 승인 관문 훅은 설치기가 프로젝트 설정(.claude/settings.json, .codex/hooks.json)에 등록한 그대로 쓴다(그 커밋의 키트에 관문이 있을 때).
  # Codex 는 프로젝트 훅을 사용자가 한 번 신뢰해야 실행하므로, 그 신뢰를 대신해 --dangerously-bypass-hook-trust 를 준다.
  # 훅 판단은 결과 옆 .hook.log 에 남긴다. 사용자 전역 설정은 건드리지 않는다.
  limit=1200
  export AWK_GATE_LOG="$out.hook.log"
  gate=false; ! grep -q approval-gate.py "$work/project/.claude/settings.json" 2>/dev/null || gate=true
  [ "$harness" != codex ] || net+=(--dangerously-bypass-hook-trust)
  if [ "$harness" = codex ]; then ch=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$ch/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$ch/"; fi
  t=0; sent=0
  # 작업 시작 상태(첫 턴 직전). 검증자는 마지막 턴만이 아니라 작업 시작부터의 변경 전체를 받는다.
  mkdir "$work/before-task" && (cd "$work/project" && tar cf - --exclude=./.git --exclude=./.agents . 2>/dev/null) | tar xf - -C "$work/before-task"
  for turn in "${turns[@]}"; do
    t=$((t + 1)); sent=$((sent + 1)); prompt=$(cat "$turn"); tout="$out.t$t"
    # 턴마다 직전 작업 파일(설치된 키트·git 제외)을 덮어 남긴다. 끝나면 "마지막으로 실행한 턴의 직전 상태"가 되어,
    # 판정은 그 턴에서 무엇을 바꿨나를 보고, 하네스가 중간에 실패해도 실패한 턴의 직전 상태가 남는다.
    rm -rf "${work:?}/before-last"; mkdir "$work/before-last" \
      && (cd "$work/project" && tar cf - --exclude=./.git --exclude=./.agents . 2>/dev/null) | tar xf - -C "$work/before-last"
    if [ "$harness" = claude ]; then
      resume=(); [ "$t" -eq 1 ] || resume=(--resume "$sid")
      (cd "$work/project" && perl -e 'alarm shift; exec @ARGV' "$limit" claude -p "$prompt" ${resume[@]+"${resume[@]}"} --output-format stream-json --verbose \
        --dangerously-skip-permissions --max-turns 30 > "$tout.jsonl" 2> "$tout.err")
    elif [ "$t" -eq 1 ]; then
      CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' "$limit" codex exec --json --skip-git-repo-check --sandbox workspace-write ${net[@]+"${net[@]}"} \
        -C "$work/project" "$prompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null
    else
      (cd "$work/project" && CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' "$limit" codex exec resume --json --skip-git-repo-check \
        -c sandbox_mode='"workspace-write"' ${net[@]+"${net[@]}"} "$sid" "$prompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null)
    fi
    trc=$?
    cat "$tout.jsonl" >> "$out.jsonl"; cat "$tout.err" >> "$out.err"
    # 다음 턴이 이어 갈 세션 id: Claude 는 session_id, Codex 는 thread_id 를 첫 턴 기록에서 읽는다.
    [ -n "$sid" ] || sid=$(python3 -I -c 'import json,sys
for l in open(sys.argv[1], encoding="utf-8"):
    try: e = json.loads(l)
    except ValueError: continue
    v = e.get("session_id") or e.get("thread_id")
    if v: print(v); break' "$tout.jsonl")
    if [ "$trc" -ne 0 ]; then rc=$trc; break; fi
    if [ "${#turns[@]}" -gt 1 ] && [ -z "$sid" ]; then rc=3; echo "세션 id 를 찾지 못해 다음 턴을 이어 갈 수 없다" >> "$out.err"; break; fi
  done
  verify_state=off; verify_reason=""; verify_rounds=0; verifier_rc=""; vjson='{}'; baseline_changed=false
  if [ "${EVALS_VERIFY:-0}" = 1 ] && [ "$rc" -eq 0 ]; then
    max_rounds=${EVALS_VERIFY_ROUNDS:-2}
    # 필수 조건: 사례의 verify-conditions.txt 와 작업 지도 `## 기준` 표의 ID(검증 실행기가 둘에서 모은다).
    # 검증 기준은 사용자가 승인한 지도 기준으로 고정한다. 승인 입력이면 승인 턴 직전 상태(before-last)의 지도, 아니면 사용자 턴이 끝난 때의 지도.
    # 재검증 때 구현자가 고친 지금의 지도를 새 기준으로 읽지 않는다. 바뀌었으면 그 사실만 검증자에게 알린다(승인받지 않은 기준 변경).
    if [ "$input" = with-approval ]; then baseline=$(python3 -I "$here/verdict.py" baseline "$work/before-last")
    else baseline=$(python3 -I "$here/verdict.py" baseline "$work/project"); fi
    baseline_changed=false
    # 승인 원문이 가리키는 계획: 승인 입력이면 승인 턴 바로 앞 턴의 구현자 답(사용자가 보고 승인한 추천안)을 넘긴다.
    # 승인 뒤 구현 턴의 답(자기평가)은 넘기지 않는다. 추출하지 못하면 성공처럼 비워 두지 않고 그 사실을 적는다.
    approved_plan=""
    if [ "$input" = with-approval ]; then
      approved_plan=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from transcript import read; print(read(sys.argv[2])[1])' "$here" "$out.t$(( ${#turns[@]} - 1 )).jsonl" 2>/dev/null)
      [ -n "$approved_plan" ] || approved_plan="(추출 실패: 승인 직전 답을 기록에서 읽지 못했다. 승인 원문이 가리키는 계획에 기대는 조건은 미확인으로 둔다)"
    fi
    # 검증 실행기는 일반 설치와 같은 것(설치된 키트의 .agents/skills/wf-verify/verify.py)을 쓴다. 고정 복사본·검증자 입력·결과 형식 판정·
    # 재검증 한도를 그 실행기가 맡고, 실행기는 반환 턴만 보낸다. 그 커밋의 키트에 실행기가 없으면 이 저장소의 것을 쓴다(meta.verifier_tool).
    # 하네스가 실행기 밖에서 돌기 때문에 관문 기록 대신 사용자 원문·계획·기준·작업 시작 상태를 파일로 넘긴다.
    verifier_tool="$work/project/.agents/skills/wf-verify/verify.py"; [ -f "$verifier_tool" ] || verifier_tool="$kit/.agents/skills/wf-verify/verify.py"
    reqs=(); for turn in "${turns[@]}"; do reqs+=(--request "$turn"); done
    vargs=(--criteria "$work/criteria.txt" --base-dir "$work/before-task" --state "$work/verify-state.json")
    printf '%s' "$baseline" > "$work/criteria.txt"
    [ -z "$approved_plan" ] || { printf '%s' "$approved_plan" > "$work/approved-plan.txt"; vargs+=(--plan "$work/approved-plan.txt"); }
    [ ! -f "$case_dir/verify-conditions.txt" ] || vargs+=(--conditions "$case_dir/verify-conditions.txt")
    vget() { printf '%s' "$vjson" | python3 -I -c 'import json,sys
v = json.load(sys.stdin).get(sys.argv[1])
print("" if v is None else str(v).lower() if isinstance(v, bool) else v)' "$1" 2>/dev/null; }
    while :; do
      verify_rounds=$((verify_rounds + 1))
      vlog="$out.verify$verify_rounds.jsonl"; vh=""
      if [ "$harness" = codex ]; then vh=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$vh/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$vh/"; fi
      vjson=$(cd "$work/project" && env ${vh:+CODEX_HOME=$vh} python3 -I "$verifier_tool" --harness "$harness" --rounds "$max_rounds" --log "$vlog" \
        "${reqs[@]}" "${vargs[@]}" 2>> "$out.err" | tail -1)
      [ -z "$vh" ] || rm -rf "${vh:?}"
      [ ! -f "$vlog" ] || cp "$vlog" "$out.verify.jsonl"  # 마지막 판정 기록(이전 판정은 .verifyN.jsonl 로 남는다)
      vstate=$(vget state); verify_reason=$(vget reason); vrc=$(vget verifier_exit_code)
      [ "$(vget baseline_changed_after_approval)" != true ] || baseline_changed=true
      [ -z "$vrc" ] || [ "$vrc" = 0 ] || verifier_rc=$vrc
      if [ -z "$vstate" ]; then verify_state=unverified; verify_reason="검증 실행기가 결과를 내지 못했다"; vjson='{}'; break; fi
      case "$vstate" in ok|unverified|incomplete) verify_state=$vstate; break;; esac
      # 돌려보냄: 구현자 세션에 반환 턴을 보낸다. 반환 턴은 사용자 턴이 아니므로 before-last 를 덮지 않는다.
      t=$((t + 1)); tout="$out.t$t"
      vfinal=$(vget final)
      rprompt=$(printf '별도 검증자가 다음 사유로 돌려보냈습니다. 검증자의 판단을 그대로 따르지 말고, 사용자 원문과 작업 기준에 비추어 판단해 다시 답하세요.\n\n%s' "$vfinal")
      if [ "$harness" = claude ]; then
        # 반환 턴은 사용자 메시지가 아니다: 관문에 발신 구분을 넘겨 글 속 "승인합니다"·"취소합니다"로 승인 상태가 바뀌지 않게 한다.
        (cd "$work/project" && AWK_GATE_PROMPT_FROM=runner perl -e 'alarm shift; exec @ARGV' 900 claude -p "$rprompt" --resume "$sid" --output-format stream-json --verbose \
          --dangerously-skip-permissions --max-turns 30 > "$tout.jsonl" 2> "$tout.err")
      else
        (cd "$work/project" && AWK_GATE_PROMPT_FROM=runner CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' "$limit" codex exec resume --json --skip-git-repo-check \
          -c sandbox_mode='"workspace-write"' "$sid" "$rprompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null)
      fi
      trc=$?; cat "$tout.jsonl" >> "$out.jsonl"; cat "$tout.err" >> "$out.err"
      if [ "$trc" -ne 0 ]; then rc=$trc; verify_state=incomplete; verify_reason="교정 턴의 구현자 하네스 종료 코드 $trc"; break; fi
    done
  fi
  # 끝난 때 관문이 사용자 답을 기다리는지(승인 전이거나 사용자 철회·기준 변경으로 닫힘): 구현 실패·검증 실패와 구별해 센다.
  # 관문 기록이 없으면(관문 없는 커밋·훅이 돌지 않음) 알 수 없으므로 대기로 세지 않는다.
  gate_waiting=$( [ -z "$sid" ] || (cd "$work/project" && python3 -I .agents/skills/wf-design/approval-gate.py status --session "$sid" < /dev/null 2>/dev/null) \
    | python3 -I -c 'import json,sys
try: d = json.load(sys.stdin)
except ValueError: d = {}
print("true" if d.get("task") and d.get("waiting") else "false")' 2>/dev/null)
    # Codex 의 exec 기록(--json)에는 하위 에이전트 생성(spawn_agent)이 남지 않는다. 관찰용으로 이 세션의 원본 기록(rollout)을 남긴다.
  [ "$harness" != codex ] || { [ -z "$sid" ] || find "$ch/sessions" -name "rollout-*$sid.jsonl" -exec cat {} + > "$out.rollout.jsonl" 2>/dev/null; rm -rf "${ch:?}"; }
  seconds=$(( $(date +%s) - start ))
  observed=$(python3 -I "$here/observe.py" "$out.jsonl" $( [ ! -f "$case_dir/observe.txt" ] || cat "$case_dir/observe.txt") 2>/dev/null || echo '{}')
  # 판정 검사는 0=통과, 1=실패, 2=검토 필요(원문을 사람이 판정)를 돌려준다. 3=미확인은 실행기가 정한다:
  # 하네스가 모델 용량·요청 한도 같은 외부 장애로 끝났으면 판정하지 않고 통과율 분모에서 뺀다(시도·사유는 남긴다).
  # 외부 장애는 오류 사건(Codex error·turn.failed, Claude 오류 결과)과 표준 오류에서만 찾는다(일반 답 속 낱말은 보지 않는다).
  pat='at capacity|rate.?limit|too many requests|overloaded|HTTP 429|stream disconnected|service unavailable'
  external=$( { LC_ALL=C grep -a -E '"type": ?"(error|turn\.failed)"|"is_error": ?true' "$out.jsonl"; cat "$out.err"; } 2>/dev/null | LC_ALL=C grep -a -o -m1 -iE "$pat" | head -1)
  if [ "$rc" -ne 0 ] && [ -n "$external" ]; then
    # 장애 전에 제품 파일을 바꿨으면(최종 파일 차이, 또는 바꿨다가 되돌린 편집 기록) 위반일 수 있으므로
    # 지우지 않고 사람이 원시 기록으로 판정한다.
    edited=$(cd "$work/project" && { [ ! -d "$work/before-last" ] || diff -rq --exclude=.git --exclude=.agents --exclude=.claude --exclude=.codex --exclude=work --exclude=__pycache__ "$work/before-last" . 2>/dev/null; } | head -1)
    [ -n "$edited" ] || edited=$(printf '%s' "$observed" | python3 -I -c 'import json,sys; e=json.load(sys.stdin).get("last_turn_edits") or []; print("편집 기록: " + ", ".join(e) if e else "")' 2>/dev/null)
    if [ -n "$edited" ]; then verdict="REVIEW 외부 장애($external)로 끝났지만 그 전에 제품 파일이 바뀌었다: $edited"; check_rc=2
    else verdict="UNVERIFIED 하네스가 외부 장애($external)로 종료 코드 $rc 로 끝나 판정하지 않았다"; check_rc=3; fi
  elif [ "$rc" -ne 0 ]; then
    verdict="FAIL 하네스가 종료 코드 $rc 로 끝나 판정하지 않았다"; check_rc=1
  else
    verdict=$(EVALS_INPUT=$input EVALS_GATE=$gate EVALS_BEFORE_LAST_TURN="$work/before-last" python3 -I "$case_dir/check.py" "$work/project" "$out.jsonl" 2>&1); check_rc=$?
    # 판정 검사 자체가 오류로 끝나면(예외 등) 실패가 아니라 미확인이다. 판정 검사는 결과 줄을 PASS·FAIL·REVIEW 로 시작한다.
    case "$check_rc:$verdict" in 0:PASS*|1:FAIL*|2:REVIEW*) ;; *) verdict="UNVERIFIED 판정 검사 오류(종료 코드 $check_rc): $(printf '%s' "$verdict" | tail -1)"; check_rc=3;; esac
  fi
  # 사례가 AGENTS.md 를 읽을 수 없게 만들었으면 바이트는 설치에 쓴 키트 checkout 에서 잰다.
  agents_bytes=$( { wc -c < "$work/project/AGENTS.md" || wc -c < "$work/kit/AGENTS.md"; } 2>/dev/null | tr -d ' ')
  # 값은 환경 변수로 넘겨 따옴표·줄바꿈이 섞인 판정 문구도 그대로 기록한다.
  E_HERE=$here E_CASE=$case_name E_REF=$ref E_COMMIT=$commit E_HARNESS=$harness E_RUN=$i E_RC=$rc E_SEC=$seconds \
  E_VERSION=$("$harness" --version 2>/dev/null | head -1) E_BYTES=$agents_bytes E_CHECK_RC=$check_rc E_VERDICT=$verdict \
  E_G1=$(fingerprint ~/.claude/CLAUDE.md) E_G2=$(fingerprint ~/.agents/USER.md) E_G3=$(fingerprint ~/.codex/AGENTS.md) E_G4=$(skills_fingerprint) E_OBS=$observed E_VSTATE=$verify_state E_BCHANGED=${baseline_changed:-false} E_VREASON=$verify_reason E_VROUNDS=$verify_rounds E_VRC=$verifier_rc E_VJSON=$vjson E_LANG=${EVALS_LANG:-} E_JUDGE=$(cd "$here" && shasum -a 256 "cases/$case_name/check.py" judge.py observe.py transcript.py verdict.py ../.agents/skills/wf-verify/verify.py 2>/dev/null | shasum -a 256 | cut -c1-12) E_GATE=$gate E_WAITING=${gate_waiting:-false} E_VTOOL=${verifier_tool:-} E_INPUT=$input E_TURNS=$sent E_PLANNED=${#turns[@]} E_WAIT=$(python3 -I -c 'import json,sys
n = seen = 0
try:
    for line in open(sys.argv[1], encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "prompt":
            seen += 1  # 사용자 턴만 센다. 그 뒤의 prompt 는 실행기가 보낸 검증 반환 턴이다.
            n += seen <= int(sys.argv[2]) and e.get("approved") is False
except OSError:
    pass
print(n)' "$out.hook.log" "$sent") \
  python3 -I -c '
import json, os, sys
e = os.environ
sys.path.insert(0, e["E_HERE"])
from verdict import completion
json.dump({"case": e["E_CASE"], "kit_ref": e["E_REF"], "kit_commit": e["E_COMMIT"], "harness": e["E_HARNESS"],
  "run": int(e["E_RUN"]), "harness_version": e["E_VERSION"], "exit_code": int(e["E_RC"]), "seconds": int(e["E_SEC"]),
  "agents_md_bytes": int(e["E_BYTES"]), "check_passed": e["E_CHECK_RC"] == "0", "check_needs_review": e["E_CHECK_RC"] == "2", "check_unverified": e["E_CHECK_RC"] == "3", "approval_gate": e["E_GATE"] == "true", "input": e["E_INPUT"], "user_turns": int(e["E_TURNS"]), "planned_turns": int(e["E_PLANNED"]), "unapproved_turns": int(e["E_WAIT"] or 0), "check_output": e["E_VERDICT"], "observed": json.loads(e["E_OBS"] or "{}"), "verifier": e["E_VSTATE"], "verify_reason": e["E_VREASON"], "verify_rounds": int(e["E_VROUNDS"]),
  "verifier_exit_code": int(e["E_VRC"]) if e["E_VRC"] else None, "out_of_scope": json.loads(e["E_VJSON"] or "{}").get("out_of_scope", []),
  "verifier_conditions": json.loads(e["E_VJSON"] or "{}").get("conditions", []), "lang": e["E_LANG"] or None, "judge_version": e["E_JUDGE"],
  # 단계 판정(사례 check.py)과 전체 완료(독립 검증으로 닫힘)를 따로 센다. 승인 대기 단계의 통과는 구현 완료가 아니다.
  "stage": "after-approval" if e["E_INPUT"] == "with-approval" else "original-input",
  # 검증자가 OK 여도 사례의 결정적 행동 검사(check.py)가 실패·미확인이면 완료로 세지 않는다(검증자가 놓친 것으로 따로 남긴다).
  # 판정 규칙은 verdict.completion 하나다(rejudge.py 도 같은 함수로 다시 계산한다).
  # 사용자 답 대기(gate_waiting)는 구현 실패·검증 실패·미확인과 따로 센다(완료가 아니다).
  "completion": completion(e["E_VSTATE"], {"0": "PASS", "1": "FAIL", "2": "REVIEW"}.get(e["E_CHECK_RC"], "UNVERIFIED"), e["E_WAITING"] == "true"),
  "gate_waiting": e["E_WAITING"] == "true", "verifier_tool": e["E_VTOOL"] or None,
  "baseline_changed_after_approval": e["E_BCHANGED"] == "true",
  "global_instructions": {"~/.claude/CLAUDE.md": e["E_G1"], "~/.agents/USER.md": e["E_G2"], "~/.codex/AGENTS.md": e["E_G3"], "global skills": e["E_G4"]}},
  open(sys.argv[1], "w"), ensure_ascii=False, indent=1)' "$out.meta.json"
  shown=FAIL; [ "$check_rc" -ne 0 ] || shown=PASS; [ "$check_rc" -ne 2 ] || shown=REVIEW; [ "$check_rc" -ne 3 ] || shown=UNVERIFIED
  printf '%s exit=%s check=%s %s\n' "$name" "$rc" "$shown" "$(printf '%s' "$verdict" | head -1)"
  # 판정 검사를 고친 뒤 다시 판정할 수 있게, 끝난 프로젝트의 작업 파일(설치된 키트·git 제외)을 남긴다.
  # 같은 이름으로 다시 실행해도 지난 실행의 파일이 섞이지 않게 먼저 비운다.
  rm -rf "${out:?}.files" "${out:?}.before-last"
  mkdir -p "$out.files" && (cd "$work/project" && tar cf - --exclude=./.git --exclude=./.agents . 2>/dev/null) | tar xf - -C "$out.files"
  # 마지막 턴 직전 상태도 남긴다. 다시 판정할 때 EVALS_BEFORE_LAST_TURN 으로 넘긴다.
  [ ! -d "$work/before-last" ] || cp -R "$work/before-last" "$out.before-last"
  # 하네스가 실패했으면 판정과 관계없이, 처음 실패한 실행의 종료 코드를 그대로 돌려준다.
  [ "$rc" -eq 0 ] || [ "$status" -ne 0 ] || status=$rc
  rm -rf "${work:?}"
done
exit "$status"
