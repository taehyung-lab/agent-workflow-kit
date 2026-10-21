#!/usr/bin/env bash
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 1; }
[ "$#" -eq 1 ] || fail 'Usage: bash install.sh TARGET_DIRECTORY'
kit_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$1"
skills=(wf-design wf-implement wf-verify)
files=(AGENTS.md CLAUDE.md .agents/skills/wf-design/work-template.md)
for s in "${skills[@]}"; do files+=(".agents/skills/$s/SKILL.md"); done
for p in "${files[@]}"; do [ -f "$kit_root/$p" ] && [ -r "$kit_root/$p" ] || fail "Missing source: $p"; done
version_file=.agents/agent-workflow-kit.version
for p in AGENTS.md CLAUDE.md .claude/skills work "$version_file" "${skills[@]/#/.agents/skills/}"; do
  [ ! -e "$p" ] && [ ! -L "$p" ] || fail "Conflict: $p"
done
for p in .agents .agents/skills .claude; do
  [ ! -L "$p" ] && { [ ! -e "$p" ] || [ -d "$p" ]; } || fail "Invalid parent: $p"
done
[ ! -L .gitignore ] && { [ ! -e .gitignore ] || { [ -f .gitignore ] && [ -r .gitignore ] && [ -w .gitignore ]; }; } || fail 'Invalid .gitignore'
trap 'printf "%s\n" "Install failed; partial files may remain. Inspect before retry." >&2' ERR
mkdir -p .agents/skills .claude
for s in "${skills[@]}"; do mkdir ".agents/skills/$s"; done
set -C
for p in "${files[@]}"; do
  cat "$kit_root/$p" > "$p"
  cmp -s "$kit_root/$p" "$p"
done
ln -s ../.agents/skills .claude/skills
# 프로젝트가 따르는 키트 버전을 고정해 기록한다(업데이트 때 비교 기준)
git -C "$kit_root" rev-parse HEAD 2>/dev/null > "$version_file" || echo unknown > "$version_file"
if ! grep -qxF '/work/' .gitignore 2>/dev/null; then
  printf '\n/work/\n' >> .gitignore
fi
printf '%s\n' 'Files installed. Fill the project map and verify skill discovery in a new session.'
