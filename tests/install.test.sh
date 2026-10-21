#!/usr/bin/env bash
# install.sh 의 설치 보장을 확인한다: 정상 설치, 충돌 시 기존 파일 보존, 재실행 거절, 잘못된 부모 경로 거절.
set -uo pipefail
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
pass=0; failed=0
ok() { pass=$((pass+1)); printf 'ok   %s\n' "$1"; }
ng() { failed=$((failed+1)); printf 'FAIL %s\n' "$1"; }
install() { bash "$kit/install.sh" "$1" >/dev/null 2>"$tmp/err"; }

# 정상 설치: 키트 파일이 원본과 같고, 링크·ignore·버전 기록이 생긴다
t="$tmp/fresh"; mkdir "$t"
if install "$t" \
  && cmp -s "$kit/AGENTS.md" "$t/AGENTS.md" && cmp -s "$kit/CLAUDE.md" "$t/CLAUDE.md" \
  && cmp -s "$kit/.agents/skills/wf-verify/SKILL.md" "$t/.agents/skills/wf-verify/SKILL.md" \
  && [ "$(readlink "$t/.claude/skills")" = "../.agents/skills" ] \
  && grep -qxF '/work/' "$t/.gitignore" && [ -s "$t/.agents/agent-workflow-kit.version" ]; then ok "fresh install"; else ng "fresh install"; fi

# 재실행 거절: 두 번째 설치는 멈추고 파일을 바꾸지 않는다
before=$(cd "$t" && find . -type f -exec cksum {} + | sort)
if ! install "$t" && grep -q 'Conflict' "$tmp/err" && [ "$(cd "$t" && find . -type f -exec cksum {} + | sort)" = "$before" ]; then ok "rerun refused"; else ng "rerun refused"; fi

# 충돌 보존: 기존 AGENTS.md·CLAUDE.md·.claude/skills 중 하나라도 있으면 멈추고 그대로 둔다
for p in AGENTS.md CLAUDE.md .claude/skills; do
  t="$tmp/conflict-${p//\//_}"; mkdir -p "$t/$(dirname "$p")"
  if [ "$p" = .claude/skills ]; then mkdir "$t/$p"; touch "$t/$p/mine"; else echo mine > "$t/$p"; fi
  if ! install "$t" && grep -q "Conflict: $p" "$tmp/err" && [ ! -e "$t/.agents/skills/wf-design" ] \
    && { [ -f "$t/$p" ] && [ "$(cat "$t/$p")" = mine ] || [ -f "$t/$p/mine" ]; }; then ok "conflict $p kept"; else ng "conflict $p kept"; fi
done

# 잘못된 부모: .agents 가 심링크거나 파일이면 거절한다
t="$tmp/parent-link"; mkdir -p "$t" "$tmp/elsewhere"; ln -s "$tmp/elsewhere" "$t/.agents"
if ! install "$t" && grep -q 'Invalid parent: .agents' "$tmp/err" && [ -z "$(ls -A "$tmp/elsewhere")" ]; then ok "symlink parent refused"; else ng "symlink parent refused"; fi
t="$tmp/parent-file"; mkdir "$t"; echo x > "$t/.claude"
if ! install "$t" && grep -q 'Invalid parent: .claude' "$tmp/err"; then ok "file parent refused"; else ng "file parent refused"; fi

printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
