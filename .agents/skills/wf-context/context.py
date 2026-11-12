"""맥락 확인 도구(읽기 전용): 지금 작업하는 저장소가 어디·어느 버전인지 도구가 관찰한 값만 낸다. 요청의 뜻·범위·승인은 판단하지 않는다.

  python3 .agents/skills/wf-context/context.py inspect [폴더]   사람·에이전트가 직접 볼 때(기본 폴더: 지금 폴더)
  python3 .agents/skills/wf-context/context.py hook            세션 시작 훅(Claude Code SessionStart)이 부른다

내는 것: 실경로, 저장소 맨 위, 브랜치·해소한 커밋, 로컬 추적 브랜치와의 차이(마지막 fetch 기준), 작업 트리 변경(파일 이름만),
설치된 키트·버전 기록(`*.version` 첫 줄, package.json 의 name@version), 같은 저장소의 다른 worktree(진단용), work/*/work.md 지도 제목.
내지 않는 것: 파일 내용(env·비밀 파일 포함), diff, 원격 URL. 어떤 실패도 막지 않는다: 늘 종료 코드 0 이고, git 이 없거나 저장소가 아니면 그 사실만 적는다.
대상과 근거를 구별하는 판단은 AGENTS.md 기본 1, 기록 방법은 wf-ask/map.md가 맡는다.
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

LIMIT_FILES = 15  # 변경 파일 이름을 몇 개까지 적을지
LIMIT_TREES = 10  # 다른 worktree 를 몇 개까지 적을지
SKIP_DIRS = {".git", "node_modules", "work", "__pycache__", ".venv", "venv", "dist", "build"}
VERSION_LINE = re.compile(r"^[\w.+\-/@: ]{1,100}$")  # 버전·커밋처럼 보이는 줄만 적는다(그 밖의 내용은 옮기지 않는다)


def git(root, *args):
    """git 명령의 출력(실패·git 없음·시간 초과면 None)."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def changes(root):
    out = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    if out is None:
        return None
    entries, recs = [], out.split("\0")
    i = 0
    while i < len(recs):
        rec = recs[i]
        i += 1
        if len(rec) < 4:
            continue
        code, name = rec[:2], rec[3:]
        if code[0] in "RC":
            i += 1  # 이름 바꾸기는 원래 이름이 다음 칸에 온다(적지 않는다)
        entries.append((code, name))
    kinds = {"수정": 0, "추가": 0, "삭제": 0, "추적 안 함": 0, "기타": 0}
    for code, _ in entries:
        k = ("추적 안 함" if code == "??" else "삭제" if "D" in code else "추가" if "A" in code
             else "수정" if ("M" in code or "R" in code or "T" in code) else "기타")
        kinds[k] += 1
    return entries, kinds


def versions(root):
    """설치된 키트·패키지의 버전 기록. 프로젝트별 지식 없이 읽을 수 있는 것만: `*.version` 첫 줄, package.json 의 name@version."""
    found, seen = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        seen += 1
        if seen > 3000:  # 아주 큰 폴더(예: 홈)에서 오래 걸리지 않게 멈춘다
            found.append("(폴더가 많아 일부만 확인)")
            break
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS and not (depth >= 3)]
        for f in sorted(filenames):
            p = Path(dirpath, f)
            rel = p.relative_to(root).as_posix()
            if f.endswith(".version") and p.is_file() and not p.is_symlink():
                try:
                    line = p.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
                except (OSError, IndexError):
                    continue
                if VERSION_LINE.match(line):
                    found.append(f"{rel}: {line}")
            elif f == "package.json" and depth <= 2 and p.is_file() and not p.is_symlink():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                name, ver = str(data.get("name") or ""), str(data.get("version") or "")
                if ver and VERSION_LINE.match(f"{name}@{ver}"):
                    found.append(f"{rel}: {name}@{ver}" if name else f"{rel}: {ver}")
    return found


def worktrees(root, top):
    out = git(root, "worktree", "list", "--porcelain")
    if out is None:
        return None
    trees, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur.get("worktree"):
                trees.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["worktree"] = line[9:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif line.startswith("HEAD "):
            cur["head"] = line[5:12]
        elif line == "detached":
            cur["branch"] = "(분리된 HEAD)"
    here = os.path.realpath(top)
    return [t for t in trees if os.path.realpath(t["worktree"]) != here]


def maps(root):
    found = []
    for f in sorted(Path(root).glob("work/*/work.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), "(제목 없음)")
        has = "맥락 절 있음" if re.search(r"^## 맥락", text, re.M) else "맥락 절 없음"
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        found.append(f"{f.relative_to(root).as_posix()} — {title[:80]} ({has}, 수정 {when})")
    return found


def inspect(start, session_dir=None):
    """관찰한 값을 사람이 읽을 줄로 낸다(정보만)."""
    lines = []
    real = os.path.realpath(start)
    top = (git(real, "rev-parse", "--show-toplevel") or "").strip()
    lines.append(f"실경로: {real}")
    if session_dir and os.path.realpath(session_dir) != real:
        lines.append(f"세션 폴더: {os.path.realpath(session_dir)}")
    if not top:
        reason = "git 을 찾지 못했다" if _no_git() else "git 저장소가 아니다"
        lines.append(f"저장소: 확인 못 함({reason}). 커밋·변경·worktree 정보 없음")
        root = real
    else:
        root = top
        if os.path.realpath(top) != real:
            lines.append(f"저장소 맨 위: {top}")
        branch = (git(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip() or "(분리된 HEAD)"
        head = (git(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        subject = (git(root, "log", "-1", "--format=%cs %s") or "").strip()
        lines.append(f"브랜치: {branch} / 커밋: {head[:12] or '(아직 없음)'}" + (f" ({subject[:70]})" if subject else ""))
        up = (git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "").strip()
        if up:
            lr = (git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}") or "").split()
            if len(lr) == 2:
                lines.append(f"추적 브랜치: {up} 보다 앞 {lr[0]} · 뒤 {lr[1]} (로컬에 받아 둔 기록 기준, 원격 최신 여부는 아님)")
        ch = changes(root)
        if ch is None:
            lines.append("작업 트리: 확인 못 함")
        else:
            entries, kinds = ch
            if not entries:
                lines.append("작업 트리: 변경 없음")
            else:
                summary = ", ".join(f"{k} {v}" for k, v in kinds.items() if v)
                names = ", ".join(n for _, n in entries[:LIMIT_FILES]) + (f" 외 {len(entries) - LIMIT_FILES}개" if len(entries) > LIMIT_FILES else "")
                lines.append(f"작업 트리: 변경 {len(entries)}개({summary}) — {names}")
    vers = versions(root)
    lines.append("버전 기록: " + ("; ".join(vers) if vers else "없음"))
    if top:
        trees = worktrees(root, top)
        if trees:
            shown = "; ".join(f"{t['worktree']} ({t.get('branch', '?')})" for t in trees[:LIMIT_TREES])
            more = f" 외 {len(trees) - LIMIT_TREES}개" if len(trees) > LIMIT_TREES else ""
            lines.append(f"같은 저장소의 다른 worktree {len(trees)}개: {shown}{more}")
    found = maps(root)
    lines.append("작업 지도: " + ("; ".join(found) if found else "없음"))
    return lines


def _no_git():
    from shutil import which
    return which("git") is None


HEADER = ("[맥락 정보] 도구가 관찰한 값이다(요청의 뜻·범위·승인과 무관, 아무것도 막지 않는다). "
          "결과를 둘 대상과 읽는 근거를 구별할 때 쓰고, 다른 경로·버전의 자료는 현재 파일과 대조한 뒤 쓴다(AGENTS.md 기본 1).")


def hook():
    """세션 시작 훅: 표준 입력의 사건 정보(있으면)를 읽고, 관찰 값을 추가 맥락(JSON)으로 낸다. 늘 종료 코드 0."""
    event, source, cwd = "SessionStart", "", None
    try:
        import select
        if not sys.stdin.isatty() and select.select([sys.stdin], [], [], 0.5)[0]:
            data = json.loads(sys.stdin.read() or "{}")
            if isinstance(data, dict):
                event = str(data.get("hook_event_name") or event)
                source, cwd = str(data.get("source") or ""), data.get("cwd")
    except Exception:
        pass
    root = Path(__file__).resolve().parents[3]  # 설치 위치: <프로젝트>/.agents/skills/wf-context/context.py
    try:
        body = inspect(root, cwd if isinstance(cwd, str) else None)
    except Exception:
        return 0
    text = HEADER + (f" (사건: {source})" if source else "") + "\n" + "\n".join("- " + l for l in body)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text[:4000]}}, ensure_ascii=False))
    return 0


def main(args):
    if args[:1] == ["hook"]:
        return hook()
    if args[:1] != ["inspect"]:
        print(__doc__.strip().splitlines()[2].strip() + "\n" + __doc__.strip().splitlines()[3].strip(), file=sys.stderr)
        return 0
    start = args[1] if len(args) > 1 else os.getcwd()
    if not os.path.isdir(start):
        print(f"폴더가 아니다: {start}")
        return 0
    print(HEADER)
    for line in inspect(start):
        print("- " + line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # 정보 도구라 실패해도 막지 않는다
        print(f"[맥락 정보] 확인하지 못했다: {e.__class__.__name__}")
        sys.exit(0)
