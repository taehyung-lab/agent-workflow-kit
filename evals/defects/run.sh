#!/usr/bin/env bash
# 결함 사례 한 회: bash evals/defects/run.sh <사례> <review|direct> <키트 커밋> <결과 폴더>
# review: 고정 입력(요청 원문·승인 계획을 기준으로 둔 작업 지도·변경)으로 독립 검토 → 돌려보내면 구현자 교정 1회 → 재검토 1회 → 실제 결과 판정
# direct: 같은 원문·계획을 구현자에게 주고 직접 확인·교정 → 실제 결과 판정. 둘 다 Codex. 판정은 scenarios.py check(결과만 본다).
set -uo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd -P); ev=$(cd "$here/.." && pwd -P); kit=$(cd "$ev/.." && pwd -P)
name=$1 arm=$2 ref=$3 out=$4; mkdir -p "$out"; tag="$name-$arm-$(git -C "$kit" rev-parse --short=7 "$ref")"
# 프로젝트 만들기(키트 커밋 설치)와 Codex 세션은 evals/session.py 가 맡는다(임시 홈·훅 신뢰는 그 안에서 실행기와 같은 규칙으로 정한다).
w=$(mktemp -d)
EVALS_LANG=python python3 -I "$ev/session.py" project "$w/p" "$ref" --setup "$ev/cases/archive-after-correction/setup.sh" --author e e@i --messages base kit
base=$(python3 -I "$ev/verdict.py" snapshot "$w/p")  # 결함을 심기 전 상태(검토의 기준 커밋)
python3 -I "$here/scenarios.py" apply "$name" "$w/p"
python3 -I "$here/scenarios.py" text "$name" request > "$w/req.txt"; python3 -I "$here/scenarios.py" text "$name" plan > "$w/plan.txt"
impl() {  # 구현자 세션 1회(승인 말 포함: v3.0 이하 커밋은 관문이 쓰기를 연다)
  (cd "$w/p" && AWK_GATE_LOG="$out/$tag.hook.log" python3 -I "$ev/session.py" start codex "$w/p" "$1" "$out/$tag.impl$2")
}
review() {  # 독립 검토 1회(고정 입력, 평가 실행기가 검토자 세션을 띄운다). 승인된 계획은 검토하는 동안만 작업 지도의 기준으로 둔다(구현자 세션에는 없다)
  mkdir -p "$w/p/work/defect" && { printf '# 결함 사례\n\n## 기준\n\n'; cat "$w/plan.txt"; printf '\n'; } > "$w/p/work/defect/work.md"
  (cd "$w/p" && python3 -I "$ev/verdict.py" session --tool "$w/p/.agents/skills/wf-verify/verify.py" --harness codex \
    --request "$w/req.txt" --map work/defect/work.md --base "$base" --rounds 2 --log "$out/$tag.review$1.jsonl" 2>> "$out/$tag.err" | tail -1)
  rm -f "$w/p/work/defect/work.md"
}
start=$(date +%s); r1=""; r2=""; returned=0
ctx=$(printf '요청 원문:\n%s\n\n승인된 계획:\n%s' "$(cat "$w/req.txt")" "$(cat "$w/plan.txt")")
if [ "$arm" = review ]; then
  r1=$(review 1); s1=$(printf '%s' "$r1" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
  if [ "$s1" = returned ]; then
    returned=1; reason=$(printf '%s' "$r1" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("final") or d.get("reason",""))')
    impl "$(printf '별도 검토자가 다음 사유로 돌려보냈습니다. 검토자 판단을 그대로 따르지 말고 요청 원문·승인 계획과 대조해 원인 자리(요구 정의·설계·코드·검사)를 고치고, 실제로 확인한 뒤 보고하세요. 진행해 주세요.\n\n%s\n\n검토 사유:\n%s' "$ctx" "$reason")" 1
    r2=$(review 2)
  fi
else
  impl "$(printf '아래 요청을 승인된 계획대로 구현해 둔 상태입니다(아직 커밋 전). 완료라고 하기 전에 요청 원문과 대조해 직접 확인하고, 문제가 있으면 원인 자리(요구 정의·설계·코드·검사)를 고친 뒤 결과를 보고하세요. 진행해 주세요.\n\n%s' "$ctx")" 1
fi
verdict=$(python3 -I "$here/scenarios.py" check "$name" "$w/p"); vrc=$?
printf '%s' "$r1" > "$w/r1.json"; printf '%s' "$r2" > "$w/r2.json"; printf '%s' "$verdict" > "$w/verdict.txt"
python3 - "$out/$tag.json" "$w" "$name" "$arm" "$ref" "$returned" "$vrc" "$(( $(date +%s) - start ))" "$here" <<'PY'
import json, subprocess, sys
from pathlib import Path
o, w, name, arm, ref, returned, vrc, secs, here = sys.argv[1:]
def st(f):
    t = Path(w, f).read_text().strip()
    try: return json.loads(t).get("state") if t else None
    except ValueError: return "parse-error"
kind = subprocess.run(["python3", f"{here}/scenarios.py", "kind", name], capture_output=True, text=True).stdout.strip()
json.dump({"case": name, "kind": kind, "arm": arm, "kit": ref, "review1": st("r1.json"), "review2": st("r2.json"), "returned": returned == "1",
           "final_pass": vrc == "0", "verdict": Path(w, "verdict.txt").read_text(), "seconds": int(secs)}, open(o, "w"), ensure_ascii=False)
PY
cp -R "$w/p" "$out/$tag.files" 2>/dev/null
echo "$tag $verdict"
