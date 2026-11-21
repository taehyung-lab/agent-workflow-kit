"""요청에서 완료까지의 연결이 끊기지 않았는지 본다. 모델을 부르지 않는다.

  python3 -I evals/chaintest.py

설치되는 글(AGENTS.md 키트 영역, .agents/skills 의 글)이 서로를 가리키는 자리를 따라가 본다. 문장이 좋은지는 보지 않는다.
1. 단계 표: AGENTS.md 「단계」 표의 단계마다 단계 파일이 있고, 파일의 name 이 폴더 이름과 같고, 표의 순서가 요구 확인 → 구현 → 결과 검토다.
3. 가리킴: 글 속의 링크·`wf-…` 이름·"기본 N"·「절 이름」이 실제 파일·단계·번호·제목에 닿는다.
"""
import re, sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
SKILLS = KIT / ".agents/skills"
STAGES = ["wf-ask", "wf-build", "wf-verify"]
bad = []
agents = (KIT / "AGENTS.md").read_text(encoding="utf-8")
region = agents[agents.index("<!-- agent-workflow-kit:begin -->"):agents.index("<!-- agent-workflow-kit:end -->")]
texts = {"AGENTS.md": region}
for f in sorted(SKILLS.rglob("*.md")):
    texts[f.relative_to(SKILLS).as_posix()] = f.read_text(encoding="utf-8")

# 1. 단계 표
rows = re.findall(r"^\| [^|]+ \| `(wf-[a-z]+)` [^|]*\| ([^|]+) \|$", region, re.M)
if [r[0] for r in rows] != STAGES:
    bad.append(f"단계 표의 순서가 {STAGES} 가 아니다: {[r[0] for r in rows]}")
for name, end in rows:
    f = SKILLS / name / "SKILL.md"
    if not f.is_file():
        bad.append(f"단계 표의 {name} 에 단계 파일이 없다"); continue
    t = f.read_text(encoding="utf-8")
    if not re.search(rf"^name: {name}$", t, re.M):
        bad.append(f"{name}/SKILL.md 의 name 이 폴더 이름과 다르다")
    if "## 끝 조건" not in t:
        bad.append(f"{name}/SKILL.md 에 끝 조건 절이 없다")
    if not end.strip():
        bad.append(f"단계 표의 {name} 에 끝 조건이 없다")

# 고정 문구의 존재는 행동을 증명하지 않는다. 책임의 실행 연결은 tests/work.test.py와
# flowtest.py, 모델의 요구 발견은 goalflow가 확인한다. 여기서는 실제 링크만 검사한다.
# 3. 가리킴
basics = set(re.findall(r"^(\d)\. ", region, re.M))
headings = set()
for f in [KIT / "AGENTS.md", KIT / "README.md", *SKILLS.rglob("*.md"), *(KIT / "docs").glob("*.md"), *(KIT / "evals").glob("*.md")]:
    headings.update(h.strip() for h in re.findall(r"^#+ (.+)$", f.read_text(encoding="utf-8"), re.M))
referring = dict(texts)
referring["README.md"] = (KIT / "README.md").read_text(encoding="utf-8")
for name, text in referring.items():
    base = KIT if name in ("AGENTS.md", "README.md") else (SKILLS / name).parent
    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
        if not re.match(r"[a-z]+://", target) and not (base / target).exists():
            bad.append(f"{name}: 링크 {target} 가 없는 파일을 가리킨다")
    for stage in set(re.findall(r"`(wf-[a-z]+)`", text)):
        if not (SKILLS / stage).is_dir():
            bad.append(f"{name}: 없는 단계 {stage} 를 가리킨다")
    for n in set(re.findall(r"기본 (\d)", text)):
        if n not in basics:
            bad.append(f"{name}: 없는 기본 규칙 번호 {n} 을 가리킨다")
    for title in set(re.findall(r"「([^」]+)」", text)):
        if not any(h == title or h.startswith(title) for h in headings):
            bad.append(f"{name}: 「{title}」 이라는 제목의 절이 없다")

for b in bad:
    print("FAIL " + b)
print(f"단계 {len(rows)}개·가리킴 검사, {len(bad)} failed")
sys.exit(1 if bad else 0)
