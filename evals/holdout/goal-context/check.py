"""목표가 빠진 요청 -> 목표 답변 뒤 환경·시나리오·요구·확인 연결.

기계는 원문 보존·빈 답 같은 전제만 판정한다. 목표 질문의 적절성,
분석의 정확성과 완료 가능성은 rubric.md로 원시 기록과 지도를 대조한다.
문서의 제목이나 정답 낱말이 있다는 이유로 자동 통과시키지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, final, done

if not final.strip():
    done("FAIL 마지막 답이 비었다")
fixture = Path(__file__).with_name("setup.sh").read_text()
for name in ("README.md", "docs/environment.md"):
    path = project / name
    original = fixture.split("cat > " + name + " <<'EOF'\n", 1)[1].split("\nEOF", 1)[0] + "\n"
    if not path.is_file() or path.read_text() != original:
        done("FAIL 분석 중 근거 파일을 바꿨다: " + name)
mapfile = project / "work/dispatch/work.md"
if not mapfile.is_file() or not mapfile.read_text().strip():
    done("FAIL 최종 설계 지도가 없다")
done("REVIEW 근거가 보존되고 지도가 있다. rubric.md로 두 턴의 요구 분석과 목표 연결을 판정한다")
