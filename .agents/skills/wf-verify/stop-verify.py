"""Stop 훅: 에이전트가 답을 마치려 할 때, 검토받지 않은 제품 변경이 있으면 별도 검증 세션에 요구 근거 검토를 맡긴다.

에이전트가 검증을 할지 정하지 않게 하려고 하네스(Codex·Claude Code)의 Stop 훅으로 실행한다.
검증자는 이 세션의 사용자 메시지 원문 그대로와 기준 커밋(HEAD) 대비 변경물만 받는다. 구현자의 보고는 넘기지 않는다.
판정은 두 가지다: RETURN(원문·외부 계약으로 고를 수 없는 사용자 결과를 구현자가 정함), OK(그런 결과 없음).
OK 는 요구 근거 검토 통과일 뿐 조건별 구현 검증 통과가 아니다.

- RETURN 이면 답을 끝내지 않고 사유를 새 지시로 돌려준다. 고친 뒤 다시 멈추면 다시 검토한다(한 턴에 최대 MAX_BLOCKS 번 막는다).
- 검토를 끝내지 못하면(원문 없음·검증 세션 실패·판정 형식 오류) 한 번 막고, 독립 검증을 주장하지 말고 미확인으로 보고하게 한다.
- 같은 원문·같은 HEAD·같은 변경에 OK 를 받았으면 다시 띄우지 않는다(.git/awk-verify/ 에 지문을 남긴다).
환경 변수: AWK_VERIFIER=claude|codex(기본: 훅을 부른 하네스), AWK_VERIFYING=1(검증 세션 안에서는 아무것도 하지 않는다),
AWK_VERIFY_LOG=<파일>(판단마다 한 줄씩 남긴다. 측정용).
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_BLOCKS = 2
TAG = "[stop-verify]"  # 훅이 돌려준 지시는 대화 기록에 사용자 메시지로 남으므로 이 표지로 원문에서 뺀다
INJECTED = ("# AGENTS.md instructions", "<environment_context", "<user_instructions", "<INSTRUCTIONS>", "<skill>",
            "<system-reminder>", "<command-", "<local-command", TAG)
SPEC = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude", ":(exclude)**/__pycache__"]


def log(what):
    if os.environ.get("AWK_VERIFY_LOG"):
        try:
            with open(os.environ["AWK_VERIFY_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(what, ensure_ascii=False) + "\n")
        except OSError:
            pass


def git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def user_messages(path):
    """대화 기록에서 사용자가 직접 쓴 메시지만 순서대로 꺼낸다(주입된 지침·도구 결과·훅의 지시는 뺀다)."""
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
            texts = [c.get("text", "") for c in p.get("content", []) if c.get("type") == "input_text"]
        elif e.get("type") == "user" and not e.get("isMeta"):
            c = (e.get("message") or {}).get("content")
            texts = [c] if isinstance(c, str) else [x.get("text", "") for x in c or [] if x.get("type") == "text"]
        else:
            continue
        out += [t.strip() for t in texts if t.strip() and not t.lstrip().startswith(INJECTED)]
    return out


def changes(root):
    """HEAD 대비 변경물. 새 파일 중 이진 파일은 경로만 적는다(내용은 검증자에게 넘길 수 없다)."""
    body = git(root, "diff", "--binary", "HEAD", *SPEC).decode(errors="replace")
    for f in [x for x in git(root, "ls-files", "-z", "--others", "--exclude-standard", *SPEC).decode().split("\0") if x]:
        p = Path(root, f)
        raw = p.read_bytes() if p.is_file() and not p.is_symlink() else b""
        if b"\0" in raw or p.is_symlink():
            body += f"\n### 새 파일 {f} (이진·링크, 내용 생략, sha256 {hashlib.sha256(raw).hexdigest()[:16]})\n"
        else:
            body += f"\n### 새 파일 {f}\n" + raw.decode(errors="replace")
    return body


def block(reason):
    print(json.dumps({"decision": "block", "reason": f"{TAG} {reason}"}, ensure_ascii=False))
    return 0


def main():
    if os.environ.get("AWK_VERIFYING") == "1":
        return 0
    data = json.load(sys.stdin)
    log({"start": data.get("hook_event_name"), "continued": bool(data.get("stop_hook_active"))})
    root = git(data.get("cwd") or ".", "rev-parse", "--show-toplevel").decode().strip()
    state = Path(git(root, "rev-parse", "--absolute-git-dir").decode().strip(), "awk-verify")
    state.mkdir(exist_ok=True)
    body = changes(root)
    if not body.strip():
        log({"skip": "no-change"})
        return 0
    originals = user_messages(data["transcript_path"]) if data.get("transcript_path") else []
    head = git(root, "rev-parse", "HEAD").decode().strip()
    rules = (HERE / "verifier.md").read_bytes()
    stamp = hashlib.sha256(json.dumps([originals, head, body]).encode() + rules).hexdigest()
    if (state / "ok").is_file() and (state / "ok").read_text().strip() == stamp:
        log({"skip": "already-ok"})
        return 0
    # 한 턴에 막는 횟수를 센다(turn_id 가 없는 하네스는 세션 단위).
    turn = str(data.get("turn_id") or data.get("session_id") or "")
    counter = state / "blocks.json"
    counts = json.loads(counter.read_text()) if counter.is_file() else {}
    if counts.get(turn, 0) >= MAX_BLOCKS:
        log({"skip": "block-limit"})
        print("stop-verify: 막는 횟수 한도에 닿아 요구 근거 검토가 미확인으로 남았다", file=sys.stderr)
        return 0
    counts[turn] = counts.get(turn, 0) + 1
    counter.write_text(json.dumps(counts))
    unverified = ("독립 검토를 끝내지 못했다({why}). 완료 보고에서 독립 검증·별도 검증 통과를 주장하지 말고, "
                  "요구 근거 검토가 미확인이라는 사실과 재개 조건을 보고하세요.")
    if not originals:
        log({"verdict": "none", "why": "no-user-message"})
        return block(unverified.format(why="대화 기록에서 사용자 원문을 찾지 못함"))
    prompt = rules.decode()
    prompt += "".join(f"\n\n## 사용자 원문 {n}\n{t}" for n, t in enumerate(originals, 1))
    prompt += "\n\n## 변경물(HEAD 대비)\n" + body[:120000]
    if len(body) > 120000:
        prompt += "\n\n(변경물이 길어 잘렸다. 나머지는 저장소에서 git diff HEAD 로 직접 읽는다.)"
    harness = os.environ.get("AWK_VERIFIER") or ("codex" if "turn_id" in data else "claude")
    env = dict(os.environ, AWK_VERIFYING="1")
    env.pop("CLAUDECODE", None)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp, "answer.txt")
        if harness == "codex":
            cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", str(out), prompt]
        else:
            cmd = ["claude", "-p", prompt, "--output-format", "text", "--tools", "Read,Grep,Glob", "--max-turns", "30"]
        try:
            r = subprocess.run(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
            answer = out.read_text(encoding="utf-8") if harness == "codex" and out.is_file() else r.stdout
            rc = r.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            answer, rc = "", repr(e)
    first = next((l.strip("*# \t") for l in answer.splitlines() if l.strip()), "")
    verdict = first if first in ("OK", "RETURN") else None
    log({"verdict": verdict or "none", "rc": rc, "answer": answer[:4000]})
    if rc != 0 or verdict is None:
        return block(unverified.format(why=f"검증 세션 종료 {rc}, 첫 줄이 OK·RETURN 이 아님" if rc == 0 else f"검증 세션 종료 {rc}"))
    if verdict == "OK":
        (state / "ok").write_text(stamp)
        return 0
    return block("별도 검증자가 아래 사유로 돌려보냈습니다(wf-verify 1). 검증자의 판단을 그대로 따르지 말고 사용자 원문과 작업 기준에 비추어 판단하세요. "
                 "근거 없이 정해진 결과가 맞다면, 이번 사용자 요청 뒤에 넣은 것 중 그 결과에 기대는 코드·검사만 되돌리고 사용자에게 추천과 함께 물으세요.\n\n" + answer)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 훅 자체의 오류는 답을 막지 않는다. 대신 기록과 표준 오류에 남긴다.
        log({"error": repr(e)})
        print(f"stop-verify: 훅 오류로 요구 근거 검토를 하지 못했다: {e!r}", file=sys.stderr)
        sys.exit(0)
