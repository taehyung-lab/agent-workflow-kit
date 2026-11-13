"""프로젝트 지도에 적힌 경로가 없어졌을 때 맥락 도구가 알려 주는지 본다. 모델을 부르지 않는다.

  python3 -I evals/maptest.py

파일이 있는지만 보는 검사다. 그 파일이 그 일의 올바른 근거인지는 이 검사로 알 수 없다.
"""
import subprocess, sys, tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
TOOL = KIT / ".agents/skills/wf-context/context.py"
bad = []


def inspect(project_part):
    d = Path(tempfile.mkdtemp(prefix="maptest-"))
    (d / "docs").mkdir(); (d / "docs/contract.md").write_text("계약", encoding="utf-8"); (d / "package.json").write_text("{}", encoding="utf-8")
    (d / "AGENTS.md").write_text("<!-- agent-workflow-kit:begin -->\n키트 영역의 `.agents/skills/none.md` 는 보지 않는다\n<!-- agent-workflow-kit:end -->\n\n## 프로젝트 지도\n\n" + project_part, encoding="utf-8")
    return subprocess.run([sys.executable, "-I", str(TOOL), "inspect", str(d)], capture_output=True, text=True).stdout


LINE = "지금 없는 경로"
out = inspect("| 코드를 고치기 전 | `docs/contract.md`, [패키지](package.json) | 계약 |\n| 결과를 확인할 때 | `npm test`, `v3.7.2`, https://example.com/a.md, `미확인` | 명령 |\n")
if LINE in out:
    bad.append("있는 경로·명령·버전·주소만 적었는데 없는 경로가 있다고 한다: " + out[-300:])
out = inspect("| 코드를 고치기 전 | `docs/gone.md`, [옛 진입점](src/main.ts#L10), `docs/contract.md` | 계약 |\n")
row = next((l for l in out.splitlines() if LINE in l), "")
if not ("docs/gone.md" in row and "src/main.ts" in row and "contract.md" not in row and "none.md" not in row):
    bad.append("없는 경로 두 개만 알려야 한다: " + (row or out[-300:]))

for b in bad:
    print("FAIL " + b)
print(f"프로젝트 지도 경로 확인 2개, {len(bad)} failed")
sys.exit(1 if bad else 0)
