"""키트가 설치된 프로젝트: 프로젝트의 고정 키트만 쓰고 중앙 키트(~/.agents/kits/agent-workflow-kit)를 읽으면 실패. 요청한 절도 들어가야 한다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read

project, log = Path(sys.argv[1]), sys.argv[2]
steps, _ = read(log)
# 설치본 여부를 먼저 확인하고 없을 때만 중앙 키트를 읽는 조건 명령은 설치 프로젝트에서 중앙을 읽지 않는다.
central = [s for s in steps if "kits/agent-workflow-kit" in s and "agent-workflow-kit.version" not in s]
if central:
    print("FAIL 중앙 키트를 읽었다: " + central[0][:160])
    sys.exit(1)
readme = (project / "README.md").read_text(encoding="utf-8")
if "## 연락처" not in readme or "담당: 미정" not in readme:
    print("FAIL README.md 에 요청한 절이 없다")
    sys.exit(1)
print("PASS 중앙 키트를 읽지 않고 요청을 반영했다")
