#!/usr/bin/env bash
# install.sh 의 보장을 확인한다: 정상 설치, 충돌·재실행·잘못된 부모·미커밋 키트 거절,
# 업데이트가 키트 소유 부분만 교체하고 프로젝트 부분을 보존하며, 키트 소유 부분의 로컬 변경은 거절하는지.
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
g init -q; g add -A; g commit -qm v1
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

# 미커밋 키트 거절: 버전 파일로 재현할 수 없는 설치는 하지 않는다
t="$tmp/dirty"; mkdir "$t"; echo x >> "$kit/README.md"
if ! install "$t" && grep -q 'uncommitted' "$tmp/err" && [ -z "$(ls -A "$t")" ]; then ok "dirty kit refused"; else ng "dirty kit refused"; fi
git -C "$kit" checkout -q -- README.md

# 업데이트 준비: v1 설치본 세 개(보존·영역 변경·스킬 변경)에 프로젝트 내용을 넣고, 키트 v2를 만든다
for n in keep region skill; do
  t="$tmp/up-$n"; mkdir "$t"; install "$t"
  sed -i.bak 's/^- 제품 원문·사용자 결정·결정권자: 미확인$/- 제품 원문·사용자 결정·결정권자: docs\/product.md/' "$t/AGENTS.md" && rm "$t/AGENTS.md.bak"
  printf '\n## 프로젝트 약속\n\n- 이 저장소만의 약속\n' >> "$t/AGENTS.md"
  mkdir -p "$t/.agents/skills/my-role"; echo role > "$t/.agents/skills/my-role/SKILL.md"
done
echo 'local' >> "$tmp/up-skill/.agents/skills/wf-verify/SKILL.md"
awk -v b="$begin" '{print} $0==b{print "LOCAL EDIT"}' "$tmp/up-region/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$tmp/up-region/AGENTS.md"
awk -v b="$begin" '{print} $0==b{print "v2 kit line"}' "$kit/AGENTS.md" > "$tmp/a" && mv "$tmp/a" "$kit/AGENTS.md"
echo 'v2' >> "$kit/.agents/skills/wf-verify/SKILL.md"
mkdir "$kit/.agents/skills/wf-new"; echo new > "$kit/.agents/skills/wf-new/SKILL.md"
git -C "$kit" rm -q .agents/skills/wf-design/work-template.md
g add -A; g commit -qm v2
v2=$(git -C "$kit" rev-parse HEAD)

# 업데이트 보존: 키트 영역·키트 스킬은 v2가 되고, 지도·프로젝트 절·역할 스킬은 그대로다
t="$tmp/up-keep"
if install --update "$t" \
  && grep -qxF 'v2 kit line' "$t/AGENTS.md" \
  && grep -qxF -- '- 제품 원문·사용자 결정·결정권자: docs/product.md' "$t/AGENTS.md" \
  && grep -qxF -- '- 이 저장소만의 약속' "$t/AGENTS.md" \
  && cmp -s "$kit/.agents/skills/wf-verify/SKILL.md" "$t/.agents/skills/wf-verify/SKILL.md" \
  && [ -f "$t/.agents/skills/wf-new/SKILL.md" ] && [ ! -e "$t/.agents/skills/wf-design/work-template.md" ] \
  && [ -f "$t/.agents/skills/wf-design/SKILL.md" ] && [ "$(cat "$t/.agents/skills/my-role/SKILL.md")" = role ] \
  && [ "$(cat "$t/.agents/agent-workflow-kit.version")" = "$v2" ] \
  && [ "$(grep -cxF "$begin" "$t/AGENTS.md")" = 1 ]; then ok "update keeps project parts"; else ng "update keeps project parts"; fi

# 같은 버전 재실행은 아무것도 바꾸지 않는다
before=$(snap "$t")
if install --update "$t" && grep -q 'Already at' "$tmp/out" && [ "$(snap "$t")" = "$before" ]; then ok "update idempotent"; else ng "update idempotent"; fi

# 키트 소유 부분의 로컬 변경은 덮어쓰지 않고 멈춘다
for n in region skill; do
  t="$tmp/up-$n"; before=$(snap "$t")
  if ! install --update "$t" && grep -q 'Local change in kit-owned path' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses local $n change"; else ng "update refuses local $n change"; fi
done

# 표시 없는(이전 방식) 설치본은 멈춘다
t="$tmp/up-nomark"; mkdir -p "$t/.agents"; grep -vxF "$begin" "$kit/AGENTS.md" > "$t/AGENTS.md"; echo "$v1" > "$t/.agents/agent-workflow-kit.version"
before=$(snap "$t")
if ! install --update "$t" && grep -q 'no single kit region' "$tmp/err" && [ "$(snap "$t")" = "$before" ]; then ok "update refuses unmarked AGENTS.md"; else ng "update refuses unmarked AGENTS.md"; fi

printf '%d passed, %d failed\n' "$pass" "$failed"
[ "$failed" -eq 0 ]
