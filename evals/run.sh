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
# EVALS_VERIFY=1 이면 모든 턴 뒤에 실행기가 별도 검증 세션(같은 하네스의 새 세션)을 띄운다. 검증자는 사용자 원문 그대로·
# 마지막 사용자 턴의 변경(diff)·구현자의 마지막 답만 받고, 근거 없이 확정된 제품 결과가 있으면 RETURN 으로 돌려보낸다.
# 돌려보내면 구현자 세션에 반환 턴을 한 번 보낸다. 판정은 반환 턴 뒤의 답과, 마지막 사용자 턴 직전 상태와의 비교로 한다.
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
    && { [ ! -f "$case_dir/setup.sh" ] || bash "$case_dir/setup.sh"; } \
    && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm fixture) || fail "사례 준비 실패"
  bash "$work/kit/install.sh" "$work/project" >/dev/null 2>&1 || fail "키트 설치 실패: $commit"
  (cd "$work/project" && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm kit)
  # 설치 뒤 준비(선택): 설치된 상태를 바꿔야 하는 사례(예: 키트 본문을 읽을 수 없게, 다른 저장소를 옆에 두기)가 쓴다.
  # 설치 커밋 뒤에 실행하므로 그 변경은 세션이 보는 작업 트리에만 남는다. EVALS_KIT 는 설치에 쓴 키트 checkout 이다.
  [ ! -f "$case_dir/after-install.sh" ] || (cd "$work/project" && EVALS_KIT="$work/kit" bash "$case_dir/after-install.sh") \
    || fail "설치 뒤 준비 실패: $case_dir/after-install.sh"

  name="$case_name-$(printf %.7s "$commit")-$harness-$i"
  out="$out_root/$name"
  # 사례의 턴: prompt.txt 가 첫 턴, prompt2.txt·prompt3.txt … 가 같은 세션을 이어 가는 다음 턴이다.
  # 턴마다 원시 기록을 .tN.jsonl 로 남기고, 판정용 .jsonl 은 모든 턴을 순서대로 이은 것이다(마지막 답 = 마지막 턴의 답).
  turns=("$case_dir/prompt.txt")
  for n in 2 3 4 5 6 7 8 9; do [ ! -f "$case_dir/prompt$n.txt" ] || turns+=("$case_dir/prompt$n.txt"); done
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
  t=0
  for turn in "${turns[@]}"; do
    t=$((t + 1)); prompt=$(cat "$turn"); tout="$out.t$t"
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
  verify_state=off
  if [ "${EVALS_VERIFY:-0}" = 1 ] && [ "$rc" -eq 0 ]; then
    # 검증자에게는 사용자 원문 그대로, 마지막 사용자 턴에서 바뀐 내용, 구현자의 마지막 답만 넘긴다(구현자가 정리한 조건은 넘기지 않는다).
    vprompt=$(cat "$here/verifier-prompt.txt"
      n=0; for turn in "${turns[@]}"; do n=$((n + 1)); printf '\n\n## 사용자 원문 %s\n' "$n"; cat "$turn"; done
      printf '\n\n## 마지막 사용자 턴에서 바뀐 내용(diff)\n'; diff -ruN -x .git -x .agents "$work/before-last" "$work/project" | head -c 60000
      printf '\n\n## 구현자의 마지막 답\n'; python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from transcript import read; print(read(sys.argv[2])[1])' "$here" "$out.t$t.jsonl")
    if [ "$harness" = claude ]; then
      (cd "$work/project" && perl -e 'alarm shift; exec @ARGV' 900 claude -p "$vprompt" --output-format stream-json --verbose \
        --allowedTools Read,Grep,Glob --max-turns 30 > "$out.verify.jsonl" 2>> "$out.err")
    else
      vh=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$vh/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$vh/"
      CODEX_HOME=$vh perl -e 'alarm shift; exec @ARGV' 900 codex exec --json --skip-git-repo-check --sandbox read-only \
        -C "$work/project" "$vprompt" > "$out.verify.jsonl" 2>> "$out.err" < /dev/null
      rm -rf "${vh:?}"
    fi
    vrc=$?
    vfinal=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from transcript import read; print(read(sys.argv[2])[1])' "$here" "$out.verify.jsonl")
    if [ "$vrc" -ne 0 ]; then rc=$vrc; verify_state=crashed
    elif printf '%s' "$vfinal" | head -1 | grep -q RETURN; then
      verify_state=returned; t=$((t + 1)); tout="$out.t$t"
      # 반환 턴은 사용자 턴이 아니므로 before-last 를 덮지 않는다(판정은 마지막 사용자 턴 직전과 비교).
      rprompt=$(printf '별도 검증자가 다음 사유로 돌려보냈습니다. 검증자의 판단을 그대로 따르지 말고, 사용자 원문과 작업 기준에 비추어 판단해 다시 답하세요.\n\n%s' "$vfinal")
      if [ "$harness" = claude ]; then
        (cd "$work/project" && perl -e 'alarm shift; exec @ARGV' 900 claude -p "$rprompt" --resume "$sid" --output-format stream-json --verbose \
          --dangerously-skip-permissions --max-turns 30 > "$tout.jsonl" 2> "$tout.err")
      else
        (cd "$work/project" && CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' "$limit" codex exec resume --json --skip-git-repo-check \
          -c sandbox_mode='"workspace-write"' "$sid" "$rprompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null)
      fi
      trc=$?; cat "$tout.jsonl" >> "$out.jsonl"; cat "$tout.err" >> "$out.err"; [ "$trc" -eq 0 ] || rc=$trc
    else verify_state=ok
    fi
  fi
  # Codex 의 exec 기록(--json)에는 하위 에이전트 생성(spawn_agent)이 남지 않는다. 관찰용으로 이 세션의 원본 기록(rollout)을 남긴다.
  [ "$harness" != codex ] || { [ -z "$sid" ] || find "$ch/sessions" -name "rollout-*$sid.jsonl" -exec cat {} + > "$out.rollout.jsonl" 2>/dev/null; rm -rf "${ch:?}"; }
  seconds=$(( $(date +%s) - start ))
  # 판정 검사는 0=통과, 1=실패, 2=검토 필요(원문을 사람이 판정)를 돌려준다. 3=미확인은 실행기가 정한다:
  # 하네스가 모델 용량·요청 한도 같은 외부 장애로 끝났으면 판정하지 않고 통과율 분모에서 뺀다(시도·사유는 남긴다).
  external=$(LC_ALL=C grep -a -o -m1 -iE 'at capacity|rate.?limit|too many requests|overloaded|HTTP 429|stream disconnected|service unavailable' "$out.jsonl" "$out.err" 2>/dev/null | head -1 | cut -d: -f2-)
  if [ "$rc" -ne 0 ] && [ -n "$external" ]; then
    verdict="UNVERIFIED 하네스가 외부 장애($external)로 종료 코드 $rc 로 끝나 판정하지 않았다"; check_rc=3
  elif [ "$rc" -ne 0 ]; then
    verdict="FAIL 하네스가 종료 코드 $rc 로 끝나 판정하지 않았다"; check_rc=1
  else
    verdict=$(EVALS_BEFORE_LAST_TURN="$work/before-last" python3 -I "$case_dir/check.py" "$work/project" "$out.jsonl" 2>&1); check_rc=$?
  fi
  # 사례가 AGENTS.md 를 읽을 수 없게 만들었으면 바이트는 설치에 쓴 키트 checkout 에서 잰다.
  observed=$(python3 -I "$here/observe.py" "$out.jsonl" $( [ ! -f "$case_dir/observe.txt" ] || cat "$case_dir/observe.txt") 2>/dev/null || echo '{}')
  agents_bytes=$( { wc -c < "$work/project/AGENTS.md" || wc -c < "$work/kit/AGENTS.md"; } 2>/dev/null | tr -d ' ')
  # 값은 환경 변수로 넘겨 따옴표·줄바꿈이 섞인 판정 문구도 그대로 기록한다.
  E_CASE=$case_name E_REF=$ref E_COMMIT=$commit E_HARNESS=$harness E_RUN=$i E_RC=$rc E_SEC=$seconds \
  E_VERSION=$("$harness" --version 2>/dev/null | head -1) E_BYTES=$agents_bytes E_CHECK_RC=$check_rc E_VERDICT=$verdict \
  E_G1=$(fingerprint ~/.claude/CLAUDE.md) E_G2=$(fingerprint ~/.agents/USER.md) E_G3=$(fingerprint ~/.codex/AGENTS.md) E_G4=$(skills_fingerprint) E_OBS=$observed E_VSTATE=$verify_state E_GATE=$gate \
  python3 -I -c '
import json, os, sys
e = os.environ
json.dump({"case": e["E_CASE"], "kit_ref": e["E_REF"], "kit_commit": e["E_COMMIT"], "harness": e["E_HARNESS"],
  "run": int(e["E_RUN"]), "harness_version": e["E_VERSION"], "exit_code": int(e["E_RC"]), "seconds": int(e["E_SEC"]),
  "agents_md_bytes": int(e["E_BYTES"]), "check_passed": e["E_CHECK_RC"] == "0", "check_needs_review": e["E_CHECK_RC"] == "2", "check_unverified": e["E_CHECK_RC"] == "3", "approval_gate": e["E_GATE"] == "true", "check_output": e["E_VERDICT"], "observed": json.loads(e["E_OBS"] or "{}"), "verifier": e["E_VSTATE"],
  "global_instructions": {"~/.claude/CLAUDE.md": e["E_G1"], "~/.agents/USER.md": e["E_G2"], "~/.codex/AGENTS.md": e["E_G3"], "global skills": e["E_G4"]}},
  open(sys.argv[1], "w"), ensure_ascii=False, indent=1)' "$out.meta.json"
  shown=FAIL; [ "$check_rc" -ne 0 ] || shown=PASS; [ "$check_rc" -ne 3 ] || shown=UNVERIFIED
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
