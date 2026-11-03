"""별도 검증자의 답을 실행기가 읽는 판정으로 바꾼다(run.sh 가 부른다). 의미를 추측하지 않고 정해진 결과 형식만 읽는다.

검증자는 답 끝에 JSON 하나를 쓴다(verifier-prompt.txt 의 형식):
  {"verdict": "OK" 또는 "RETURN", "conditions": [{"id": "C1", "result": "충족|미충족|미확인", "evidence": "..."}],
   "return_reason": "...", "out_of_scope": ["..."]}
판정(state):
- ok: verdict 가 OK 이고, 조건이 하나 이상이며, 모든 조건이 충족이고 근거(evidence)가 있으며, 실행기가 넘긴 필수 조건 ID 가 모두 들어 있다.
- returned: verdict 가 RETURN 이고 사유(return_reason 또는 충족이 아닌 조건)가 있다. 실행기는 구현자에게 돌려보내고 새 버전을 다시 판정한다.
- unverified: 그 밖의 모든 경우(빈 답, JSON 없음·깨짐, 알 수 없는 verdict, OK 인데 미충족·미확인·근거 없음·필수 조건 누락, 사유 없는 RETURN).
  미확인은 완료가 아니다.
out_of_scope(새 요구가 있어야 성립하는 반례)는 판정을 막지 않고 따로 남긴다.

사용:
  python3 -I evals/verdict.py judge <검증자 기록 .jsonl> [필수 조건 ID ...]   → 판정 JSON 한 줄
  python3 -I evals/verdict.py baseline <프로젝트>                              → 작업 지도들의 `## 기준` 절(검증자에게 넘길 합의 조건)
  python3 -I evals/verdict.py completion <검증 상태> <PASS|REVIEW|FAIL|UNVERIFIED> → 전체 완료 판정
  python3 -I evals/verdict.py ids <파일>                                       → 파일에 적힌 조건 ID(표의 첫 칸 또는 줄 머리)
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
RESULTS = {"충족", "미충족", "미확인"}
ID = r"[A-Z]{1,3}\d{1,3}"


def last_json(text):
    """답의 최종 결과 JSON. 마지막 `"verdict":` 키를 담은 완결 객체여야 한다(코드 울타리 ``` 안이어도 된다).
    그 뒤에 끊기거나 깨진 결과 JSON 이 있으면 앞선 완결 객체(예시 등)를 대신 쓰지 않는다.
    돌려줌: (객체 또는 None, 실패 사유)."""
    keys = [m.start() for m in re.finditer(r'"verdict"\s*:', text)]
    if not keys:
        return None, "결과 형식(JSON)이 없다" if text.strip() else "빈 답"
    dec = json.JSONDecoder()
    last = keys[-1]
    for i in range(last, -1, -1):  # 마지막 verdict 키를 감싸는 가장 가까운 여는 괄호부터 해석한다
        if text[i] != "{":
            continue
        try:
            obj, end = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and i + end > last and "verdict" in obj:
            return obj, ""
    return None, "최종 결과 JSON 이 끊기거나 형식이 틀렸다(앞선 JSON 으로 대신하지 않는다)"


def judge(final, required=()):
    v, why = last_json(final or "")
    if v is None:
        return {"state": "unverified", "reason": why, "out_of_scope": []}
    oos = [str(x) for x in v.get("out_of_scope") or [] if str(x).strip()] if isinstance(v.get("out_of_scope"), list) else []
    conds = v.get("conditions") if isinstance(v.get("conditions"), list) else []
    bad_shape = [c for c in conds if not (isinstance(c, dict) and str(c.get("id", "")).strip() and c.get("result") in RESULTS)]
    out = {"out_of_scope": oos, "conditions": [{"id": c.get("id"), "result": c.get("result")} for c in conds if isinstance(c, dict)]}
    verdict = str(v.get("verdict", "")).strip().upper()
    if verdict == "RETURN":
        reasons = str(v.get("return_reason") or "").strip() or [c for c in conds if isinstance(c, dict) and c.get("result") != "충족"]
        return {**out, "state": "returned" if reasons else "unverified", "reason": "" if reasons else "사유 없는 RETURN"}
    if verdict != "OK":
        return {**out, "state": "unverified", "reason": f"알 수 없는 verdict: {verdict or '없음'}"}
    problems = []
    if not conds:
        problems.append("조건별 결과가 없다")
    if bad_shape:
        problems.append("형식이 틀린 조건 결과")
    ids = {str(c.get("id")).strip() for c in conds if isinstance(c, dict)}
    missing = [r for r in required if r not in ids]
    if missing:
        problems.append("필수 조건 누락: " + ", ".join(missing))
    unmet = [str(c.get("id")) for c in conds if isinstance(c, dict) and c.get("result") != "충족"]
    if unmet:
        problems.append("OK 인데 충족이 아닌 조건: " + ", ".join(unmet))
    no_evidence = [str(c.get("id")) for c in conds if isinstance(c, dict) and not str(c.get("evidence") or "").strip()]
    if no_evidence:
        problems.append("근거 없는 조건: " + ", ".join(no_evidence))
    if problems:
        return {**out, "state": "unverified", "reason": " / ".join(problems)}
    return {**out, "state": "ok", "reason": ""}


def completion(verifier, check):
    """전체 완료 판정(run.sh 와 rejudge.py 가 같이 쓴다). verifier: 검증 상태(off·ok·returned·incomplete·unverified),
    check: 사례 판정(PASS·REVIEW·FAIL·UNVERIFIED). 검증자가 OK 여도 결정적 행동 검사가 실패하면 완료가 아니다."""
    if verifier == "ok":
        return {"PASS": "verified", "REVIEW": "verified", "FAIL": "check-failed"}.get(check, "unverified")
    return {"off": "not-verified"}.get(verifier, verifier)


def baseline(project):
    """work/*/work.md 의 `## 기준` 절만 모은다(`## 증거` 같은 구현자의 실행 기록·자기평가는 넣지 않는다)."""
    parts = []
    for f in sorted(Path(project).glob("work/*/work.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^## 기준[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m and m.group(1).strip():
            parts.append(f"### {f.relative_to(project)}\n{m.group(1).strip()}")
    return "\n\n".join(parts)


def ids(text):
    found = []
    for line in text.splitlines():
        m = re.match(r"^\s*\|?\s*(" + ID + r")\b", line)
        if m and m.group(1) not in found:
            found.append(m.group(1))
    return found


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "judge":
        from transcript import read
        final = read(sys.argv[2])[1] if Path(sys.argv[2]).is_file() else ""
        print(json.dumps(judge(final, sys.argv[3:]), ensure_ascii=False))
    elif cmd == "baseline":
        print(baseline(sys.argv[2]))
    elif cmd == "ids":
        print(" ".join(ids(Path(sys.argv[2]).read_text(encoding="utf-8") if Path(sys.argv[2]).is_file() else "")))
