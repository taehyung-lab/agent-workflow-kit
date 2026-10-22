#!/usr/bin/env bash
# 키트를 대상 저장소에 처음 설치하거나(--update 없이), 설치된 저장소의 키트 소유 부분만 키트의 현재 커밋으로 교체한다.
# 키트 소유 부분: AGENTS.md의 표시 영역, CLAUDE.md, 키트 .agents/skills 아래 파일. 그 밖은 프로젝트가 관리한다.
# macOS 기본 bash 3.2에서 돌도록 mapfile·빈 배열 확장을 쓰지 않는다.
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 1; }
mode=install
if [ "${1-}" = --update ]; then mode=update; shift; fi
[ "$#" -eq 1 ] || fail 'Usage: bash install.sh [--update] TARGET_DIRECTORY'
kit_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
kit() { git -C "$kit_root" "$@"; }
new=$(kit rev-parse --verify HEAD 2>/dev/null) || fail 'Kit must be a git checkout'
[ -z "$(kit status --porcelain)" ] || fail 'Kit has uncommitted changes; the version file could not reproduce them'
cd -- "$1"
begin='<!-- agent-workflow-kit:begin -->'
end='<!-- agent-workflow-kit:end -->'
version_file=.agents/agent-workflow-kit.version

# 커밋 $1에서 키트가 통째로 소유하는 파일 목록을 줄 단위로 낸다(AGENTS.md는 영역 단위라 제외)
owned() { printf '%s\n' CLAUDE.md; kit ls-tree -r --name-only "$1" -- .agents/skills; }
# 표준 입력에서 키트 영역(표시 줄 포함)만 낸다
region() { awk -v b="$begin" -v e="$end" '$0==b{f=1} f{print} $0==e{f=0}'; }
# 파일 $1에 시작·끝 표시가 하나씩 순서대로 있는지 확인한다
markers_ok() { awk -v b="$begin" -v e="$end" '$0==b{nb++; if(ne)bad=1} $0==e{ne++} END{exit !(nb==1 && ne==1 && !bad)}' "$1"; }
# 줄 목록 $2에 줄 $1이 있는지 확인한다
listed() { printf '%s\n' "$2" | grep -qxF -- "$1"; }
trap 'printf "%s\n" "Install failed; partial files may remain. Inspect before retry." >&2' ERR

# 처음 설치: 키트 소유 경로가 하나라도 있으면 쓰기 전에 멈춘다
install_fresh() {
  local p files skill_dirs
  files=$(owned "$new")
  skill_dirs=$(printf '%s\n' "$files" | awk -F/ '$1==".agents"{print $1"/"$2"/"$3}' | sort -u)
  for p in AGENTS.md CLAUDE.md .claude/skills work "$version_file" $skill_dirs; do
    [ ! -e "$p" ] && [ ! -L "$p" ] || fail "Conflict: $p"
  done
  for p in .agents .agents/skills .claude; do
    [ ! -L "$p" ] && { [ ! -e "$p" ] || [ -d "$p" ]; } || fail "Invalid parent: $p"
  done
  [ ! -L .gitignore ] && { [ ! -e .gitignore ] || { [ -f .gitignore ] && [ -r .gitignore ] && [ -w .gitignore ]; }; } || fail 'Invalid .gitignore'
  mkdir -p .agents/skills .claude
  set -C
  for p in AGENTS.md $files; do
    mkdir -p "$(dirname -- "$p")"
    kit show "$new:$p" > "$p"
  done
  set +C
  ln -s ../.agents/skills .claude/skills
  printf '%s\n' "$new" > "$version_file"
  if ! grep -qxF '/work/' .gitignore 2>/dev/null; then
    printf '\n/work/\n' >> .gitignore
  fi
  printf '%s\n' 'Files installed. Fill the project map and verify skill discovery in a new session.'
}

# 업데이트: 키트 소유 부분이 설치 당시 그대로일 때만 새 커밋으로 교체하고, 프로젝트 부분은 건드리지 않는다
install_update() {
  local p old old_files new_files changed=''
  [ -f "$version_file" ] || fail "Not installed: $version_file missing"
  old=$(cat "$version_file")
  kit cat-file -e "$old^{commit}" 2>/dev/null || fail "Installed version $old not found in kit; fetch it first"
  if [ "$old" = "$new" ]; then printf 'Already at %s\n' "$new"; return; fi
  [ -f AGENTS.md ] && markers_ok AGENTS.md || fail 'AGENTS.md has no single kit region; see README to mark it once'
  kit show "$old:AGENTS.md" | grep -qxF "$begin" || fail "Installed version $old predates kit region; see README to mark it once"
  cmp -s <(region < AGENTS.md) <(kit show "$old:AGENTS.md" | region) || changed="$changed AGENTS.md(kit-region)"
  old_files=$(owned "$old")
  new_files=$(owned "$new")
  for p in $old_files; do
    [ -f "$p" ] && [ ! -L "$p" ] && cmp -s "$p" <(kit show "$old:$p") || changed="$changed $p"
  done
  for p in $new_files; do
    listed "$p" "$old_files" || { [ ! -e "$p" ] && [ ! -L "$p" ]; } || changed="$changed $p(exists)"
  done
  [ -z "$changed" ] || fail "Local change in kit-owned path:$changed. Move project changes to project sections or role skills, then retry."
  kit show "$new:AGENTS.md" | region > AGENTS.md.kit-region
  awk -v b="$begin" -v e="$end" -v rf=AGENTS.md.kit-region \
    '$0==b{while((getline l < rf)>0)print l; f=1; next} $0==e{f=0; next} !f{print}' AGENTS.md > AGENTS.md.kit-update
  mv AGENTS.md.kit-update AGENTS.md
  rm AGENTS.md.kit-region
  for p in $old_files; do
    listed "$p" "$new_files" && continue
    rm -- "$p"
    rmdir -p -- "$(dirname -- "$p")" 2>/dev/null || true
  done
  for p in $new_files; do
    mkdir -p "$(dirname -- "$p")"
    kit show "$new:$p" > "$p"
  done
  printf '%s\n' "$new" > "$version_file"
  printf 'Updated %s -> %s. Review the diff and verify skill discovery in a new session.\n' "$old" "$new"
}

if [ "$mode" = update ]; then install_update; else install_fresh; fi
