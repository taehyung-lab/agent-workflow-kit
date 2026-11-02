"""Stop 훅: 에이전트가 답을 마치려 할 때, 검증받지 않은 제품 변경이 있으면 별도 검증 세션을 띄운다.

에이전트가 검증을 할지 정하지 않게 하려고 하네스(Codex·Claude Code)의 Stop 훅으로 실행한다.
검증자는 이 세션의 사용자 메시지 원문 그대로, 기준 커밋(HEAD) 대비 변경물, 에이전트의 마지막 답만 받는다.
검증자가 RETURN 을 내면 답을 끝내지 않고 사유를 새 지시로 돌려준다(그 결과에 기대는 코드·검사를 되돌리고 사용자에게 묻게 한다).
같은 변경을 이미 OK 로 판정했으면 다시 띄우지 않는다(.git/awk-verified 에 변경 지문을 남긴다). 돌려받은 뒤의 답은 다시 막지 않는다.
검증 세션이 판정 없이 끝나면 막지 않고, 그 사실을 표준 오류에 남긴다.
환경 변수: AWK_VERIFIER=claude|codex(기본: 훅을 부른 하네스), AWK_VERIFYING=1(검증 세션 안에서는 훅이 아무것도 하지 않는다),
AWK_VERIFY_LOG=<파일>(훅이 판단할 때마다 한 줄씩 남긴다. 측정용).
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP = ("<", "# AGENTS.md instructions")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True).stdout


def user_messages(path):
    """대화 기록에서 사용자가 직접 쓴 메시지만 순서대로 꺼낸다(주입된 지침·도구 결과는 뺀다)."""
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
        out += [t.strip() for t in texts if t.strip() and not t.lstrip().startswith(SKIP)]
    return out


def log(what):
    if os.environ.get("AWK_VERIFY_LOG"):
        with open(os.environ["AWK_VERIFY_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(what, ensure_ascii=False) + "\n")


def main():
    if os.environ.get("AWK_VERIFYING"):
        return 0
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        log({"skip": "continued"})
        return 0
    root = git(data.get("cwd") or ".", "rev-parse", "--show-toplevel").strip()
    if not root:
        return 0
    spec = ["--", ".", ":(exclude).agents", ":(exclude)work", ":(exclude).codex", ":(exclude).claude"]
    diff = git(root, "diff", "HEAD", *spec)
    new = git(root, "ls-files", "--others", "--exclude-standard", *spec).split()
    if not diff and not new:
        log({"skip": "no-change"})
        return 0
    body = diff + "".join(f"\n### 새 파일 {f}\n" + Path(root, f).read_text(errors="replace")[:8000] for f in new[:50])
    mark = Path(git(root, "rev-parse", "--absolute-git-dir").strip(), "awk-verified")
    stamp = hashlib.sha256(body.encode()).hexdigest()
    if mark.is_file() and mark.read_text().strip() == stamp:
        log({"skip": "already-ok"})
        return 0
    originals = user_messages(data["transcript_path"]) if data.get("transcript_path") else []
    if not originals:
        print("stop-verify: 사용자 원문을 찾지 못해 검증하지 않았다", file=sys.stderr)
        return 0
    prompt = (HERE / "verifier.md").read_text(encoding="utf-8")
    prompt += "".join(f"\n\n## 사용자 원문 {n}\n{t}" for n, t in enumerate(originals, 1))
    prompt += "\n\n## 변경물(HEAD 대비)\n" + body[:80000]
    prompt += "\n\n## 구현자의 마지막 답(근거가 아니다)\n" + (data.get("last_assistant_message") or "")
    harness = os.environ.get("AWK_VERIFIER") or ("codex" if "turn_id" in data else "claude")
    env = dict(os.environ, AWK_VERIFYING="1")
    env.pop("CLAUDECODE", None)
    with tempfile.NamedTemporaryFile("r", suffix=".txt") as out:
        if harness == "codex":
            cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", out.name, prompt]
            r = subprocess.run(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            answer = Path(out.name).read_text(encoding="utf-8")
        else:
            cmd = ["claude", "-p", prompt, "--output-format", "text", "--allowedTools", "Read,Grep,Glob", "--max-turns", "30"]
            r = subprocess.run(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            answer = r.stdout
    first = next((l.strip("*# \t") for l in answer.splitlines() if l.strip()), "")
    if r.returncode != 0 or not first.startswith(("OK", "RETURN")):
        print(f"stop-verify: 검증 세션이 판정 없이 끝났다(종료 코드 {r.returncode})", file=sys.stderr)
        log({"verdict": "none", "rc": r.returncode, "answer": answer[:2000]})
        return 0
    log({"verdict": first.split()[0] if first.split() else first, "answer": answer[:4000]})
    if first.startswith("OK"):
        mark.write_text(stamp)
        return 0
    reason = ("별도 검증자가 아래 사유로 돌려보냈습니다(wf-verify 1). 검증자의 판단을 그대로 따르지 말고 사용자 원문과 작업 기준에 비추어 판단하세요. "
              "근거 없이 정해진 결과가 맞다면, 그 결과에 기대는 코드·검사를 답 전 상태로 되돌리고 사용자에게 추천과 함께 물으세요.\n\n" + answer)
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
