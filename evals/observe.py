"""실행 기록에서 판정과 따로 관찰할 사실을 뽑아 JSON 으로 낸다(run.sh 가 meta 의 observed 에 넣는다).

- final_question: 마지막 답에 질문 표지가 있는가(후보일 뿐, 의미 판정은 사람이 한다)
- last_turn_edits: 마지막 턴 기록에 남은 편집 대상 파일(편집 뒤 되돌려 최종 파일이 같아도 남는다)
- claims_independent_verification: 마지막 답이 독립·별도 검증을 통과했다고 주장하는가
- verifier_observed: 마지막 턴에 검증자를 만든 흔적(입력이 있는 하위 에이전트 생성 호출이나 wf-verify/verify.sh 실행)이 있는가.
  Codex 의 exec 기록에는 생성 호출이 남지 않으므로, run.sh 가 남긴 원본 기록(<이름>.rollout.jsonl)의 spawn_agent 호출을 본다.
  Codex 의 수신자 없는 wait 나 Claude 의 입력 없는 호출은 흔적으로 치지 않는다. 검증자에게 넘긴 내용은 Codex 원본에서 암호화되어 볼 수 없다.
- verifier_record: 검증자 생성을 볼 수 있는 기록이 있었는가. "observed"(생성 흔적 있음)·"none"(볼 수 있는 기록에 없음)·
  "no-record"(Codex 원본 기록이 없어 생성 여부를 볼 수 없음). 생성 흔적은 검증 통과의 증거가 아니다(무엇을 넘겼고 어떻게 판정했는지는 따로 본다).
- independent_claim_unverified: 독립 검증을 주장했는데 볼 수 있는 기록에 생성 흔적이 없음(기록이 없으면 참으로 세지 않는다)

사용: python3 -I evals/observe.py <원시 기록 .jsonl> [제품 파일 이름 ...]
마지막 턴 기록은 <이름>.tN.jsonl 중 가장 큰 N 이고, 없으면 주어진 파일 자체다.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import QUESTION
from transcript import read

CLAIM = r"(독립\s*검증|별도\s*검증|독립\s*판정|별도\s*검토|독립\s*검토|independent(ly)?\s+verif)"
# 검증 도구를 읽기만 한 것(cat 등)은 치지 않고 bash·sh 로 실행한 것만 친다.
RUN_VERIFY = r"\b(bash|sh)\s+\S*wf-verify/verify\.sh"
WRITES = r"(>\s*\S|sed\s+-i|write_text|open\([^)]*['\"]w|apply_patch|tee\s)"


def last_turn_log(log):
    log = Path(log)
    turns = sorted(log.parent.glob(log.name[: -len(".jsonl")] + ".t*.jsonl"), key=lambda p: int(re.search(r"\.t(\d+)\.jsonl$", p.name).group(1)))
    return turns[-1] if turns else log


def edits(path, names):
    found = set()
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for part in e.get("message", {}).get("content", []):
                if part.get("type") != "tool_use":
                    continue
                inp = part.get("input") or {}
                target = str(inp.get("file_path") or "")
                cmd = str(inp.get("command") or "")
                for n in names:
                    if part.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit") and target.endswith(n):
                        found.add(n)
                    elif n in cmd and re.search(WRITES, cmd):
                        found.add(n)
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "file_change":
            for c in item.get("changes", []):
                for n in names:
                    if str(c.get("path", "")).endswith(n) or f"/{n}/" in str(c.get("path", "")):
                        found.add(n)
        if e.get("type") == "item.completed" and item.get("type") == "command_execution":
            cmd = item.get("command", "")
            for n in names:
                if n in cmd and re.search(WRITES, cmd):
                    found.add(n)
    return sorted(found)


def verifier_observed(path):
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get("item") or {}
        if item.get("type") == "command_execution" and re.search(RUN_VERIFY, item.get("command", "")):
            return True
        if item.get("type") == "collab_tool_call" and item.get("tool") != "wait" and (item.get("prompt") or item.get("receiver_thread_ids")):
            return True
        if e.get("type") == "assistant":
            for part in e.get("message", {}).get("content", []):
                inp = part.get("input") or {} if part.get("type") == "tool_use" else {}
                if part.get("name") in ("Agent", "Task") and inp.get("prompt"):
                    return True
                if part.get("name") == "Bash" and re.search(RUN_VERIFY, str(inp.get("command", ""))):
                    return True
    return False


def rollout_spawned_in_last_turn(log):
    """Codex 원본 기록에서 마지막 사용자 턴 뒤에 하위 에이전트를 만들었는가. 원본이 없으면 None."""
    path = Path(str(log)[: -len(".jsonl")] + ".rollout.jsonl")
    if not path.is_file():
        return None
    spawned = False
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") == "user_message":
            spawned = False  # 새 사용자 턴이 시작되면 다시 센다
        elif e.get("type") == "response_item" and p.get("type") == "function_call" and p.get("name") == "spawn_agent":
            spawned = True
    return spawned


def codex_log(path):
    """Codex exec 기록인가(첫 사건이 thread.started 등 Codex 형식)."""
    for line in open(path, encoding="utf-8"):
        try:
            return json.loads(line).get("type", "").startswith(("thread.", "turn.", "item."))
        except ValueError:
            continue
    return False


def observe(log, names):
    last = last_turn_log(log)
    _, final = read(last)
    claimed = bool(re.search(CLAIM, final, re.I))
    spawned = rollout_spawned_in_last_turn(log)
    observed = verifier_observed(last) or bool(spawned)
    codex = codex_log(last)
    record = "observed" if observed else ("no-record" if codex and spawned is None else "none")
    return {
        "final_question": bool(re.search(QUESTION, final)),
        "last_turn_edits": edits(last, names),
        "claims_independent_verification": claimed,
        "verifier_observed": observed,
        "verifier_record": record,
        "independent_claim_unverified": claimed and record == "none",
    }


if __name__ == "__main__":
    print(json.dumps(observe(sys.argv[1], sys.argv[2:]), ensure_ascii=False))
