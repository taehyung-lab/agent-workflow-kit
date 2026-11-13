#!/usr/bin/env bash
# 키트를 대상 저장소에 처음 설치하거나(--update 없이), 설치된 저장소의 키트 소유 부분만 키트의 현재 커밋으로 교체한다.
# 키트 소유 부분: AGENTS.md의 표시 영역, CLAUDE.md, 키트 .agents/skills 아래 파일. 그 밖은 프로젝트가 관리한다.
# 훅: Claude 프로젝트 설정에 세션 시작 정보 훅(정보만, 차단 없음) 하나를 두고, Codex 설정의 키트 훅과 v3.0 이하의 승인 관문 훅 항목은 지운다(kit_hooks). 다른 훅·설정은 그대로 둔다.
# macOS 기본 bash 3.2에서 돌도록 mapfile·빈 배열 확장을 쓰지 않는다.
set -Eeuo pipefail
fail() { printf '%s\n' "$*" >&2; exit 1; }
mode=install
if [ "${1-}" = --update ]; then mode=update; shift; fi
[ "$#" -eq 1 ] || fail 'Usage: bash install.sh [--update] TARGET_DIRECTORY'
kit_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
kit() { git -C "$kit_root" "$@"; }
new=$(kit rev-parse --verify HEAD 2>/dev/null) || fail 'Kit must be a git checkout'
[ "$(kit rev-parse --show-toplevel)" = "$kit_root" ] || fail 'Kit must be the root of its own git checkout'
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
# 키트가 쓰는 경로 $@의 상위 폴더가 심링크이거나 폴더가 아니면 멈춘다(쓰기가 대상 밖으로 나가지 않게)
parents_ok() {
  local p d
  for p in "$@"; do
    d=$(dirname -- "$p")
    while [ "$d" != . ]; do
      [ ! -L "$d" ] && { [ ! -e "$d" ] || [ -d "$d" ]; } || fail "Invalid parent: $d"
      d=$(dirname -- "$d")
    done
  done
}
# 실패하면 조립 중이던 임시 파일을 지우고 부분 설치 가능성을 알린다
assembled=''
trap 'rm -f "$assembled"; printf "%s\n" "Install failed; partial files may remain. Inspect before retry." >&2' ERR

# 프로젝트 훅 설정(.claude/settings.json, .codex/hooks.json)에서 키트 항목만 맞춘다. 다른 훅·설정(예: 프로젝트의 포맷터 훅,
# enabledPlugins, permissions)은 그대로 두고, 바꿀 것이 없는 파일은 쓰지 않는다. 사용자 전역 설정(~/.claude, ~/.codex)은 건드리지 않는다.
# 키트 항목: ① 세션 시작 정보 훅(명령에 wf-context/context.py, v3.2~): 키트에 그 파일이 있으면 Claude 의 SessionStart 에 하나 두고, 없으면 지운다.
#            이 훅은 맥락 정보만 낸다(차단·승인 판독 없음, 늘 종료 0). 파일 쓰기·명령 허용은 각 도구의 권한 설정이 맡는다.
#            Codex(.codex/hooks.json)에는 두지 않고 있던 항목을 지운다(v3.5~): Codex 는 경로·명령마다 훅 신뢰를 따로 묻고, 신뢰 전에는
#            경고 없이 건너뛰어 새 워크트리·자동 실행에서 정보를 넣지 못하면서 확인창만 늘렸다. 같은 정보는 context.py inspect 로 얻는다.
#            ② v3.0 이하의 승인 관문 훅(명령에 approval-gate.py): 지운다.
# $1 = check: 쓰기 전에, 고칠 파일이 일반 파일이고 올바른 JSON 객체인지만 확인한다(깨졌으면 멈춘다). $1 = apply: 맞춘다.
kit_hooks() {
  local f found='' want=0
  [ -f .agents/skills/wf-context/context.py ] && want=1
  [ "$1" = check ] && kit show "$new:.agents/skills/wf-context/context.py" >/dev/null 2>&1 && want=1
  for f in .claude/settings.json .codex/hooks.json; do
    if [ -e "$f" ] || [ -L "$f" ]; then
      if { [ "$want" = 1 ] && [ "$f" = .claude/settings.json ]; } || grep -qE 'approval-gate\.py|wf-context/context\.py' "$f" 2>/dev/null; then found="$found $f"; fi
    fi
  done
  [ "$want" = 1 ] || [ -n "$found" ] || return 0
  parents_ok .claude/settings.json .codex/hooks.json
  for f in $found; do [ ! -L "$f" ] && [ -f "$f" ] || fail "Could not read hook settings in $f (not a regular file); fix it, then retry"; done
  if ! command -v python3 >/dev/null 2>&1; then
    [ "$1" = check ] || printf 'Hook settings NOT updated (python3 not found). The context hook is not registered; run python3 .agents/skills/wf-context/context.py inspect when python3 is available.%s\n' "${found:+ Remove entries running approval-gate.py from$found by hand.}"
    return 0
  fi
  AWK_WANT=$want python3 -I - "$1" <<'PY' || fail "Could not read hook settings in$found; fix the JSON, then retry"
import json, os, sys
mode, want_any = sys.argv[1], os.environ.get("AWK_WANT") == "1"
script = ".agents/skills/wf-context/context.py"
# 훅 명령: 키트 파일이나 python3·git 이 없어도 아무것도 내지 않고 0 으로 끝난다(정보만 주는 훅이라 세션을 막지 않는다).
# Claude Code 는 프로젝트 폴더를 CLAUDE_PROJECT_DIR 로 준다.
tail = f'f="$p/{script}"; [ -f "$f" ] && command -v python3 >/dev/null 2>&1 && python3 -I "$f" hook 2>/dev/null; exit 0'
want_hook = {
    ".claude/settings.json": {"type": "command", "command": 'p="$CLAUDE_PROJECT_DIR"; ' + tail, "timeout": 10},
    ".codex/hooks.json": None,  # 더하지 않는다: 예전 키트 항목을 지우려고만 읽는다
}
def kit_entry(h):
    return isinstance(h, dict) and any(k in str(h.get("command", "")) for k in ("approval-gate.py", "wf-context/context.py"))
for path, desired in want_hook.items():
    want = want_any and path == ".claude/settings.json"  # Codex 에는 정보 훅을 두지 않는다(위 ① 설명)
    exists = os.path.exists(path)
    if not exists and not want:
        continue
    try:
        raw = open(path, encoding="utf-8").read() if exists else ""
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        sys.exit(1)
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        sys.exit(1)
    if mode == "check":
        continue
    before = json.dumps(data)
    hooks = data.get("hooks", {})
    kept_desired, removed_gate = False, False
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        groups = []
        for g in hooks[event]:  # 키트 항목만 빼고, 같은 그룹의 다른 훅·matcher 는 그대로 둔다
            inner = g.get("hooks") if isinstance(g, dict) else None
            if not isinstance(inner, list):
                groups.append(g)
                continue
            kept = []
            for h in inner:
                if want and event == "SessionStart" and h == desired and not kept_desired:
                    kept.append(h); kept_desired = True  # 이미 같은 항목이 있으면 자리를 옮기지 않는다(다시 실행해도 그대로)
                elif kit_entry(h):
                    removed_gate = removed_gate or "approval-gate.py" in str(h.get("command", ""))
                else:
                    kept.append(h)
            if kept or not inner:
                groups.append({**g, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if want and not kept_desired:
        hooks.setdefault("SessionStart", []).append({"hooks": [desired]})
    if hooks:
        data["hooks"] = hooks
    elif "hooks" in data:
        del data["hooks"]
    if json.dumps(data) == before and exists:
        continue  # 바꿀 것이 없으면 쓰지 않는다(명령이 아닌 곳에만 이름이 든 파일 포함)
    if not data and path == ".codex/hooks.json":
        os.remove(path)  # 키트 항목만 있던 파일: 빈 설정을 남기지 않는다(다른 키·훅이 하나라도 있으면 그대로 쓴다)
        print(f"Removed kit hook entries from {path}; the file held nothing else, so it was removed.")
        continue
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".kit-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    if removed_gate:
        print(f"Removed old approval gate hook entries from {path} (other hooks and settings kept).")
    if want and not kept_desired:
        print(f"Context hook (information only, never blocks) registered in {path} SessionStart (other hooks and settings kept).")
    elif not want:
        print(f"Removed kit hook entries from {path} (other hooks and settings kept).")
PY
  [ "$1" = apply ] && [ "$want" = 1 ] \
    && printf '%s\n' 'Codex gets no kit hook (no trust prompt from the kit). At start, target change or resume, run: python3 .agents/skills/wf-context/context.py inspect'
  return 0
}

# 처음 설치: 키트 소유 경로가 하나라도 있으면 쓰기 전에 멈춘다
install_fresh() {
  local p files skill_dirs
  files=$(owned "$new")
  skill_dirs=$(printf '%s\n' "$files" | awk -F/ '$1==".agents"{print $1"/"$2"/"$3}' | sort -u)
  for p in AGENTS.md CLAUDE.md .claude/skills work "$version_file" $skill_dirs; do
    [ ! -e "$p" ] && [ ! -L "$p" ] || fail "Conflict: $p"
  done
  parents_ok .agents/skills/x .claude/x $files
  kit_hooks check
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
  kit_hooks apply
  printf '%s\n' 'Files installed. Next, in a new session: survey this repository, fill the 4 project-map rows in AGENTS.md (leave 미확인 where no evidence), decide keep/move/remove for existing agent docs, then confirm with one small real request.'
}

# 업데이트: 키트 소유 부분이 설치 당시 그대로일 때만 새 커밋으로 교체하고, 프로젝트 부분은 건드리지 않는다
install_update() {
  local p d stem old old_files new_files changed=''
  [ ! -L "$version_file" ] || fail "$version_file is a symlink; replace it with the plain file it points to"
  [ -f "$version_file" ] || fail "Not installed: $version_file missing"
  old=$(cat "$version_file")
  printf '%s\n' "$old" | grep -qxE '[0-9a-f]{40}' || fail "Invalid version in $version_file: $old"
  kit cat-file -e "$old^{commit}" 2>/dev/null || fail "Installed version $old not found in kit; fetch it first"
  kit merge-base --is-ancestor "$old" "$new" || fail "Kit HEAD $new is not newer than installed $old"
  [ ! -L AGENTS.md ] || fail 'AGENTS.md is a symlink; update the file it points to by hand'
  [ -f AGENTS.md ] && markers_ok AGENTS.md || fail 'AGENTS.md has no single kit region; see README to mark it once'
  kit show "$old:AGENTS.md" | grep -qxF "$begin" || fail "Installed version $old predates kit region; see README to mark it once"
  cmp -s <(region < AGENTS.md) <(kit show "$old:AGENTS.md" | region) || changed="$changed AGENTS.md(kit-region)"
  old_files=$(owned "$old")
  new_files=$(owned "$new")
  parents_ok "$version_file" $old_files $new_files
  for p in $old_files; do
    [ -f "$p" ] && [ ! -L "$p" ] && cmp -s "$p" <(kit show "$old:$p") || changed="$changed $p"
  done
  for p in $new_files; do
    listed "$p" "$old_files" || { [ ! -e "$p" ] && [ ! -L "$p" ]; } || changed="$changed $p(exists)"
  done
  [ -z "$changed" ] || fail "Local change in kit-owned path:$changed. Move project changes to project sections or role skills, then retry."
  kit_hooks check
  # 같은 버전은 소유 부분이 설치 당시 그대로임을 확인한 뒤에만 무변경으로 끝낸다
  if [ "$old" = "$new" ]; then kit_hooks apply; printf 'Already at %s\n' "$new"; return; fi
  # 영역 밖은 바이트 그대로 두고, 권한을 복사한 옆 임시 파일에 명령마다 따로 조립한 뒤 한 번에 바꿔 끼운다
  local b e
  b=$(grep -nxF -- "$begin" AGENTS.md | cut -d: -f1)
  e=$(grep -nxF -- "$end" AGENTS.md | cut -d: -f1)
  assembled=$(mktemp AGENTS.md.kit-XXXXXX)
  cp -p AGENTS.md "$assembled"
  awk -v b="$b" 'NR<b' AGENTS.md > "$assembled"
  kit show "$new:AGENTS.md" | region >> "$assembled"
  tail -n "+$((e + 1))" AGENTS.md >> "$assembled"
  mv "$assembled" AGENTS.md
  assembled=''
  for p in $old_files; do
    listed "$p" "$new_files" && continue
    rm -- "$p"
    # 지운 키트 파이썬 파일이 남긴 바이트코드 캐시(예: wf-design/__pycache__/approval-gate.*.pyc)만 함께 지운다
    d=$(dirname -- "$p")/__pycache__; stem=$(basename -- "$p" .py)
    if [ "$stem" != "$(basename -- "$p")" ] && [ -d "$d" ] && [ ! -L "$d" ]; then
      rm -f -- "$d/$stem".*.pyc; rmdir -- "$d" 2>/dev/null || true
    fi
    rmdir -p -- "$(dirname -- "$p")" 2>/dev/null || true
  done
  for p in $new_files; do
    mkdir -p "$(dirname -- "$p")"
    kit show "$new:$p" > "$p"
  done
  printf '%s\n' "$new" > "$version_file"
  kit_hooks apply
  printf 'Updated %s -> %s. Review the diff and verify skill discovery in a new session.\n' "$old" "$new"
}

if [ "$mode" = update ]; then install_update; else install_fresh; fi
