"""전역 진입 문장을 평가 세션에 넣는 길의 시험. 모델을 부르지 않는다.

  python3 -I evals/entrytest.py

보는 것: 키트의 entry.md 에서 문단을 꺼내는가, Claude 세션은 그 세션에서만 사용자 설정을 빼고 그 글을 받는가,
Codex 임시 홈의 AGENTS.md 가 사용자의 것이 아니라 그 글인가, entry 를 주지 않으면 전과 같은가, 사용자 홈의 파일을 바꾸지 않는가.
"""
import hashlib, os, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session  # noqa: E402

checks = []
check = lambda name, ok: checks.append((name, bool(ok)))
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
personal = [Path.home() / ".codex/AGENTS.md", Path.home() / ".claude/CLAUDE.md", Path.home() / ".agents/USER.md"]
before = [digest(p) for p in personal]

text = session.entry_text(HERE.parent)
check("키트의 entry.md 에서 전역 지침 문단을 꺼낸다(울타리와 안내 글은 빼고)", text and text.startswith("# 작업 기준") and "```" not in text and "평가 실행기" not in text)
check("<중앙 키트> 자리에 중앙 키트 경로를 넣는다", text and "<중앙 키트>" not in text and session.CENTRAL_KIT in text)
with tempfile.TemporaryDirectory() as empty:
    check("entry.md 가 없는 키트 커밋이면 None(개인 지침 그대로 돌리고 meta 에 남긴다)", session.entry_text(empty) is None)

claude = session.Claude("/nonexistent", entry=text)
flags = claude._flags()
check("Claude: entry 가 있으면 이 세션에서만 사용자 설정을 빼고(project,local) 그 글을 시스템 지침 끝에 넣는다",
      flags[flags.index("--setting-sources") + 1] == "project,local" and flags[flags.index("--append-system-prompt") + 1] == text)
check("Claude: entry 가 없으면 전과 같은 옵션이다", session.Claude("/nonexistent")._flags() == session.Claude.FLAGS)

home = session._codex_home(text)
try:
    check("Codex: entry 가 있으면 임시 홈의 AGENTS.md 가 그 글이다", (Path(home) / "AGENTS.md").read_text(encoding="utf-8").strip() == text)
    check("Codex: 임시 홈은 사용자 홈이 아니다", Path(home).resolve() != (Path.home() / ".codex").resolve())
finally:
    shutil.rmtree(home, ignore_errors=True)
home = session._codex_home()
try:
    mine = Path.home() / ".codex/AGENTS.md"
    check("Codex: entry 가 없으면 사용자의 AGENTS.md 를 복사한다(있을 때)", (not mine.is_file()) or (Path(home) / "AGENTS.md").read_bytes() == mine.read_bytes())
finally:
    shutil.rmtree(home, ignore_errors=True)

for case in ("installed-kit-only", "switch-project", "kit-unreadable"):
    check(f"{case}: 전역 진입 문장을 받는 사례로 표시돼 있다(global-entry)", (HERE / "cases" / case / "global-entry").is_file())
check("사용자 홈의 전역 지침 파일은 바뀌지 않았다", before == [digest(p) for p in personal])

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
