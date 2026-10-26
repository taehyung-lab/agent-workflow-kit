#!/usr/bin/env bash
# install.sh 의 보장을 확인한다: 정상 설치, 충돌·재실행·잘못된 부모·미커밋 키트 거절,
# 업데이트가 키트 소유 부분만 교체하고 프로젝트 부분을 보존하며, 키트 소유 부분의 로컬 변경은 같은 버전에서도 거절하고
# 부모 심링크를 따라 대상 밖에 쓰지 않는지.
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

# 정상 설치: 키트 파일이 원본과 같고, 링크·ignore·버전 기록이 생긴다
t="$tmp/fresh"; mkdir "$t"
if install "$t" \
  && cmp -s "$kit/AGENTS.md" "$t/AGENTS.md" && cmp -s "$kit/CLAUDE.md" "$t/CLAUDE.md" \
  && cmp -s "$kit/.agents/skills/wf-verify/SKILL.md" "$t/.agents/skills/wf-verify/SKILL.md" \
  && cmp -s "$kit/.agents/skills/wf-design/work-template.md" "$t/.agents/skills/wf-design/work-template.md" \
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
  if ! install "$t" && grep -q "Conflict: $p" "$tmp/err" && [ ! -e "$t/.agents/skills/wf-design" ] \
    && { [ -f "$t/$p" ] && [ "$(cat "$t/$p")" = mine ] || [ -f "$t/$p/mine" ]; }; then ok "conflict $p kept"; else ng "conflict $p kept"; fi
done

# 잘못된 부모: .agents 가 심링크거나 파일이면 거절한다
t="$tmp/parent-link"; mkdir -p "$t" "$tmp/elsewhere"; ln -s "$tmp/elsewhere" "$t/.agents"
if ! install "$t" && grep -q 'Invalid parent: .agents' "$tmp/err" && [ -z "$(ls -A "$tmp/elsewhere")" ]; then ok "symlink parent refused"; else ng "symlink parent refused"; fi
t="$tmp/parent-file"; mkdir "$t"; echo x > "$t/.claude"
if ! install "$t" && grep -q 'Invalid parent: .claude' "$tmp/err"; then ok "file parent refused"; else ng "file parent refused"; fi

# 키트 스킬 폴더가 이미 있으면 멈춘다
t="$tmp/conflict-skill"; mkdir -p "$t/.agents/skills/wf-design"
if ! install "$t" && grep -q 'Conflict: .agents/skills/wf-design' "$tmp/err" && [ ! -e "$t/AGENTS.md" ]; then ok "conflict wf dir kept"; else ng "conflict wf dir kept"; fi

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
echo 'local' >> "$tmp/up-skill/.agents/skills/wf-verify/SKILL.md"
mkdir -p "$tmp/up-exists/.agents/skills/wf-new"; echo mine > "$tmp/up-exists/.agents/skills/wf-new/SKILL.md"
{ printf '# 프로젝트 머리말\n\n'; cat "$tmp/up-keep/AGENTS.md"; printf 'tail & \\1 without newline'; } > "$tmp/a" && cat "$tmp/a" > "$tmp/up-keep/AGENTS.md"; chmod 640 "$tmp/up-keep/AGENTS.md"
awk -v b="$begin" '{print} $0==b{print "LOCAL EDIT"}' "$tmp/up-region/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$tmp/up-region/AGENTS.md"
awk -v b="$begin" '{print} $0==b{print "v2 kit line"}' "$kit/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$kit/AGENTS.md"
echo 'v2' >> "$kit/.agents/skills/wf-verify/SKILL.md"
mkdir "$kit/.agents/skills/wf-new"; echo new > "$kit/.agents/skills/wf-new/SKILL.md"
git -C "$kit" rm -q .agents/skills/wf-design/work-template.md
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
  && cmp -s "$kit/.agents/skills/wf-verify/SKILL.md" "$t/.agents/skills/wf-verify/SKILL.md" \
  && [ -f "$t/.agents/skills/wf-new/SKILL.md" ] && [ ! -e "$t/.agents/skills/wf-design/work-template.md" ] \
  && [ -f "$t/.agents/skills/wf-design/SKILL.md" ] && [ "$(cat "$t/.agents/skills/my-role/SKILL.md")" = role ] \
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
t="$tmp/up-same-drift"; mkdir "$t"; install "$t"; echo tampered >> "$t/.agents/skills/wf-verify/SKILL.md"; before=$(snap "$t")
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

printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
