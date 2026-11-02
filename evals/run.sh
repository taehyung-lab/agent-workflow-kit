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
mkdir -p "$out_root"
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

  name="$case_name-$(printf %.7s "$commit")-$harness-$i"
  out="$out_root/$name"
  # 사례의 턴: prompt.txt 가 첫 턴, prompt2.txt·prompt3.txt … 가 같은 세션을 이어 가는 다음 턴이다.
  # 턴마다 원시 기록을 .tN.jsonl 로 남기고, 판정용 .jsonl 은 모든 턴을 순서대로 이은 것이다(마지막 답 = 마지막 턴의 답).
  turns=("$case_dir/prompt.txt")
  for n in 2 3 4 5 6 7 8 9; do [ ! -f "$case_dir/prompt$n.txt" ] || turns+=("$case_dir/prompt$n.txt"); done
  start=$(date +%s); rc=0; sid=""; : > "$out.jsonl"; : > "$out.err"
  # Codex 는 전역 지침을 CODEX_HOME 에서 읽는다. 실제 설정을 복사한 임시 홈을 쓰고, 세션을 이어 가도록 모든 턴이 끝날 때까지 둔다.
  if [ "$harness" = codex ]; then ch=$(mktemp -d); cp ~/.codex/auth.json ~/.codex/config.toml "$ch/" 2>/dev/null; [ ! -f ~/.codex/AGENTS.md ] || cp ~/.codex/AGENTS.md "$ch/"; fi
  t=0
  for turn in "${turns[@]}"; do
    t=$((t + 1)); prompt=$(cat "$turn"); tout="$out.t$t"
    # 마지막 턴 직전의 작업 파일(설치된 키트·git 제외)을 남겨, 판정이 "마지막 턴에서 무엇을 바꿨나"를 볼 수 있게 한다.
    if [ "$t" -eq "${#turns[@]}" ]; then rm -rf "${work:?}/before-last"; mkdir "$work/before-last" \
      && (cd "$work/project" && tar cf - --exclude=./.git --exclude=./.agents .) | tar xf - -C "$work/before-last"; fi
    if [ "$harness" = claude ]; then
      resume=(); [ "$t" -eq 1 ] || resume=(--resume "$sid")
      (cd "$work/project" && perl -e 'alarm shift; exec @ARGV' 900 claude -p "$prompt" ${resume[@]+"${resume[@]}"} --output-format stream-json --verbose \
        --dangerously-skip-permissions --max-turns 30 > "$tout.jsonl" 2> "$tout.err")
    elif [ "$t" -eq 1 ]; then
      CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' 900 codex exec --json --skip-git-repo-check --sandbox workspace-write \
        -C "$work/project" "$prompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null
    else
      (cd "$work/project" && CODEX_HOME=$ch perl -e 'alarm shift; exec @ARGV' 900 codex exec resume --json --skip-git-repo-check \
        -c sandbox_mode='"workspace-write"' "$sid" "$prompt" > "$tout.jsonl" 2> "$tout.err" < /dev/null)
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
  [ "$harness" != codex ] || rm -rf "${ch:?}"
  seconds=$(( $(date +%s) - start ))
  # 판정 검사는 0=통과, 1=실패, 2=검토 필요(원문을 사람이 판정)를 돌려준다.
  verdict=$(EVALS_BEFORE_LAST_TURN="$work/before-last" python3 -I "$case_dir/check.py" "$work/project" "$out.jsonl" 2>&1); check_rc=$?
  agents_bytes=$(wc -c < "$work/project/AGENTS.md" | tr -d ' ')
  # 값은 환경 변수로 넘겨 따옴표·줄바꿈이 섞인 판정 문구도 그대로 기록한다.
  E_CASE=$case_name E_REF=$ref E_COMMIT=$commit E_HARNESS=$harness E_RUN=$i E_RC=$rc E_SEC=$seconds \
  E_VERSION=$("$harness" --version 2>/dev/null | head -1) E_BYTES=$agents_bytes E_CHECK_RC=$check_rc E_VERDICT=$verdict \
  E_G1=$(fingerprint ~/.claude/CLAUDE.md) E_G2=$(fingerprint ~/.agents/USER.md) E_G3=$(fingerprint ~/.codex/AGENTS.md) E_G4=$(skills_fingerprint) \
  python3 -I -c '
import json, os, sys
e = os.environ
json.dump({"case": e["E_CASE"], "kit_ref": e["E_REF"], "kit_commit": e["E_COMMIT"], "harness": e["E_HARNESS"],
  "run": int(e["E_RUN"]), "harness_version": e["E_VERSION"], "exit_code": int(e["E_RC"]), "seconds": int(e["E_SEC"]),
  "agents_md_bytes": int(e["E_BYTES"]), "check_passed": e["E_CHECK_RC"] == "0", "check_needs_review": e["E_CHECK_RC"] == "2", "check_output": e["E_VERDICT"],
  "global_instructions": {"~/.claude/CLAUDE.md": e["E_G1"], "~/.agents/USER.md": e["E_G2"], "~/.codex/AGENTS.md": e["E_G3"], "global skills": e["E_G4"]}},
  open(sys.argv[1], "w"), ensure_ascii=False, indent=1)' "$out.meta.json"
  printf '%s exit=%s check=%s %s\n' "$name" "$rc" "$([ $check_rc -eq 0 ] && echo PASS || echo FAIL)" "$(printf '%s' "$verdict" | head -1)"
  # 판정 검사를 고친 뒤 다시 판정할 수 있게, 끝난 프로젝트의 작업 파일(설치된 키트·git 제외)을 남긴다.
  mkdir -p "$out.files" && (cd "$work/project" && tar cf - --exclude=./.git --exclude=./.agents .) | tar xf - -C "$out.files"
  # 마지막 턴 직전 상태도 남긴다. 다시 판정할 때 EVALS_BEFORE_LAST_TURN 으로 넘긴다.
  [ ! -d "$work/before-last" ] || cp -R "$work/before-last" "$out.before-last"
  # 하네스가 실패했으면 판정과 관계없이, 처음 실패한 실행의 종료 코드를 그대로 돌려준다.
  [ "$rc" -eq 0 ] || [ "$status" -ne 0 ] || status=$rc
  rm -rf "${work:?}"
done
exit "$status"
