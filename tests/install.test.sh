#!/usr/bin/env bash
# install.sh 의 보장을 확인한다: 정상 설치, 충돌·재실행·잘못된 부모·미커밋 키트 거절,
# 업데이트가 키트 소유 부분만 교체하고 프로젝트 부분을 보존하며, 키트 소유 부분의 로컬 변경은 같은 버전에서도 거절하고
# 부모 심링크를 따라 대상 밖에 쓰지 않는지. 훅: 세션 시작 정보 훅 항목 하나만 더하거나 지우고(다른 훅·설정 보존, 다시 실행해도 그대로),
# 훅 명령은 python3·git 이 없어도 아무것도 내지 않고 0 으로 끝나는지.
# 작업 트리의 키트를 임시 git 저장소로 복사해 커밋 v1·v2를 만들어 시험한다.
set -uo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
pass=0; failed=0
ok() { pass=$((pass+1)); printf 'ok   %s\n' "$1"; }
ng() { failed=$((failed+1)); printf 'FAIL %s\n' "$1"; }
kit="$tmp/kit"
g() { git -C "$kit" -c user.name=t -c user.email=t@t "$@" >/dev/null; }
install() { bash "$kit/install.sh" "$@" >"$tmp/out" 2>"$tmp/err"; }
snap() { (cd "$1" && find . -type f -exec cksum {} + | sort); }

mkdir "$kit"
(cd "$src" && tar cf - --exclude=.git .) | (cd "$kit" && tar xf -)
g init -q; g add -A
# v0: 표시 영역이 없던 이전 방식 키트. v1에서 표시를 되살린다
cp "$kit/AGENTS.md" "$tmp/agents.v1"; grep -vE '^<!-- agent-workflow-kit:(begin|end) -->$' "$tmp/agents.v1" > "$kit/AGENTS.md"
g add -A; g commit -qm v0; v0=$(git -C "$kit" rev-parse HEAD)
cp "$tmp/agents.v1" "$kit/AGENTS.md"; g add -A; g commit -qm v1
v1=$(git -C "$kit" rev-parse HEAD)
begin='<!-- agent-workflow-kit:begin -->'
region() { awk -v b="$begin" -v e='<!-- agent-workflow-kit:end -->' '$0==b{f=1} f{print} $0==e{f=0}'; }

# 정상 설치: 키트 파일이 원본과 같고, 링크·ignore·버전 기록이 생긴다
t="$tmp/fresh"; mkdir "$t"
if install "$t" \
  && cmp -s "$kit/AGENTS.md" "$t/AGENTS.md" && cmp -s "$kit/CLAUDE.md" "$t/CLAUDE.md" \
  && cmp -s "$kit/.agents/skills/guide.md" "$t/.agents/skills/guide.md" \
  && cmp -s "$kit/.agents/skills/wf-verify/verify.py" "$t/.agents/skills/wf-verify/verify.py" \
  && [ "$(readlink "$t/.claude/skills")" = "../.agents/skills" ] \
  && grep -qxF '/work/' "$t/.gitignore" && [ "$(cat "$t/.agents/agent-workflow-kit.version")" = "$v1" ] \
  && grep -qxF "$begin" "$t/AGENTS.md"; then ok "fresh install"; else ng "fresh install"; fi

# 재실행 거절: 두 번째 설치는 멈추고 파일을 바꾸지 않는다
before=$(snap "$t")
if ! install "$t" && grep -q 'Conflict' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "rerun refused"; else ng "rerun refused"; fi

# 충돌 보존: 기존 AGENTS.md·CLAUDE.md·.claude/skills 중 하나라도 있으면 멈추고 그대로 둔다
for p in AGENTS.md CLAUDE.md .claude/skills; do
  t="$tmp/conflict-${p//\//_}"; mkdir -p "$t/$(dirname "$p")"
  if [ "$p" = .claude/skills ]; then mkdir "$t/$p"; touch "$t/$p/mine"; else echo mine > "$t/$p"; fi
  if ! install "$t" && grep -q "Conflict: $p" "$tmp/err" && [ ! -e "$t/.agents/skills/wf-verify" ] \
    && { [ -f "$t/$p" ] && [ "$(cat "$t/$p")" = mine ] || [ -f "$t/$p/mine" ]; }; then ok "conflict $p kept"; else ng "conflict $p kept"; fi
done

# 잘못된 부모: .agents 가 심링크거나 파일이면 거절한다
t="$tmp/parent-link"; mkdir -p "$t" "$tmp/elsewhere"; ln -s "$tmp/elsewhere" "$t/.agents"
if ! install "$t" && grep -q 'Invalid parent: .agents' "$tmp/err" && [ -z "$(ls -A "$tmp/elsewhere")" ]; then ok "symlink parent refused"; else ng "symlink parent refused"; fi
t="$tmp/parent-file"; mkdir "$t"; echo x > "$t/.claude"
if ! install "$t" && grep -q 'Invalid parent: .claude' "$tmp/err"; then ok "file parent refused"; else ng "file parent refused"; fi

# 키트 스킬 폴더가 이미 있으면 멈춘다
t="$tmp/conflict-skill"; mkdir -p "$t/.agents/skills/wf-verify"
if ! install "$t" && grep -q 'Conflict: .agents/skills/wf-verify' "$tmp/err" && [ ! -e "$t/AGENTS.md" ]; then ok "conflict wf dir kept"; else ng "conflict wf dir kept"; fi

# git이 아니거나 다른 저장소 안에 들어 있는 키트는 거절한다
t="$tmp/nogit"; mkdir -p "$t" "$tmp/plain"; git -C "$kit" archive HEAD | tar xf - -C "$tmp/plain"
if ! bash "$tmp/plain/install.sh" "$t" 2>"$tmp/err" && grep -q 'Kit must be a git checkout' "$tmp/err" && [ -z "$(ls -A "$t")" ]; then ok "non-git kit refused"; else ng "non-git kit refused"; fi
mkdir -p "$tmp/outer/vendor"; git -C "$kit" archive HEAD | tar xf - -C "$tmp/outer/vendor"
git -C "$tmp/outer" init -q; git -C "$tmp/outer" add -A; git -C "$tmp/outer" -c user.name=t -c user.email=t@t commit -qm o
t="$tmp/subdir"; mkdir "$t"
if ! bash "$tmp/outer/vendor/install.sh" "$t" 2>"$tmp/err" && grep -q 'root of its own' "$tmp/err" && [ -z "$(ls -A "$t")" ]; then ok "nested kit refused"; else ng "nested kit refused"; fi

# 쓰기 도중 실패하면 부분 설치 안내를 낸다
t="$tmp/readonly"; mkdir -p "$t/.agents/skills"; chmod 555 "$t/.agents/skills"
if ! install "$t" && grep -q 'partial files may remain' "$tmp/err"; then ok "partial-write notice"; else ng "partial-write notice"; fi
chmod 755 "$t/.agents/skills"

# 미커밋 키트 거절: 버전 파일로 재현할 수 없는 설치는 하지 않는다
t="$tmp/dirty"; mkdir "$t"; echo x >> "$kit/README.md"
if ! install "$t" && grep -q 'uncommitted' "$tmp/err" && [ -z "$(ls -A "$t")" ]; then ok "dirty kit refused"; else ng "dirty kit refused"; fi
git -C "$kit" checkout -q -- README.md

# 업데이트 준비: v1 설치본 세 개(보존·영역 변경·스킬 변경)에 프로젝트 내용을 넣고, 키트 v2를 만든다
for n in keep plain region skill exists; do
  t="$tmp/up-$n"; mkdir "$t"; install "$t"
  sed -i.bak 's/^- 제품 원문·사용자 결정·결정권자: 미확인$/- 제품 원문·사용자 결정·결정권자: docs\/product.md/' "$t/AGENTS.md" && rm "$t/AGENTS.md.bak"
  printf '\n## 프로젝트 약속\n\n- 이 저장소만의 약속\n' >> "$t/AGENTS.md"
  mkdir -p "$t/.agents/skills/my-role"; echo role > "$t/.agents/skills/my-role/SKILL.md"
done
echo 'local' >> "$tmp/up-skill/.agents/skills/guide.md"
mkdir -p "$tmp/up-exists/.agents/skills/wf-new"; echo mine > "$tmp/up-exists/.agents/skills/wf-new/SKILL.md"
{ printf '# 프로젝트 머리말\n\n'; cat "$tmp/up-keep/AGENTS.md"; printf 'tail & \\1 without newline'; } > "$tmp/a" && cat "$tmp/a" > "$tmp/up-keep/AGENTS.md"; chmod 640 "$tmp/up-keep/AGENTS.md"
awk -v b="$begin" '{print} $0==b{print "LOCAL EDIT"}' "$tmp/up-region/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$tmp/up-region/AGENTS.md"
awk -v b="$begin" '{print} $0==b{print "v2 kit line"}' "$kit/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$kit/AGENTS.md"
echo 'v2' >> "$kit/.agents/skills/guide.md"
mkdir "$kit/.agents/skills/wf-new"; echo new > "$kit/.agents/skills/wf-new/SKILL.md"
git -C "$kit" rm -q .agents/skills/README.md
mkdir "$kit/.agents/skills/wf-old"; echo old > "$kit/.agents/skills/wf-old/SKILL.md"
g add -A; g commit -qm v2
v2=$(git -C "$kit" rev-parse HEAD)

# 업데이트 보존: 키트 영역·키트 스킬은 v2가 되고, 지도·프로젝트 절·역할 스킬은 그대로다
t="$tmp/up-keep"
if install --update "$t" && [ ! -s "$tmp/err" ] \
  && [ "$(head -n 2 "$t/AGENTS.md")" = "$(printf '# 프로젝트 머리말\n')" ] \
  && grep -qxF 'v2 kit line' "$t/AGENTS.md" \
  && grep -qxF -- '- 제품 원문·사용자 결정·결정권자: docs/product.md' "$t/AGENTS.md" \
  && grep -qxF -- '- 이 저장소만의 약속' "$t/AGENTS.md" \
  && cmp -s "$kit/.agents/skills/guide.md" "$t/.agents/skills/guide.md" \
  && [ -f "$t/.agents/skills/wf-new/SKILL.md" ] && [ ! -e "$t/.agents/skills/README.md" ] \
  && [ -f "$t/.agents/skills/wf-verify/verify.py" ] && [ "$(cat "$t/.agents/skills/my-role/SKILL.md")" = role ] \
  && [ "$(cat "$t/.agents/agent-workflow-kit.version")" = "$v2" ] \
  && [ "$(grep -cxF "$begin" "$t/AGENTS.md")" = 1 ] \
  && [ "$(tail -c 25 "$t/AGENTS.md")" = 'tail & \1 without newline' ] \
  && [ "$(ls -l "$t/AGENTS.md" | cut -c1-10)" = '-rw-r-----' ]; then ok "update keeps project parts"; else ng "update keeps project parts"; fi

# 조립 도중 실패하면 AGENTS.md를 그대로 두고 임시 파일도 남기지 않는다
t="$tmp/up-plain"; mkdir -p "$tmp/shim"; printf '#!/bin/sh\nexit 1\n' > "$tmp/shim/tail"; chmod +x "$tmp/shim/tail"
before=$(snap "$t")
if ! PATH="$tmp/shim:$PATH" install --update "$t" && grep -q 'partial files may remain' "$tmp/err" \
  && [ "$(snap "$t")" = "$before" ]; then ok "failed assembly keeps AGENTS.md"; else ng "failed assembly keeps AGENTS.md"; fi

# 마지막 바꿔 끼우기가 실패해도 AGENTS.md는 비지 않는다
mkdir -p "$tmp/shim-mv"; printf '#!/bin/sh\nexit 1\n' > "$tmp/shim-mv/mv"; chmod +x "$tmp/shim-mv/mv"
if ! PATH="$tmp/shim-mv:$PATH" install --update "$t" && [ "$(snap "$t")" = "$before" ]; then ok "failed replace keeps AGENTS.md"; else ng "failed replace keeps AGENTS.md"; fi

# 설치 그대로(영역이 첫 줄)인 대상도 경고 없이 업데이트된다
t="$tmp/up-plain"
if install --update "$t" && [ ! -s "$tmp/err" ] && grep -qxF 'v2 kit line' "$t/AGENTS.md" && [ "$(head -n 1 "$t/AGENTS.md")" = "$begin" ] \
  && [ -z "$(find "$t" -name 'AGENTS.md.kit-*')" ]; then ok "update quiet when region starts file"; else ng "update quiet when region starts file"; fi
t="$tmp/up-keep"

# 키트에서 지운 스킬은 빈 폴더까지 정리한다(v3에서 wf-old 삭제)
git -C "$kit" rm -q -r .agents/skills/wf-old; g commit -qm v3
if install --update "$t" && [ ! -e "$t/.agents/skills/wf-old" ] && [ -d "$t/.agents/skills/my-role" ]; then ok "update removes dropped skill dir"; else ng "update removes dropped skill dir"; fi

# 더 오래된 키트 커밋으로는 내려가지 않는다
git -C "$kit" checkout -q "$v2"; before=$(snap "$t")
if ! install --update "$t" && grep -q 'not newer' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses downgrade"; else ng "update refuses downgrade"; fi
git -C "$kit" checkout -q -; v3=$(git -C "$kit" rev-parse HEAD)

# 같은 버전 재실행은 아무것도 바꾸지 않는다
before=$(snap "$t")
if install --update "$t" && grep -q 'Already at' "$tmp/out" && [ "$(snap "$t")" = "$before" ]; then ok "update idempotent"; else ng "update idempotent"; fi

# 키트 소유 부분의 로컬 변경은 덮어쓰지 않고 멈춘다
for n in region skill exists; do
  t="$tmp/up-$n"; before=$(snap "$t")
  if ! install --update "$t" && grep -q 'Local change in kit-owned path' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses local $n change"; else ng "update refuses local $n change"; fi
done

# AGENTS.md가 심링크면 링크를 일반 파일로 바꾸지 않고 멈춘다
t="$tmp/up-link"; mkdir "$t"; git -C "$kit" checkout -q "$v2"; install "$t"; git -C "$kit" checkout -q -
mkdir "$t/docs"; mv "$t/AGENTS.md" "$t/docs/AGENTS.md"; ln -s docs/AGENTS.md "$t/AGENTS.md"; before=$(snap "$t")
if ! install --update "$t" && grep -q 'symlink' "$tmp/err" && [ -L "$t/AGENTS.md" ] && [ "$(snap "$t")" = "$before" ]; then ok "update refuses symlinked AGENTS.md"; else ng "update refuses symlinked AGENTS.md"; fi

# 표시 없는(이전 방식) 설치본은 멈춘다
t="$tmp/up-nomark"; mkdir -p "$t/.agents"; grep -vxF "$begin" "$kit/AGENTS.md" > "$t/AGENTS.md"; echo "$v1" > "$t/.agents/agent-workflow-kit.version"
before=$(snap "$t")
if ! install --update "$t" && grep -q 'no single kit region' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses unmarked AGENTS.md"; else ng "update refuses unmarked AGENTS.md"; fi

# 버전 파일이 쓸 수 없는 값이면 멈춘다: 키트에 없는 커밋, sha가 아닌 값, 표시 이전 커밋
for case in "0000000000000000000000000000000000000000|not found in kit" "HEAD~1|Invalid version" "$v0|predates kit region"; do
  bad=${case%%|*}; want=${case#*|}
  t="$tmp/up-bad"; rm -rf "$t"; mkdir "$t"; install "$t"; echo "$bad" > "$t/.agents/agent-workflow-kit.version"; before=$(snap "$t")
  if ! install --update "$t" && grep -q "$want" "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses version: $want"; else ng "update refuses version: $want"; fi
done

# 같은 버전이어도 키트 소유 부분의 로컬 변경은 "이미 최신"으로 넘기지 않고 멈춘다
t="$tmp/up-same-drift"; mkdir "$t"; install "$t"; echo tampered >> "$t/.agents/skills/guide.md"; before=$(snap "$t")
if ! install --update "$t" && grep -q 'Local change in kit-owned path' "$tmp/err" && ! grep -q 'Already at' "$tmp/out" \
  && [ "$(snap "$t")" = "$before" ]; then ok "same-version update refuses local change"; else ng "same-version update refuses local change"; fi

# 업데이트도 대상 밖으로 쓰지 않는다: .agents/skills 또는 키트 스킬 폴더가 심링크면 멈추고 링크 대상을 건드리지 않는다
for link in .agents/skills .agents/skills/wf-verify; do
  t="$tmp/up-parent-${link//\//_}"; out="$tmp/outside-${link//\//_}"; rm -rf "$t" "$out"; mkdir "$t"
  git -C "$kit" checkout -q "$v2"; install "$t"; git -C "$kit" checkout -q -
  mv "$t/$link" "$out"; ln -s "$out" "$t/$link"; before=$(snap "$out")
  if ! install --update "$t" && grep -q 'Invalid parent' "$tmp/err" && [ -L "$t/$link" ] \
    && [ "$(snap "$out")" = "$before" ]; then ok "update refuses symlinked $link"; else ng "update refuses symlinked $link"; fi
done

# 버전 파일 자체가 심링크면 링크를 따라 대상 밖을 고치지 않고 멈춘다
t="$tmp/up-version-link"; out="$tmp/outside-version"; rm -rf "$t"; mkdir "$t"
git -C "$kit" checkout -q "$v2"; install "$t"; git -C "$kit" checkout -q -
mv "$t/.agents/agent-workflow-kit.version" "$out"; ln -s "$out" "$t/.agents/agent-workflow-kit.version"; before=$(cat "$out")
if ! install --update "$t" && grep -q 'symlink' "$tmp/err" && [ -L "$t/.agents/agent-workflow-kit.version" ] \
  && [ "$(cat "$out")" = "$before" ]; then ok "update refuses symlinked version file"; else ng "update refuses symlinked version file"; fi

# 훅 항목 확인 도구: 파일 $1 에서 키트 정보 훅(wf-context)을 빼고 남은 내용이 JSON $2 와 같고, 키트 항목이 SessionStart 에 정확히 하나인지
kit_hook_ok() { python3 -I - "$1" "$2" "${3:-1}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); want = json.loads(sys.argv[2]); n = int(sys.argv[3])
kit = [h for g in d.get("hooks", {}).get("SessionStart", []) for h in g.get("hooks", []) if "wf-context/context.py" in str(h.get("command", ""))]
assert len(kit) == n, kit
assert all("approval-gate" not in json.dumps(h) for h in kit) and all(h.get("timeout") == 10 for h in kit)
hooks = d.get("hooks", {})
for ev in list(hooks):
    hooks[ev] = [g for g in ({**g, "hooks": [h for h in g.get("hooks", []) if "wf-context/context.py" not in str(h.get("command", ""))]} for g in hooks[ev]) if g["hooks"]]
    if not hooks[ev]: del hooks[ev]
if not hooks: d.pop("hooks", None)
assert d == want, (d, want)
PY
}

# 훅: 처음 설치는 정보 훅 항목 하나만 더하고, 기존 훅·권한 설정은 그대로 둔다(파일 쓰기·명령 허용은 각 도구의 권한 설정이 맡는다)
t="$tmp/hooks-fresh"; mkdir -p "$t/.claude" "$t/.codex"
printf '{"permissions": {"defaultMode": "plan"},\n "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}' > "$t/.claude/settings.json"
printf '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"my-stop.sh"}]}]}}' > "$t/.codex/hooks.json"
t2="$tmp/hooks-none"; mkdir "$t2"
if install "$t" && grep -q 'information only' "$tmp/out" && install "$t2" \
  && kit_hook_ok "$t/.claude/settings.json" '{"permissions": {"defaultMode": "plan"}, "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}' \
  && kit_hook_ok "$t/.codex/hooks.json" '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-stop.sh"}]}]}}' \
  && kit_hook_ok "$t2/.claude/settings.json" '{}' && kit_hook_ok "$t2/.codex/hooks.json" '{}' \
  && grep -q 'CLAUDE_PROJECT_DIR' "$t2/.claude/settings.json" && ! grep -q 'CLAUDE_PROJECT_DIR' "$t2/.codex/hooks.json" \
  && [ ! -e "$t2/.agents/skills/wf-design" ] && [ -f "$t2/.agents/skills/wf-context/context.py" ]; then ok "fresh install adds only the SessionStart information hook and keeps existing hooks and permissions"; else ng "fresh install adds only the SessionStart information hook and keeps existing hooks and permissions"; cat "$tmp/err"; fi

# 훅 명령: python3·git 이 없거나 키트 파일이 없어도 아무것도 내지 않고 0. 있으면 정보 JSON 을 내고 0(git 저장소가 아니어도)
cmd_of() { python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(h["command"] for g in d["hooks"]["SessionStart"] for h in g["hooks"] if "wf-context" in h["command"]))' "$1"; }
ccmd=$(cmd_of "$t2/.claude/settings.json"); xcmd=$(cmd_of "$t2/.codex/hooks.json"); mkdir -p "$tmp/empty-path"
o1=$(cd "$t2" && echo '{}' | CLAUDE_PROJECT_DIR="$t2" PATH="$tmp/empty-path" /bin/sh -c "$ccmd"); r1=$?
o2=$(cd "$t2" && echo '{}' | PATH="$tmp/empty-path" /bin/sh -c "$xcmd"); r2=$?
o3=$(cd "$tmp" && echo '{}' | CLAUDE_PROJECT_DIR="$tmp/no-such" /bin/sh -c "$ccmd"); r3=$?
o4=$(cd "$t2" && echo '{"hook_event_name": "SessionStart", "source": "resume"}' | CLAUDE_PROJECT_DIR="$t2" /bin/sh -c "$ccmd"); r4=$?
o5=$(cd "$t2" && echo '{}' | /bin/sh -c "$xcmd"); r5=$?
if [ "$r1$r2$r3$r4$r5" = 00000 ] && [ -z "$o1$o2$o3" ] \
  && printf '%s' "$o4" | python3 -I -c 'import json,sys; d=json.load(sys.stdin)["hookSpecificOutput"]; assert d["hookEventName"]=="SessionStart" and "실경로" in d["additionalContext"] and "resume" in d["additionalContext"]' \
  && printf '%s' "$o5" | grep -q '실경로'; then ok "hook command: silent exit 0 without python3/git/kit file; information JSON exit 0 otherwise"; else ng "hook command exit/output: $r1$r2$r3$r4$r5 [$o1|$o2|$o3]"; fi

# 훅 설정 파일이 깨졌거나 심링크면 아무것도 쓰기 전에 멈춘다
t="$tmp/hooks-broken"; mkdir -p "$t/.codex"; printf '{"hooks": ' > "$t/.codex/hooks.json"
if ! install "$t" && grep -q 'Could not read hook settings' "$tmp/err" && [ ! -e "$t/AGENTS.md" ] && [ "$(cat "$t/.codex/hooks.json")" = '{"hooks": ' ]; then ok "broken hook settings refused before writing"; else ng "broken hook settings refused before writing"; fi
t="$tmp/hooks-link"; mkdir -p "$t/.claude"; echo '{}' > "$tmp/outside-settings.json"; ln -s "$tmp/outside-settings.json" "$t/.claude/settings.json"
if ! install "$t" && grep -q 'Could not read hook settings' "$tmp/err" && [ ! -e "$t/AGENTS.md" ] && [ "$(cat "$tmp/outside-settings.json")" = '{}' ]; then ok "symlinked hook settings refused before writing"; else ng "symlinked hook settings refused before writing"; fi

# v3.0.0 → 이 커밋 업그레이드: v3.0.0 설치기가 등록한 관문 훅 항목만 지우고, 프로젝트의 다른 훅·설정은 그대로 둔다.
# 실제 v3.0.0 태그의 키트로 설치한 뒤(그 설치기가 훅을 등록), 같은 저장소에서 지금 작업 트리를 다음 커밋으로 만들어 --update 한다.
old_ref=${KIT_OLD_REF:-v3.0.0}
if ! git -C "$src" rev-parse -q --verify "$old_ref^{commit}" >/dev/null; then
  ng "upgrade from $old_ref: tag not found in kit checkout (fetch tags, e.g. git fetch --tags)"
else
  ok_kit="$tmp/kit-old"; mkdir "$ok_kit"
  gk() { git -C "$ok_kit" -c user.name=t -c user.email=t@t "$@" >/dev/null; }
  git -C "$src" archive "$old_ref" | tar xf - -C "$ok_kit"; gk init -q; gk add -A; gk commit -qm old
  t="$tmp/upgrade"; mkdir -p "$t/.claude" "$t/.codex"
  cat > "$t/.claude/settings.json" <<'JSON'
{
  "permissions": {"allow": ["Bash(pnpm test)"]},
  "hooks": {
    "PostToolUse": [{"matcher": "^(Edit|Write)$", "hooks": [{"type": "command", "command": "node \"$CLAUDE_PROJECT_DIR/scripts/format/edited.mjs\" --hook", "timeout": 60}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}, {"type": "command", "command": "python3 old/approval-gate.py pre"}]}]
  },
  "enabledPlugins": {"superpowers@claude-plugins-official": false}
}
JSON
  printf '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-stop.sh"}]}]}}' > "$t/.codex/hooks.json"
  bash "$ok_kit/install.sh" "$t" >"$tmp/out" 2>"$tmp/err"
  mkdir -p "$t/.agents/skills/wf-design/__pycache__"; echo pyc > "$t/.agents/skills/wf-design/__pycache__/approval-gate.cpython-314.pyc"
  gates() { grep -c 'approval-gate' "$1" || true; }
  if [ "$(gates "$t/.claude/settings.json")" = 3 ] && [ "$(gates "$t/.codex/hooks.json")" = 3 ]; then ok "fixture: $old_ref installer registered its gate hooks"; else ng "fixture: $old_ref installer registered its gate hooks"; fi
  # 지금 작업 트리를 다음 커밋으로 만든다(위 시험이 바꾼 임시 키트가 아니라 원본 작업 트리에서 복사)
  (cd "$ok_kit" && git ls-files -z | xargs -0 rm -f) && (cd "$src" && tar cf - --exclude=.git --exclude=__pycache__ .) | (cd "$ok_kit" && tar xf -)
  gk add -A; gk commit -qm new; new_sha=$(git -C "$ok_kit" rev-parse HEAD)
  settings_ok() { python3 -I -c 'import json,sys
c = json.load(open(sys.argv[1])); x = json.load(open(sys.argv[2]))
h = c["hooks"]
assert c["enabledPlugins"] == {"superpowers@claude-plugins-official": False} and c["permissions"] == {"allow": ["Bash(pnpm test)"]}
assert h["PostToolUse"] == [{"matcher": "^(Edit|Write)$", "hooks": [{"type": "command", "command": "node \"$CLAUDE_PROJECT_DIR/scripts/format/edited.mjs\" --hook", "timeout": 60}]}]
assert h["PreToolUse"] == [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]
assert set(h) == {"PostToolUse", "PreToolUse", "SessionStart"} and len(h["SessionStart"]) == 1 and "wf-context/context.py" in h["SessionStart"][0]["hooks"][0]["command"]
assert x["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "my-stop.sh"}]}] and set(x["hooks"]) == {"Stop", "SessionStart"}
assert "wf-context/context.py" in x["hooks"]["SessionStart"][0]["hooks"][0]["command"]' "$t/.claude/settings.json" "$t/.codex/hooks.json"; }
  if bash "$ok_kit/install.sh" --update "$t" >"$tmp/out" 2>"$tmp/err" \
    && [ "$(gates "$t/.claude/settings.json")" = 0 ] && [ "$(gates "$t/.codex/hooks.json")" = 0 ] && settings_ok \
    && grep -q 'Removed old approval gate hook entries from .claude/settings.json' "$tmp/out" \
    && [ ! -e "$t/.agents/skills/wf-design" ] && [ -f "$t/.agents/skills/wf-verify/verify.py" ] \
    && [ "$(cat "$t/.agents/agent-workflow-kit.version")" = "$new_sha" ] \
    && cmp -s <(region < "$t/AGENTS.md") <(region < "$src/AGENTS.md"); then ok "upgrade from $old_ref removes only gate hook entries, adds the information hook, keeps formatter hook, same-group hook, plugins, permissions"; else ng "upgrade from $old_ref removes only gate hook entries, adds the information hook, keeps formatter hook, same-group hook, plugins, permissions"; cat "$tmp/err"; fi
  before=$(snap "$t")
  if bash "$ok_kit/install.sh" --update "$t" >"$tmp/out" 2>&1 && grep -q 'Already at' "$tmp/out" && [ "$(snap "$t")" = "$before" ]; then ok "upgrade rerun changes nothing"; else ng "upgrade rerun changes nothing"; fi

  # 관문 항목이 든 설정 파일이 깨졌으면 아무것도 쓰기 전에 멈춘다
  t="$tmp/upgrade-bad"; mkdir "$t"
  git -C "$ok_kit" checkout -q HEAD~1; bash "$ok_kit/install.sh" "$t" >/dev/null 2>&1; git -C "$ok_kit" checkout -q -
  printf '{"hooks": {"Stop": [{"hooks": [{"command": "python3 x/approval-gate.py stop"}]}]}' > "$t/.codex/hooks.json"
  before=$(snap "$t")
  if ! bash "$ok_kit/install.sh" --update "$t" >"$tmp/out" 2>"$tmp/err" && grep -q 'Could not read hook settings' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "broken settings with gate entries refused before writing"; else ng "broken settings with gate entries refused before writing"; fi
fi

# v3.1.0(훅 없음) → 이 커밋: 정보 훅만 더하고 프로젝트의 포맷터 훅·플러그인 설정은 그대로. 다시 실행하면 아무것도 바꾸지 않는다.
# 이어서 정보 훅 파일을 뺀 다음 키트 커밋으로 업데이트하면(훅 제거 경로) 키트 항목만 지우고 다른 훅·설정은 그대로 둔다.
if git -C "$src" rev-parse -q --verify "v3.1.0^{commit}" >/dev/null; then
  k31="$tmp/kit-31"; mkdir "$k31"
  g31() { git -C "$k31" -c user.name=t -c user.email=t@t "$@" >/dev/null; }
  git -C "$src" archive v3.1.0 | tar xf - -C "$k31"; g31 init -q; g31 add -A; g31 commit -qm v31
  t="$tmp/up31"; mkdir -p "$t/.claude"
  printf '{"hooks": {"PostToolUse": [{"matcher": "^(Edit|Write)$", "hooks": [{"type": "command", "command": "fmt.sh", "timeout": 60}]}]}, "enabledPlugins": {"p@x": false}}' > "$t/.claude/settings.json"
  bash "$k31/install.sh" "$t" >/dev/null 2>&1
  keep31='{"hooks": {"PostToolUse": [{"matcher": "^(Edit|Write)$", "hooks": [{"type": "command", "command": "fmt.sh", "timeout": 60}]}]}, "enabledPlugins": {"p@x": false}}'
  [ ! -e "$t/.codex" ] && kit_hook_ok "$t/.claude/settings.json" "$keep31" 0 && ok "fixture: v3.1.0 installer wrote no hooks" || ng "fixture: v3.1.0 installer wrote no hooks"
  (cd "$k31" && git ls-files -z | xargs -0 rm -f) && (cd "$src" && tar cf - --exclude=.git --exclude=__pycache__ .) | (cd "$k31" && tar xf -)
  g31 add -A; g31 commit -qm new
  if bash "$k31/install.sh" --update "$t" >"$tmp/out" 2>"$tmp/err" && kit_hook_ok "$t/.claude/settings.json" "$keep31" && kit_hook_ok "$t/.codex/hooks.json" '{}' \
    && grep -q 'information only' "$tmp/out"; then ok "upgrade from v3.1.0 adds only the information hook, keeps formatter hook and plugins"; else ng "upgrade from v3.1.0 adds only the information hook, keeps formatter hook and plugins"; cat "$tmp/err"; fi
  before=$(snap "$t")
  if bash "$k31/install.sh" --update "$t" >"$tmp/out" 2>&1 && grep -q 'Already at' "$tmp/out" && [ "$(snap "$t")" = "$before" ]; then ok "hook update rerun changes nothing"; else ng "hook update rerun changes nothing"; fi
  # 사용자가 같은 SessionStart 에 자기 훅을 더해도 다시 실행이 그 훅·순서를 바꾸지 않는다
  python3 -I -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["hooks"]["SessionStart"].append({"matcher": "startup", "hooks": [{"type": "command", "command": "my-start.sh"}]}); json.dump(d, open(p, "w"))' "$t/.claude/settings.json"
  before=$(snap "$t")
  if bash "$k31/install.sh" --update "$t" >"$tmp/out" 2>&1 && [ "$(snap "$t")" = "$before" ]; then ok "rerun keeps a user SessionStart hook next to the kit entry untouched"; else ng "rerun keeps a user SessionStart hook next to the kit entry untouched"; fi
  git -C "$k31" rm -q -r .agents/skills/wf-context; g31 commit -qm drop-context
  if bash "$k31/install.sh" --update "$t" >"$tmp/out" 2>"$tmp/err" && [ ! -e "$t/.agents/skills/wf-context" ] \
    && kit_hook_ok "$t/.claude/settings.json" "$(python3 -I -c 'import json,sys; d=json.loads(sys.argv[1]); d["hooks"]["SessionStart"]=[{"matcher": "startup", "hooks": [{"type": "command", "command": "my-start.sh"}]}]; print(json.dumps(d))' "$keep31")" 0 \
    && kit_hook_ok "$t/.codex/hooks.json" '{}' 0 && grep -q 'Removed kit hook entries' "$tmp/out"; then ok "update to a kit without the inspector removes only kit hook entries (user hooks, formatter, plugins kept)"; else ng "update to a kit without the inspector removes only kit hook entries (user hooks, formatter, plugins kept)"; cat "$tmp/err"; fi
else
  ng "upgrade from v3.1.0: tag not found in kit checkout (fetch tags, e.g. git fetch --tags)"
fi

printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
