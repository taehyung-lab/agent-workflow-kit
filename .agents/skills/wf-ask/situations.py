"""상황 기록 확인: 상태 × 명령 표의 칸이 모두 상황으로 채워졌는지, '정해짐'이 그 결과를 말하는 인용을 가졌는지 본다.

  python3 .agents/skills/wf-ask/situations.py <상황.json> --request <원문 파일> [--request ...] [--root <프로젝트>]

입력(독자 반환과 주 담당자의 기록이 같은 양식을 쓴다):
  {"axes": {"states": [{"name", "where": 자료 위치}], "commands": [{"name", "where": 코드 위치}]},
   "situations": [항목, ...]}
표의 상태 × 명령 칸마다 cell 이 그 칸인 항목이 하나 이상 있어야 한다. 빈 칸이 있으면 종료 코드 3 으로
missing 에 칸을 내보낸다(그 칸의 상황을 만들어 다시 확인한다). 표가 없으면 종료 코드 3 이다.
항목:
  {"id": "Q1", "cell": ["상태", "명령"], "expect": "실제 상황(자료 위치) → 결과", "source": [1], "state": "확정" 또는 "미정",
   "decided_by": {"kind": "요청" | "합의" | "답", "file": "합의일 때 프로젝트 기준 경로", "quote": "글자 그대로"},
   "facts": "지금 동작·금지 문장 없음·요청 범위 같은 사실(출처가 아님)"}

확정 항목은 decided_by 가 필요하다. 요청·답은 source 번호의 원문 파일(--request 순서가 원문 번호)에,
합의는 --root 아래 file 에 quote 가 글자 그대로(공백 차이만 무시) 있어야 한다. 아니면 미정으로 바꾸고 사유를 붙인다.
인용한 문장이 그 상황의 결과를 정말 말하는지는 이 도구가 판단하지 못한다. 그래서 확정 목록을 인용과 함께 내보내
사용자에게 보내는 글에 그대로 보이게 한다. 미정 목록은 질문 대상이다.
출력은 JSON 한 줄: {"settled": [...], "open": [...], "demoted": [{"id", "reason"}], "missing": [["상태", "명령"], ...]}.
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


def missing_cells(axes, items):
    """표의 상태 × 명령 가운데 상황이 하나도 없는 칸."""
    names = {}
    for axis in ("states", "commands"):
        entries = axes.get(axis) if isinstance(axes, dict) else None
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"표의 {axis} 가 비었다")
        if any(not isinstance(e, dict) or not str(e.get("name", "")).strip() or not str(e.get("where", "")).strip() for e in entries):
            raise ValueError(f"표의 {axis} 마다 name 과 where(실제 위치)가 필요하다")
        names[axis] = [e["name"] for e in entries]
    filled = {tuple(item["cell"]) for item in items if isinstance(item.get("cell"), list) and len(item["cell"]) == 2}
    for cell in filled:
        if cell[0] not in names["states"] or cell[1] not in names["commands"]:
            raise ValueError(f"표에 없는 칸이다: {list(cell)}")
    return [[s, c] for s in names["states"] for c in names["commands"] if (s, c) not in filled]


def classify(items, requests, roots):
    """확정 항목의 출처를 확인해 미정으로 내릴 것을 내린다. 입력은 바꾸지 않는다.

    items 가 표({"axes", "situations"})면 빈 칸도 함께 낸다. 배열이면 표 확인 없이 출처만 본다."""
    axes = None
    if isinstance(items, dict):
        axes, items = items.get("axes"), items.get("situations")
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
    return {"settled": settled, "open": pending, "demoted": demoted,
            "missing": missing_cells(axes, settled + pending) if axes is not None else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("situations", type=Path)
    parser.add_argument("--request", action="append", default=[], type=Path, help="사용자 원문 파일(순서가 원문 번호)")
    parser.add_argument("--root", action="append", default=[], type=Path, help="합의 문서를 찾을 프로젝트 폴더(기본: 현재 폴더)")
    args = parser.parse_args()
    try:
        requests = [path.read_text(encoding="utf-8") for path in args.request]
        roots = [root.resolve() for root in (args.root or [Path.cwd()])]
        data = json.loads(args.situations.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "axes" not in data:
            raise ValueError("상태 × 명령 표(axes)가 없다")
        result = classify(data, requests, roots)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False))
    return 3 if result["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
