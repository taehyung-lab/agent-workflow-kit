"""상황 기록 확인: '정해짐'은 그 결과를 말하는 문장을 인용할 때만 남긴다.

  python3 .agents/skills/wf-ask/situations.py <상황.json> --request <원문 파일> [--request ...] [--root <프로젝트>]

상황 배열의 항목(독자 반환과 주 담당자의 기록이 같은 양식을 쓴다):
  {"id": "Q1", "expect": "실제 상황(자료 위치) → 결과", "source": [1], "state": "확정" 또는 "미정",
   "decided_by": {"kind": "요청" | "합의" | "답", "file": "합의일 때 프로젝트 기준 경로", "quote": "글자 그대로"},
   "facts": "지금 동작·금지 문장 없음·요청 범위 같은 사실(출처가 아님)"}

확정 항목은 decided_by 가 필요하다. 요청·답은 source 번호의 원문 파일(--request 순서가 원문 번호)에,
합의는 --root 아래 file 에 quote 가 글자 그대로(공백 차이만 무시) 있어야 한다. 아니면 미정으로 바꾸고 사유를 붙인다.
인용한 문장이 그 상황의 결과를 정말 말하는지는 이 도구가 판단하지 못한다. 그래서 확정 목록을 인용과 함께 내보내
사용자에게 보내는 글에 그대로 보이게 한다. 미정 목록은 질문 대상이다.
출력은 JSON 한 줄: {"settled": [...], "open": [...], "demoted": [{"id", "reason"}]}.
"""
import argparse
import json
import re
import sys
from pathlib import Path

KINDS = ("요청", "합의", "답")
MIN_QUOTE = 6


def _plain(text):
    return re.sub(r"\s+", "", text)


def _quote_found(item, requests, roots):
    """확정 근거의 인용이 가리킨 원문·문서에 있으면 None, 없으면 사유."""
    by = item.get("decided_by")
    if not isinstance(by, dict) or by.get("kind") not in KINDS:
        return "결정 출처(요청·합의·답 인용)가 없다"
    quote = _plain(str(by.get("quote", "")))
    if len(quote) < MIN_QUOTE:
        return "결정 출처의 인용 문장이 없다"
    if by["kind"] == "합의":
        rel = str(by.get("file", ""))
        texts = [(root / rel) for root in roots if rel and (root / rel).is_file()]
        if not texts:
            return f"합의 문서 {rel or '(경로 없음)'} 를 찾지 못했다"
        bodies = [path.read_text(encoding="utf-8", errors="replace") for path in texts]
    else:
        numbers = item.get("source") or []
        bodies = [requests[n - 1] for n in numbers if isinstance(n, int) and 0 < n <= len(requests)]
        if not bodies:
            return "인용한 원문 번호가 없다"
    if not any(quote in _plain(body) for body in bodies):
        return "인용 문장이 가리킨 원문·문서에 없다"
    return None


def classify(items, requests, roots):
    """확정 항목의 출처를 확인해 미정으로 내릴 것을 내린다. 입력 배열은 바꾸지 않는다."""
    if not isinstance(items, list):
        raise ValueError("상황 기록은 배열이어야 한다")
    settled, pending, demoted = [], [], []
    for original in items:
        item = json.loads(json.dumps(original))
        if not isinstance(item, dict) or not item.get("id") or not str(item.get("expect", "")).strip():
            raise ValueError("항목마다 id 와 expect 가 필요하다")
        if item.get("state") == "확정":
            reason = _quote_found(item, requests, roots)
            if reason:
                item["state"] = "미정"
                item.pop("decided_by", None)
                demoted.append({"id": item["id"], "reason": reason})
        if item.get("state") == "확정":
            settled.append(item)
        elif item.get("state") == "미정":
            pending.append(item)
        else:
            raise ValueError(f"{item['id']}: 상태는 확정 또는 미정이다")
    return {"settled": settled, "open": pending, "demoted": demoted}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("situations", type=Path)
    parser.add_argument("--request", action="append", default=[], type=Path, help="사용자 원문 파일(순서가 원문 번호)")
    parser.add_argument("--root", action="append", default=[], type=Path, help="합의 문서를 찾을 프로젝트 폴더(기본: 현재 폴더)")
    args = parser.parse_args()
    try:
        requests = [path.read_text(encoding="utf-8") for path in args.request]
        roots = [root.resolve() for root in (args.root or [Path.cwd()])]
        result = classify(json.loads(args.situations.read_text(encoding="utf-8")), requests, roots)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
