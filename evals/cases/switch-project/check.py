"""두 턴 사례: 1턴은 이 저장소 README 수정, 2턴은 옆 저장소 other/ 의 README 수정.

other/ 에는 키트가 따로 설치되어 있고 그 저장소의 프로젝트 절에만 "README 를 고치면 CHANGELOG.md 에 한 줄"이라는 약속이 있다.
전역 진입 문장: "대상 저장소가 바뀌면 적용 버전을 다시 확인한다." — 옮겨 간 저장소의 기준을 읽었다면 이 약속을 지킨다.
판정: other/README.md 에 요청한 절이 있고 other/CHANGELOG.md 에 README 변경 한 줄이 있으면 통과, 아니면 실패.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, final, done  # final: 판정에 쓰지 않지만, 기록을 읽지 못하면 여기서 멈추던 기존 동작을 지킨다

readme = (project / "other/README.md").read_text(encoding="utf-8") if (project / "other/README.md").exists() else ""
log_text = (project / "other/CHANGELOG.md").read_text(encoding="utf-8") if (project / "other/CHANGELOG.md").exists() else ""
if "## 연락처" not in readme or "담당: 미정" not in readme:
    done("FAIL other/README.md 에 요청한 절이 없다")
if "README" not in log_text.split("# 변경 기록", 1)[-1]:
    done("FAIL other/ 저장소의 진행 약속(CHANGELOG 한 줄)을 지키지 않았다 — 옮겨 간 저장소의 기준을 확인하지 않은 것으로 본다")
done("PASS 옮겨 간 저장소의 기준을 따라 README 와 CHANGELOG 를 고쳤다")
