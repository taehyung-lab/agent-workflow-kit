"""상황 기록 확인: 상태 × 명령 표의 칸이 모두 상황으로 채워졌는지, '정해짐'이 그 결과를 말하는 인용을 가졌는지,
합친 기록이 독자 표를 줄이지 않았는지 본다.

  python3 .agents/skills/wf-ask/situations.py <상황.json> --request <원문 파일> [--request ...] [--reader <독자 표>] [--root <프로젝트>]

입력(독자 반환과 주 담당자의 기록이 같은 양식을 쓴다):
  {"axes": {"states": [{"name", "where": 자료 위치}], "commands": [{"name", "where": 코드 위치}]},
   "situations": [항목, ...]}
표의 상태 × 명령 칸마다 cell 이 그 칸인 항목이 하나 이상 있어야 한다. 빈 칸이 있으면 종료 코드 3 으로
missing 에 칸을 내보낸다(그 칸의 상황을 만들어 다시 확인한다). 표가 없으면 종료 코드 3 이다.
항목:
  {"id": "Q1", "cell": ["상태", "명령"], "expect": "실제 상황(자료 위치)", "results": ["사용자가 볼 결과 A", "결과 B"],
   "source": [1], "state": "확정" 또는 "미정", "chosen": "확정이면 인용이 고른 결과(results 중 하나)",
   "decided_by": {"kind": "요청" | "합의" | "답" | "기준", "file": "합의일 때 프로젝트 기준 경로", "quote": "글자 그대로"},
   "observed": {"where", "value"} (기준일 때: 지정한 기준에서 관찰한 위치·값),
   "default": "미정이면 기본값(results 중 하나)", "default_by": "기본값을 고른 근거 인용 또는 '추천: 이유'",
   "facts": "지금 동작·금지 문장 없음·요청 범위 같은 사실(출처가 아님)"}
표의 상황은 사용자에게 보일 수 있는 서로 다른 결과를 둘 이상 적는다(results). 확정은 인용 문장이 그중 무엇을 고르는지
chosen 으로 적는다. 결과가 하나뿐인 상황은 형식 오류다(종료 코드 3). 확정인데 chosen 이 results 에 없으면 미정으로 내린다.

--reader 로 독자가 반환한 표를 주면, 합친 기록이 그 표를 줄이지 않았는지 본다: 독자 표의 상태·명령 이름이 모두 남고,
독자 상황이 같은 id·칸으로 남으며, 독자가 미정으로 둔 상황은 사용자 답(kind 답)의 인용 없이 확정이 되지 않는다.
어기면 종료 코드 3 이다.

확정 항목은 decided_by 가 필요하다. 요청·답·기준은 source 번호의 원문 파일(--request 순서가 원문 번호)에,
합의는 --root 아래 file 에 quote 가 글자 그대로(공백 차이만 무시) 있어야 한다. --base <커밋> 을 주면 합의는 작업 시작
판의 문서에서 찾는다(이번 작업에서 고친 문장은 합의가 아니다). 기준은 observed 의 where·value 가 필요하다.
아니면 미정으로 바꾸고 사유를 붙인다.

답은 그 줄의 질문(독자 ask 또는 그 줄의 ask)을 실제로 보낸 글 뒤의 사용자 턴에서만 인용한다. --sent 는 사용자 턴마다
그 뒤에 보낸 글이다(N 번째 --sent 는 N 번째 원문 뒤). --reader 나 --sent 를 주면, 사용자 답으로 확정한 줄과 독자가
확정한 결과를 바꾼 줄마다 그 질문이 답 턴보다 앞선 보낸 글에 그대로 있는지 본다. 없으면 종료 코드 3 이다(그 줄은
미정으로 두고 질문을 보낸다). 독자가 정한 결과는 '진행'·'추천대로' 같은 일반 승인으로 바뀌지 않는다. 출력의 ready 는 미정·빈 칸·미전달이 없어 구현으로 넘길 수 있는지다.
인용한 문장이 그 상황의 결과를 정말 말하는지는 이 도구가 판단하지 못한다. 그래서 확정 목록을 인용과 함께 내보내
사용자에게 보내는 글에 그대로 보이게 한다. 미정 목록은 질문 대상이다.
출력은 JSON 한 줄: {"settled": [...], "open": [...], "demoted": [{"id", "reason"}], "missing": [["상태", "명령"], ...]}.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KINDS = ("요청", "합의", "답", "기준")
MIN_QUOTE = 6


def _plain(text):
    return re.sub(r"\s+", "", text)


def _at_base(root, rel, base):
    out = subprocess.run(["git", "-C", str(root), "show", f"{base}:{rel}"], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def _quote_found(item, requests, roots, base=None):
    """확정 근거의 인용이 가리킨 원문·문서에 있으면 None, 없으면 사유."""
    by = item.get("decided_by")
    if not isinstance(by, dict) or by.get("kind") not in KINDS:
        return "결정 출처(요청·합의·답·기준 인용)가 없다"
    quote = _plain(str(by.get("quote", "")))
    if len(quote) < MIN_QUOTE:
        return "결정 출처의 인용 문장이 없다"
    if by["kind"] == "기준":
        seen = item.get("observed")
        if not isinstance(seen, dict) or not str(seen.get("where", "")).strip() or not str(seen.get("value", "")).strip():
            return "기준 인용에는 기준에서 관찰한 위치·값(observed)이 필요하다"
    if by["kind"] == "합의":
        rel = str(by.get("file", ""))
        if base:
            bodies = [b for b in (_at_base(root, rel, base) for root in roots if rel) if b is not None]
            if not bodies:
                return f"합의 문서 {rel or '(경로 없음)'} 가 작업 시작 판({base})에 없다"
        else:
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


def _results_problem(item):
    results = item.get("results")
    if not isinstance(results, list) or len({str(r).strip() for r in results if str(r).strip()}) < 2:
        return f"{item.get('id')}: 상황마다 사용자에게 보일 서로 다른 결과를 둘 이상 results 에 적는다"
    return None


def reader_kept(merged, reader, requests=(), roots=()):
    """합친 기록이 독자 표를 줄였거나, 독자가 정한 줄을 근거 없이 미정으로 돌렸으면 그 사유 목록."""
    problems = []
    axes = merged.get("axes") or {}
    for axis in ("states", "commands"):
        have = {e.get("name") for e in axes.get(axis) or [] if isinstance(e, dict)}
        for e in (reader.get("axes") or {}).get(axis) or []:
            if isinstance(e, dict) and e.get("name") not in have:
                problems.append(f"독자 표의 {axis} '{e.get('name')}' 가 빠졌다")
    mine = {i.get("id"): i for i in merged.get("situations") or [] if isinstance(i, dict)}
    for r in reader.get("situations") or []:
        if not isinstance(r, dict):
            continue
        m = mine.get(r.get("id"))
        if m is None:
            problems.append(f"독자 상황 {r.get('id')} 가 빠졌다")
        elif m.get("cell") != r.get("cell"):
            problems.append(f"독자 상황 {r.get('id')} 의 칸이 바뀌었다")
        elif r.get("state") != "확정" and m.get("state") == "확정" and (m.get("decided_by") or {}).get("kind") != "답":
            problems.append(f"독자가 미정으로 둔 {r.get('id')} 를 사용자 답 없이 확정했다")
        elif r.get("state") == "확정" and m.get("state") == "미정":
            reopen = {"decided_by": m.get("reopened_by"), "source": m.get("source")}
            if not m.get("reopened_by") or _quote_found(reopen, list(requests), list(roots)):
                problems.append(f"독자가 정한 {r.get('id')} 를 근거(reopened_by 인용) 없이 미정으로 돌렸다")
    return problems


def undelivered(merged, reader, message):
    """독자가 미정으로 돌려준 상황 가운데, 사용자 답으로 정해지지 않았고 그 ask 문장이 보낸 글에 그대로 없는 것.
    질문 문장은 독자가 쓰므로 담당자의 거르기·바꿔 쓰기와 무관하게 글자 대조로 판정한다(공백 차이만 무시)."""
    mine = {i.get("id"): i for i in merged.get("situations") or [] if isinstance(i, dict)}
    body = _plain(message)
    missing = []
    for r in reader.get("situations") or []:
        if not isinstance(r, dict) or r.get("state") != "미정":
            continue
        m = mine.get(r.get("id")) or {}
        if m.get("state") == "확정" and (m.get("decided_by") or {}).get("kind") == "답":
            continue
        ask = str(r.get("ask") or "").strip()
        if not ask:
            missing.append({"id": r.get("id"), "reason": "독자 미정에 ask 가 없다"})
        elif _plain(ask) not in body:
            missing.append({"id": r.get("id"), "reason": "보낸 글에 독자의 질문이 없다", "ask": ask})
    return missing


def _asked_before(item, ask, sent):
    """답 인용의 턴보다 앞서 보낸 글에 그 줄의 질문이 그대로 있는가."""
    turns = [n for n in item.get("source") or [] if isinstance(n, int)]
    question = _plain(ask)
    return bool(question and turns) and any(question in _plain(sent[k - 1]) for k in range(1, min(turns)) if k <= len(sent))


GENERIC = re.compile(r"(진행|그렇게|그대로|추천대로|추천안|추천|기본값대로|네|예|좋아요|좋습니다|맞아요|맞습니다|해\s*주세요|해주세요|하세요|합시다|ok|okay|yes|go|[\s.,!~。…]+)", re.I)


def _generic(quote):
    """'진행해주세요'·'추천대로' 같은 일반 승인: 결과를 직접 말하지 않는다."""
    return len(GENERIC.sub("", str(quote))) < 4


def answers_unbound(merged, reader, sent):
    """사용자 답으로 확정한 줄과 독자가 확정한 결과를 바꾼 줄 가운데, 그 줄을 물은 글 뒤의 답이 아닌 것."""
    theirs = {r.get("id"): r for r in reader.get("situations") or [] if isinstance(r, dict)}
    problems = []
    for m in merged.get("situations") or []:
        if not isinstance(m, dict) or m.get("state") != "확정":
            continue
        r = theirs.get(m.get("id")) or {}
        kept = r.get("state") == "확정" and r.get("chosen") == m.get("chosen")
        kind = (m.get("decided_by") or {}).get("kind")
        if kept or (kind != "답" and r.get("state") != "확정"):
            continue
        if kind != "답":
            problems.append(f"독자가 정한 {m.get('id')} 의 결과를 사용자 답 없이 바꿨다")
        elif r.get("state") == "확정" and _generic((m.get("decided_by") or {}).get("quote", "")):
            problems.append(f"독자가 정한 {m.get('id')} 의 결과는 일반 승인('진행' 등)으로 바뀌지 않는다: 사용자가 다른 결과를 직접 말해야 한다")
        elif not _asked_before(m, r.get("ask") or m.get("ask") or "", sent):
            problems.append(f"{m.get('id')} 의 답 인용이 그 줄의 질문(ask)을 보낸 글 뒤의 사용자 턴이 아니다")
    return problems


def compose(result, reader):
    """첫 답에 붙일 목록을 분류 결과(classify 의 settled·open)에서 만든다. 지정 기준에서 관찰해 정한 결과(observed)는
    "기준 관찰" 알림 줄로 먼저, 미정(독자·담당자 것 모두, 출처가 약해 내려간 줄 포함)은 질문 줄로 낸다.
    질문 문장은 독자 ask → 그 줄의 ask → "실제 상황: 결과 A / 결과 B" 순으로 고르고, 같은 문장은 한 번만 낸다."""
    theirs = {r.get("id"): r for r in reader.get("situations") or [] if isinstance(r, dict)}
    lines = []
    for item in result["settled"]:
        seen = item.get("observed")
        if not seen:
            continue
        if not isinstance(seen, dict) or not str(seen.get("where", "")).strip() or not str(seen.get("value", "")).strip():
            raise ValueError(f"기준 관찰 {item.get('id')} 에 where(위치)와 value(값)가 필요하다")
        lines.append(f"기준 관찰: {item.get('expect')} → {seen['value']} ({seen['where']})")
    for item in result["open"]:
        r = theirs.get(item.get("id")) or {}
        ask = str(r.get("ask") or item.get("ask") or "").strip()
        if not ask:
            ask = f"{item.get('expect')}: " + " / ".join(str(x) for x in item.get("results") or [])
        default, why = r.get("default") or item.get("default"), r.get("default_by") or item.get("default_by")
        if default:
            if default not in (item.get("results") or []):
                raise ValueError(f"{item.get('id')} 의 기본값(default)이 results 에 없다")
            ask += f" (기본값: {default} — {why or '근거 없음'})"
        if ask not in lines:
            lines.append(ask)
    return lines


def classify(items, requests, roots, base=None):
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
        if axes is not None and _results_problem(item):
            raise ValueError(_results_problem(item))
        if item.get("state") == "확정":
            reason = _quote_found(item, requests, roots, base)
            if not reason and axes is not None and item.get("chosen") not in item["results"]:
                reason = "인용이 고른 결과(chosen)가 results 에 없다"
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
    parser.add_argument("--reader", action="append", default=[], type=Path, help="독자가 반환한 표 JSON(합친 기록이 줄이지 않았는지 확인)")
    parser.add_argument("--root", action="append", default=[], type=Path, help="합의 문서를 찾을 프로젝트 폴더(기본: 현재 폴더)")
    parser.add_argument("--compose", action="store_true", help="첫 답에 그대로 붙일 질문 목록(독자 미정의 ask)을 글로 낸다")
    parser.add_argument("--message", type=Path, help="사용자에게 보낼 글. --reader 의 미정마다 ask 문장이 그대로 있는지 본다")
    parser.add_argument("--sent", action="append", default=[], type=Path, help="사용자 턴마다 그 뒤에 보낸 글(순서가 원문 번호)")
    parser.add_argument("--base", help="작업 시작 커밋. 합의 인용을 이 판의 문서에서 찾는다")
    args = parser.parse_args()
    try:
        requests = [path.read_text(encoding="utf-8") for path in args.request]
        roots = [root.resolve() for root in (args.root or [Path.cwd()])]
        data = json.loads(args.situations.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "axes" not in data:
            raise ValueError("상태 × 명령 표(axes)가 없다")
        readers = [json.loads(path.read_text(encoding="utf-8")) for path in args.reader]
        kept = [p for reader in readers for p in reader_kept(data, reader, requests, roots)]
        if kept:
            raise ValueError("합친 기록이 독자 표를 줄였다: " + "; ".join(kept))
        if readers or args.sent:
            sent = [path.read_text(encoding="utf-8") for path in args.sent]
            unbound = [p for reader in (readers or [{}]) for p in answers_unbound(data, reader, sent)]
            if unbound:
                raise ValueError("그 줄을 물은 글 뒤의 답이 아니다: " + "; ".join(unbound))
        result = classify(data, requests, roots, args.base)
        if args.compose:
            if not args.reader:
                raise ValueError("--compose 는 --reader 와 함께 쓴다")
            asks = [a for path in args.reader for a in compose(result, json.loads(path.read_text(encoding="utf-8")))]
            print("\n".join(f"{n}. {a}" for n, a in enumerate(asks, 1)))
            return 0
        if args.message:
            if not args.reader:
                raise ValueError("--message 는 --reader 와 함께 쓴다")
            text = args.message.read_text(encoding="utf-8")
            result["undelivered"] = [u for path in args.reader for u in undelivered(data, json.loads(path.read_text(encoding="utf-8")), text)]
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 3
    result["ready"] = not (result["open"] or result["missing"] or result.get("undelivered"))
    print(json.dumps(result, ensure_ascii=False))
    return 3 if result["missing"] or result.get("undelivered") else 0


if __name__ == "__main__":
    sys.exit(main())
