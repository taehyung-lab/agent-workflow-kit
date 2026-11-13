"""평가가 재려는 것이 평가 밖으로 새지 않았는지 본다. 모델을 부르지 않는다.

  python3 -I evals/leaktest.py

1. 설치되는 지침(AGENTS.md 키트 영역, .agents/skills 의 글)에 평가 과제 고유의 낱말이 없어야 한다.
   지침의 예시가 과제의 요청이나 정답과 같으면 그 과제의 통과는 예시 덕일 수 있다(2026-11-12: 예시가 과제 정답과 같아 3/3, 예시를 바꾸자 1/3).
   낱말 목록은 evals/leak-words.txt 다. 새 과제를 만들면 그 과제에만 나오는 낱말을 더한다.
2. 표본(evals/cases·evals/holdout)에 실행한 사람의 홈 경로가 없어야 한다. 실제 기록을 표본으로 옮길 때는 /Users/USER 로 바꾼다.
"""
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
problems = []

words = [w.strip() for w in (HERE / "leak-words.txt").read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
agents = (KIT / "AGENTS.md").read_text(encoding="utf-8")
region = agents[agents.index("<!-- agent-workflow-kit:begin -->"):agents.index("<!-- agent-workflow-kit:end -->")]
installed = {"AGENTS.md(키트 영역)": region}
for f in sorted((KIT / ".agents/skills").rglob("*")):
    if f.is_file() and f.suffix in (".md", ".txt"):
        installed[f.relative_to(KIT).as_posix()] = f.read_text(encoding="utf-8")
# 검토자 지시문도 모델이 읽는 설치 글이다
verify = (KIT / ".agents/skills/wf-verify/verify.py").read_text(encoding="utf-8")
m = re.search(r'VERIFIER_PROMPT = """(.*?)"""', verify, re.S)
if m:
    installed["wf-verify/verify.py(검토자 지시문)"] = m.group(1)
for name, text in installed.items():
    for w in words:
        if w in text:
            problems.append(f"{name}: 평가 과제의 낱말 '{w}' 가 설치되는 지침에 있다(예시를 과제와 무관한 것으로 바꾼다)")

HOME = re.compile(r"/(?:Users|home)/(?!USER\b)[A-Za-z0-9._-]+")
for root in (HERE / "cases", HERE / "holdout"):
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = sorted(set(HOME.findall(text)))
        if found:
            problems.append(f"{f.relative_to(KIT).as_posix()}: 홈 경로 {', '.join(found[:3])} 가 있다(/Users/USER 로 바꾼다)")

for p in problems:
    print("FAIL " + p)
print(f"{'0' if problems else '2'} passed, {len(problems)} failed" if problems else f"설치 지침 {len(installed)}개·낱말 {len(words)}개·표본 홈 경로 검사 통과, 0 failed")
sys.exit(1 if problems else 0)
