#!/usr/bin/env bash
# 코드·검사·표본을 같은 작업 트리에서 고정한 뒤 전체 시험을 그 복사본에서 실행한다.
set -euo pipefail
kitdir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
snapshot=$(mktemp -d)
trap 'rm -rf "$snapshot"' EXIT
# 별도 index를 사용하므로 사용자가 스테이징한 상태는 건드리지 않는다.
export_index="$snapshot/index"
GIT_INDEX_FILE="$export_index" git -C "$kitdir" add -A
tree=$(GIT_INDEX_FILE="$export_index" git -C "$kitdir" write-tree)
head=$(git -C "$kitdir" rev-parse HEAD)
if [ "$tree" = "$(git -C "$kitdir" rev-parse 'HEAD^{tree}')" ]; then
  ref=$head
else
  ref=$(git -C "$kitdir" -c user.name=selftest -c user.email=selftest@invalid commit-tree "$tree" -p "$head" -m selftest-worktree)
fi
git clone -q --no-checkout "$kitdir" "$snapshot/kit"
git -C "$snapshot/kit" checkout -q --detach "$ref"
printf '시험 고정본: commit=%s tree=%s\n' "$ref" "$tree"
cd "$snapshot/kit"
bash evals/selftest-run.sh
