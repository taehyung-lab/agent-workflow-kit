"""요청에서 완료까지의 연결이 끊기지 않았는지 본다. 모델을 부르지 않는다.

  python3 -I evals/chaintest.py

설치되는 글(AGENTS.md 키트 영역, .agents/skills 의 글)이 서로를 가리키는 자리를 따라가 본다. 문장이 좋은지는 보지 않는다.
1. 단계 표: AGENTS.md 「단계」 표의 단계마다 단계 파일이 있고, 파일의 name 이 폴더 이름과 같고, 표의 순서가 요구 확인 → 구현 → 결과 검토다.
2. 넘겨주기: 단계 파일이 다음 단계에 넘기는 것과 원인 단계로 돌아가는 길이 양쪽 파일에 모두 있다(아래 HANDOFFS).
3. 가리킴: 글 속의 링크·`wf-…` 이름·"기본 N"·「절 이름」이 실제 파일·단계·번호·제목에 닿는다.
"""
import re, sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
SKILLS = KIT / ".agents/skills"
STAGES = ["wf-ask", "wf-build", "wf-verify"]
# (주는 파일, 주는 쪽 문구, 받는 파일, 받는 쪽 문구, 무엇의 연결인가)
HANDOFFS = [
    ("AGENTS.md", "요청이 바꿀 곳과 결과를 글자 그대로 정한 변경은 단계 없이 바로 바꾸고 4로 확인한다", "AGENTS.md", "4. 완료라고 말하기 전에", "단계를 건너뛴 변경도 확인을 거친다"),
    ("wf-ask/SKILL.md", "`wf-build` 로 간다", "wf-build/SKILL.md", "확인된 요구", "요구 확인 → 구현"),
    ("wf-ask/map.md", "요구(입력→관찰 장소→기대)", "wf-build/SKILL.md", "요구 기록 표의 행", "지도의 요구 기록 → 구현의 기대값"),
    ("wf-build/SKILL.md", "실행한 명령과 실제 출력을 요구별로 남긴다", "wf-verify/SKILL.md", "요구마다 실행한 명령과 실제 출력으로 확인한다", "구현의 증거 → 결과 검토"),
    ("wf-ask/SKILL.md", "`wf-verify` 의 보고에 밝힌다", "wf-verify/SKILL.md", "묻지 않고 기존 방식대로 정한 표시", "묻지 않고 정한 표시 → 완료 보고"),
    ("wf-build/SKILL.md", "`wf-ask` 로 돌아간다", "wf-ask/SKILL.md", "답이 연 가지를 다시 편다", "구현 중 새 선택 → 요구 확인"),
    ("wf-verify/SKILL.md", "`wf-ask` 로 돌아가 묻는다", "wf-ask/SKILL.md", "남은 항목을 한 번에 보낸다", "확인받지 않은 결정 → 요구 확인"),
    ("wf-verify/SKILL.md", "요구는 `wf-ask`, 설계·코드·검사는 `wf-build`", "AGENTS.md", "원인이 앞 단계에 있으면 그 단계를 다시 호출한다", "검토 반환 → 원인 단계"),
    ("wf-verify/SKILL.md", "승인된 후속 작업이 있으면 이어서 한다", "AGENTS.md", "사용자가 승인한 후속 작업", "완료 → 후속 작업"),
    ("AGENTS.md", "`wf-verify` 의 독립 검토를 받는다", "wf-verify/SKILL.md", "AGENTS.md 기본 4가 정한 작업", "필수 독립 검토"),
]
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
    if "## 끝 조건" not in t or "## 절차" not in t:
        bad.append(f"{name}/SKILL.md 에 절차나 끝 조건 절이 없다")
    if not end.strip():
        bad.append(f"단계 표의 {name} 에 끝 조건이 없다")

# 2. 넘겨주기
for giver, give, taker, take, what in HANDOFFS:
    if give not in texts.get(giver, ""):
        bad.append(f"끊김({what}): {giver} 에 '{give}' 가 없다")
    if take not in texts.get(taker, ""):
        bad.append(f"끊김({what}): {taker} 에 받는 문구 '{take}' 가 없다")

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
print(f"단계 {len(rows)}개·넘겨주기 {len(HANDOFFS)}개·가리킴 검사, {len(bad)} failed")
sys.exit(1 if bad else 0)
