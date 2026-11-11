#!/usr/bin/env bash
# 키트 문장의 행동 효과를 새 세션으로 잰다.
# 사례 하나를, 지정한 키트 커밋을 설치한 격리 프로젝트에서 Claude·Codex 새 세션에 주고
# 원시 기록·메타데이터·판정을 evals/results/ 아래에 남긴다. 답이나 예상 결과는 세션에 주지 않는다.
#
# 사용: bash evals/run.sh <사례> <키트 커밋·태그> <claude|codex> [반복 수]
#   예: bash evals/run.sh weight-accounting v1.0.0 claude 2
#       bash evals/run.sh question-order 7c39b22..HEAD codex 10   (두 커밋 비교, 끝에 report.py --compare)
#       bash evals/run.sh weight-accounting HEAD codex
# 여러 턴 사례는 prompt2.txt … 를 두면 같은 세션을 이어 가며 차례로 보낸다.
# 결과 요약: python3 -I evals/report.py evals/results
# EVALS_VERIFY=1 이면 모든 턴 뒤에 실행기가 별도 검증 세션(같은 하네스의 새 세션)을 판정 대상의 복사본에서 띄운다.
# 검증 라운드는 설치되는 검토 도구(.agents/skills/wf-verify/verify.py)를 사용자와 같은 옵션(--request·--map·--base·--conditions·--rounds)으로 부른다.
# 검증자는 사용자 원문 그대로(모든 사용자 턴)·작업 지도 `## 기준`·필수 조건·대상 버전·작업 시작부터의 변경(diff)·실행 방법만 받는다.
# 구현자의 답·지도의 증거(자기평가)는 넘기지 않는다. 판정은 정해진 결과 형식(JSON)으로만 읽는다:
#   ok → 완료, returned → 구현자에게 돌려보내고 새 버전을 다시 판정(EVALS_VERIFY_ROUNDS 번까지, 기본 2), 그 밖(빈 답·형식 오류·
#   조건 누락·OK 인데 미충족)·검증자 하네스 오류·검증자가 추적 파일을 바꿈 → 미확인. 한도에 닿으면 미완료. 미확인·미완료는 완료가 아니다.
#   이 루프는 지금 도구의 옵션을 쓴다. v3.5 이하 커밋의 검토 비교는 그 태그를 꺼내 그 태그의 evals 로 돌린다.
# EVALS_LANG=<언어> 는 사례의 setup.sh 에 넘겨 같은 사례를 다른 제품 언어로 만든다(사례가 지원할 때). meta 의 lang 에 남는다.
# EVALS_CLAUDE_SETTINGS=<JSON 파일> 은 설치 뒤 프로젝트 .claude/settings.json 에 그 내용을 합친다(맨 위 키 단위, enabledPlugins 는 항목 단위).
#   실제 사용 조합 재현용 예: evals/profiles/real-plugins.json(superpowers 를 프로젝트에서 끄고, 사용자 설정의 나머지 플러그인은 그대로).
#   Claude 는 늘 사용자 홈(~/.claude)의 전역 지침·플러그인·훅을 함께 읽는다. 실제로 켜진 플러그인 목록의 지문은 meta 의 global_instructions.plugins 에 남는다.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
kit=$(cd -- "$here/.." && pwd -P)
fail() { printf 'evals: %s\n' "$*" >&2; exit 2; }
[ "$#" -ge 3 ] || fail '사용: bash evals/run.sh <사례> <키트 커밋·태그 | 기준..대상> <claude|codex> [반복 수]'
case_name=$1 ref=$2 harness=$3 times=${4:-1}
# 비교 실행: <기준>..<대상> 이면 같은 사례·하네스로 두 커밋을 번갈아(기준 1회, 대상 1회, …) 돌린다(시간대·모델 상태의 차이가 한쪽에 몰리지 않게).
# 끝나면 양쪽 원시 기록을 지금 판정기로 다시 판정(rejudge)한 뒤 report.py --compare 로 전후를 보여 준다(판정기가 달라 비교 불가가 되지 않게).
if [[ "$ref" == *..* ]]; then
  out=${EVALS_RESULTS:-"$here/results/$(date +%Y%m%d)"}; rc=0
  for i in $(seq 1 "$times"); do
    for side in "${ref%%..*}" "${ref##*..}"; do EVALS_RESULTS=$out EVALS_RUN_OFFSET=$((i - 1)) bash "$0" "$case_name" "$side" "$harness" 1 || rc=$?; done
  done
  python3 -I "$here/rejudge.py" "$out" > /dev/null || rc=$?
  python3 -I "$here/report.py" --compare "${ref%%..*}" "${ref##*..}" "$out"; exit "$rc"
fi
case_dir=$(python3 -I "$here/caseinfo.py" path "$case_name") || fail "사례 위치를 정하지 못했다: $case_name"  # cases 에 없으면 holdout(숨겨 둔 평가 사례)
[ -f "$case_dir/prompt.txt" ] && [ -f "$case_dir/check.py" ] || fail "사례가 없거나 prompt.txt·check.py 가 빠졌다: $case_dir"
# 판정기 지문은 재판정(rejudge.py)과 같은 함수로 만든다. 판정 파일이 빠졌으면 모델을 돌리기 전에 멈춘다.
python3 -I "$here/caseinfo.py" version "$case_dir" > /dev/null || fail "판정기 지문을 만들 수 없다(위 파일 누락)"
commit=$(git -C "$kit" rev-parse --verify -q "$ref^{commit}") || fail "키트에 없는 커밋·태그: $ref"
case "$harness" in claude|codex) command -v "$harness" >/dev/null || fail "$harness 명령이 없다";; *) fail "하네스는 claude 또는 codex";; esac

# 비교가 같은 조건인지 판단할 수 있게, 세션에 함께 들어오는 전역 지침의 지문을 남긴다(내용은 남기지 않는다).
fingerprint() { [ -f "$1" ] && shasum -a 256 "$1" | cut -c1-12 || echo none; }
# 전역 스킬은 폴더 전체의 SKILL.md 내용으로 지문을 만든다(스킬이 하나 바뀌어도 지문이 달라진다).
skills_fingerprint() { find -L "$HOME/.agents/skills" "$HOME/.claude/skills" -name SKILL.md 2>/dev/null | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-12; }
# Claude 에서 실제로 켜지는 플러그인 목록(사용자 설정 위에 프로젝트 설정을 덮은 enabledPlugins 중 true)의 지문. 플러그인 조합이 다른 실행끼리 비교하지 않게 한다.
plugins_fingerprint() { python3 -I - "$HOME/.claude/settings.json" "$1/.claude/settings.json" "$1/.claude/settings.local.json" <<'PY' 2>/dev/null || echo none
import hashlib, json, os, sys
on = {}
for f in sys.argv[1:]:
    if os.path.isfile(f):
        on.update(json.load(open(f, encoding="utf-8")).get("enabledPlugins") or {})
print(hashlib.sha256(json.dumps(sorted(k for k, v in on.items() if v)).encode()).hexdigest()[:12])
PY
}
out_root=${EVALS_RESULTS:-"$here/results/$(date +%Y%m%d)"}
# 이후 턴은 프로젝트 폴더로 옮겨 실행하므로 결과 폴더는 절대 경로로 바꿔 둔다(상대 경로면 2턴 기록을 쓰지 못한다).
mkdir -p "$out_root" && out_root=$(cd -- "$out_root" && pwd -P)
status=0
for i in $(seq $((1 + ${EVALS_RUN_OFFSET:-0})) $((times + ${EVALS_RUN_OFFSET:-0}))); do  # 비교 실행은 번호를 이어 받아 결과 이름이 겹치지 않게 한다
  work=$(mktemp -d)
  # 지정한 커밋의 키트를 깨끗한 checkout 으로 만들어 install.sh 로 설치한다(설치기가 미커밋 키트를 거절하므로).
  git clone -q "$kit" "$work/kit" && git -C "$work/kit" checkout -q "$commit" || fail "키트 checkout 실패: $commit"
  mkdir "$work/project" && (cd "$work/project" && git init -q && printf '# 샘플\n' > README.md \
    && { [ ! -f "$case_dir/setup.sh" ] || EVALS_LANG=${EVALS_LANG:-} bash "$case_dir/setup.sh"; } \
    && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm fixture) || fail "사례 준비 실패"
  bash "$work/kit/install.sh" "$work/project" >/dev/null 2>&1 || fail "키트 설치 실패: $commit"
  if [ -n "${EVALS_CLAUDE_SETTINGS:-}" ]; then
    python3 -I - "$EVALS_CLAUDE_SETTINGS" "$work/project/.claude/settings.json" <<'PY' || fail "EVALS_CLAUDE_SETTINGS 를 합치지 못했다: $EVALS_CLAUDE_SETTINGS"
import json, os, sys
add = json.load(open(sys.argv[1], encoding="utf-8"))
cur = json.load(open(sys.argv[2], encoding="utf-8")) if os.path.isfile(sys.argv[2]) else {}
for k, v in add.items():
    cur[k] = {**cur.get(k, {}), **v} if k == "enabledPlugins" and isinstance(v, dict) else v
os.makedirs(os.path.dirname(sys.argv[2]), exist_ok=True)
json.dump(cur, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  fi
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
  # v3.1 부터 키트는 훅을 설치하지 않는다. 승인 관문이 있던 커밋(v3.0 이하)을 비교할 때만 설치기가 등록한 관문 훅이 돌고,
  # 그 판단을 결과 옆 .hook.log 에 남긴다(AWK_GATE_LOG). Codex 는 프로젝트 훅을 사용자가 한 번 신뢰해야 실행하므로,
  # 프로젝트에 .codex/hooks.json 이 있을 때만 그 신뢰를 대신해 --dangerously-bypass-hook-trust 를 준다. 사용자 전역 설정은 건드리지 않는다.
  limit=1200
  export AWK_GATE_LOG="$out.hook.log"
  gate=false; ! grep -q approval-gate.py "$work/project/.claude/settings.json" 2>/dev/null || gate=true
  [ "$harness" != codex ] || [ ! -f "$work/project/.codex/hooks.json" ] || net+=(--dangerously-bypass-hook-trust)
  if [ "$harness" = codex ]; then ch=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$ch/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$ch/"; fi
  # v3.2~ 의 세션 시작 정보 훅(wf-context)은 Codex 가 프로젝트를 신뢰해야(trust_level) 읽힌다. 프로젝트를 신뢰한 사용자를 재현하려고
  # 임시 홈의 config.toml 에만 이 프로젝트 신뢰를 더한다(사용자 전역 설정은 건드리지 않는다). 관문이 있던 v3.0 이하 커밋의 실행 조건은 바꾸지 않는다.
  codex_trusted=false
  if [ "$harness" = codex ] && grep -q 'wf-context/context.py' "$work/project/.codex/hooks.json" 2>/dev/null; then
    for pdir in "$work/project" "$(cd "$work/project" && pwd -P)"; do
      grep -qF "[projects.\"$pdir\"]" "$ch/config.toml" 2>/dev/null || printf '\n[projects."%s"]\ntrust_level = "trusted"\n' "$pdir" >> "$ch/config.toml"
    done
    codex_trusted=true
  fi
  t=0; sent=0
  # 작업 시작 상태(첫 턴 직전)를 커밋 하나로 남긴다(가지·index 는 그대로). 검증자는 마지막 턴만이 아니라 작업 시작부터의 변경 전체를 받는다.
  base_sha=$(python3 -I "$here/verdict.py" snapshot "$work/project" 2>> "$out.err")
  for turn in "${turns[@]}"; do
    t=$((t + 1)); sent=$((sent + 1)); prompt=$(cat "$turn"); tout="$out.t$t"
    # 턴 사이 준비(선택): before-turnN.sh 가 있으면 N 번째 턴을 보내기 전에 프로젝트 폴더에서 실행한다(예: 재개 전에 다른 사람이 파일을 바꿈).
    [ ! -f "$case_dir/before-turn$t.sh" ] || (cd "$work/project" && bash "$case_dir/before-turn$t.sh") >> "$out.err" 2>&1 \
      || { rc=3; echo "턴 사이 준비 실패: before-turn$t.sh" >> "$out.err"; break; }
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
    # 검증 입력 묶기·결과 판정·재검증 한도는 설치된 검토 도구가 맡고, 검토자 세션을 띄우는 일만 평가 실행기(verdict.py session)가 한다.
    # 도구는 사용자와 같은 옵션으로 부른다: 사용자 턴 전부(--request), 작업 시작 커밋(--base), 사례의 필수 조건(--conditions), 지도가 하나면 그 지도(--map, session 이 고른다).
    # 그 커밋의 키트에 도구가 없으면 이 저장소의 것을 쓴다(meta.verifier_tool).
    baseline_changed=false
    verifier_tool="$work/project/.agents/skills/wf-verify/verify.py"; [ -f "$verifier_tool" ] || verifier_tool="$kit/.agents/skills/wf-verify/verify.py"
    reqs=(); for turn in "${turns[@]}"; do reqs+=(--request "$turn"); done
    vargs=(--base "$base_sha")
    [ ! -f "$case_dir/verify-conditions.txt" ] || vargs+=(--conditions "$case_dir/verify-conditions.txt")
    had_work=false; [ ! -e "$work/project/work" ] || had_work=true
    # 도구가 지금 옵션을 모르거나(v3.5 이하 커밋) 작업 시작 상태를 남기지 못했으면 검토를 돌리지 않는다(다른 기준으로 조용히 대신하지 않는다).
    vblock=""; grep -q "^def record" "$verifier_tool" || vblock="이 커밋의 검토 도구는 지금 옵션을 쓰지 않는다. 그 태그의 evals 로 돌린다"
    [ -n "$base_sha" ] || vblock="작업 시작 상태를 커밋으로 남기지 못했다"
    vget() { printf '%s' "$vjson" | python3 -I -c 'import json,sys
v = json.load(sys.stdin).get(sys.argv[1])
print("" if v is None else str(v).lower() if isinstance(v, bool) else v)' "$1" 2>/dev/null; }
    while :; do
      if [ -n "$vblock" ]; then verify_state=unverified; verify_reason=$vblock; break; fi
      # 도구의 회차 기록은 구현자도 쓰는 프로젝트 안에 있어 시도가 새로 시작될 수 있다. 실행기도 한도를 따로 센다.
      if [ "$verify_rounds" -ge "$max_rounds" ]; then verify_state=incomplete; verify_reason="재검증 한도($max_rounds)에 닿았다"; break; fi
      verify_rounds=$((verify_rounds + 1))
      vlog="$out.verify$verify_rounds.jsonl"; vh=""
      if [ "$harness" = codex ]; then vh=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$vh/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$vh/"; fi
      vjson=$(cd "$work/project" && env ${vh:+CODEX_HOME=$vh} python3 -I "$here/verdict.py" session --tool "$verifier_tool" --harness "$harness" \
        --rounds "$max_rounds" --log "$vlog" "${reqs[@]}" "${vargs[@]}" 2>> "$out.err" | tail -1)
      [ -z "$vh" ] || rm -rf "${vh:?}"
      [ ! -f "$vlog" ] || cp "$vlog" "$out.verify.jsonl"  # 마지막 판정 기록(이전 판정은 .verifyN.jsonl 로 남는다)
      vstate=$(vget state); verify_reason=$(vget reason); vrc=$(vget verifier_exit_code)
      [ "$(vget criteria_changed)" != true ] || baseline_changed=true
      [ -z "$vrc" ] || [ "$vrc" = 0 ] || verifier_rc=$vrc
      if [ -z "$vstate" ]; then verify_state=unverified; verify_reason="검증 실행기가 결과를 내지 못했다"; vjson='{}'; break; fi
      case "$vstate" in ok|unverified|incomplete) verify_state=$vstate; break;; esac
      # 돌려보냄: 구현자 세션에 반환 턴을 보낸다. 반환 턴은 사용자 턴이 아니므로 before-last 를 덮지 않는다.
      t=$((t + 1)); tout="$out.t$t"
      vfinal=$(vget final)
      rprompt=$(printf '별도 검증자가 다음 사유로 돌려보냈습니다. 검증자의 판단을 그대로 따르지 말고, 사용자 원문과 작업 기준에 비추어 판단해 다시 답하세요.\n\n%s' "$vfinal")
      if [ "$harness" = claude ]; then
        # 반환 턴은 사용자 메시지가 아니다: 관문이 있던 커밋(v3.0 이하)에 발신 구분을 넘겨 글 속 "승인합니다"로 승인 상태가 바뀌지 않게 한다.
        (cd "$work/project" && AWK_GATE_PROMPT_FROM=runner perl -e 'alarm shift; exec @ARGV' 900 claude -p "$rprompt" --resume "$sid" --output-format stream-json --verbose \
          --dangerously-skip-permissions --max-turns 30 > "$tout.jsonl" 2> "$tout.err")
      else
        (cd "$work/project" && AWK_GATE_PROMPT_FROM=runner CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' "$limit" codex exec resume --json --skip-git-repo-check \
          -c sandbox_mode='"workspace-write"' "$sid" "$rprompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null)
      fi
      trc=$?; cat "$tout.jsonl" >> "$out.jsonl"; cat "$tout.err" >> "$out.err"
      if [ "$trc" -ne 0 ]; then rc=$trc; verify_state=incomplete; verify_reason="교정 턴의 구현자 하네스 종료 코드 $trc"; break; fi
    done
    # 회차 증거(판정 대상 복사본 포함)는 결과 폴더로 옮긴다: 프로젝트에 남으면 사례 판정이 검토 흔적을 구현자의 산출물로 읽는다.
    rm -rf "${out:?}.rounds"; mkdir -p "$out.rounds"
    for ev in "$work/project/work/review" "$work/project"/work/*/verify; do
      [ ! -d "$ev" ] || mv "$ev" "$out.rounds/$(basename "$(dirname "$ev")")-$(basename "$ev")"
    done
    rmdir "$out.rounds" 2>/dev/null; [ "$had_work" = true ] || rmdir "$work/project/work" 2>/dev/null
  fi
  # 끝난 때 관문이 사용자 답을 기다리는지(v3.0 이하 커밋: 승인 전이거나 사용자 철회·기준 변경으로 닫힘): 구현 실패·검증 실패와 구별해 센다.
  # 관문 기록이 없으면(관문 없는 커밋·훅이 돌지 않음) 알 수 없으므로 대기로 세지 않는다.
  gate_waiting=$( [ -z "$sid" ] || [ ! -f "$work/project/.agents/skills/wf-design/approval-gate.py" ] || (cd "$work/project" && python3 -I .agents/skills/wf-design/approval-gate.py status --session "$sid" < /dev/null 2>/dev/null) \
    | python3 -I -c 'import json,sys
try: d = json.load(sys.stdin)
except ValueError: d = {}
print("true" if d.get("waiting") else "false")' 2>/dev/null)
    # Codex 의 exec 기록(--json)에는 하위 에이전트 생성(spawn_agent)이 남지 않는다. 관찰용으로 이 세션의 원본 기록(rollout)을 남긴다.
  [ "$harness" != codex ] || { [ -z "$sid" ] || find "$ch/sessions" -name "rollout-*$sid.jsonl" -exec cat {} + > "$out.rollout.jsonl" 2>/dev/null; rm -rf "${ch:?}"; }
  seconds=$(( $(date +%s) - start ))
  observed=$(python3 -I "$here/observe.py" "$out.jsonl" $( [ ! -f "$case_dir/observe.txt" ] || cat "$case_dir/observe.txt") 2>/dev/null || echo '{}')
  # 판정 검사는 0=통과, 1=실패, 2=검토 필요(원문을 사람이 판정)를 돌려준다. 3=미확인은 실행기가 정한다:
  # 하네스가 모델 용량·요청 한도 같은 외부 장애로 끝났으면 판정하지 않고 통과율 분모에서 뺀다(시도·사유는 남긴다).
  # 외부 장애는 오류 사건(Codex error·turn.failed, Claude 오류 결과)과 표준 오류에서만 찾는다(일반 답 속 낱말은 보지 않는다).
  pat='at capacity|rate.?limit|usage.?limit|hit your [0-9a-z -]*limit|api_error_status"?: ?429|too many requests|overloaded|HTTP 429|stream disconnected|service unavailable'
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
  # 판정에 쓴 파일의 지문. 실행 중 판정 파일이 사라졌으면 빈 지문으로 기록하지 않고 멈춘다(원시 기록 .jsonl 은 남아 있다).
  judge_version=$(python3 -I "$here/caseinfo.py" version "$case_dir") || fail "판정기 지문을 만들 수 없다(위 파일 누락): $out"
  # 사례가 AGENTS.md 를 읽을 수 없게 만들었으면 바이트는 설치에 쓴 키트 checkout 에서 잰다.
  agents_bytes=$( { wc -c < "$work/project/AGENTS.md" || wc -c < "$work/kit/AGENTS.md"; } 2>/dev/null | tr -d ' ')
  # 값은 환경 변수로 넘겨 따옴표·줄바꿈이 섞인 판정 문구도 그대로 기록한다.
  E_REQUIRED=$( [ -f "$case_dir/review-required" ] && echo true || echo false ) E_HERE=$here E_CASE=$case_name E_REF=$ref E_COMMIT=$commit E_HARNESS=$harness E_RUN=$i E_RC=$rc E_SEC=$seconds \
  E_VERSION=$("$harness" --version 2>/dev/null | head -1) E_BYTES=$agents_bytes E_CHECK_RC=$check_rc E_VERDICT=$verdict \
  E_G1=$(fingerprint ~/.claude/CLAUDE.md) E_G2=$(fingerprint ~/.agents/USER.md) E_G3=$(fingerprint ~/.codex/AGENTS.md) E_G4=$(skills_fingerprint) E_G5=$(plugins_fingerprint "$work/project") E_OBS=$observed E_VSTATE=$verify_state E_BCHANGED=${baseline_changed:-false} E_VREASON=$verify_reason E_VROUNDS=$verify_rounds E_VRC=$verifier_rc E_VJSON=$vjson E_LANG=${EVALS_LANG:-} E_CSET=${EVALS_CLAUDE_SETTINGS:+$(cat "$EVALS_CLAUDE_SETTINGS")} E_JUDGE=$judge_version E_GATE=$gate E_WAITING=${gate_waiting:-false} E_VTOOL=${verifier_tool:-} E_CTRUST=${codex_trusted:-false} E_INPUT=$input E_TURNS=$sent E_PLANNED=${#turns[@]} E_WAIT=$(python3 -I -c 'import json,sys
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
  python3 -I "$here/result.py" "$out.meta.json"
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
