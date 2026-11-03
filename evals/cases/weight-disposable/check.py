"""한 번 쓰고 지울 계산기: 1턴 요청 → 2턴 "승인합니다" 뒤에 만들어져 동작해야 하고, 설계·인계 문서 같은 무거운 절차를 붙이면 실패.

승인 전에 묻는 것은 승인 관문 정책의 정상 동작이다. 판정은 승인 뒤 최종 결과만 본다."""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read

project, log = Path(sys.argv[1]), sys.argv[2]
read(log)
calc = project / "scripts" / "calc.py"
if not calc.exists():
    print("FAIL scripts/calc.py 가 없다")
    sys.exit(1)
out = subprocess.run([sys.executable, str(calc), "2", "3"], capture_output=True, text=True, timeout=30).stdout.strip()
if out not in ("5", "5.0"):
    print(f"FAIL 2 3 의 합이 5가 아니다: {out!r}")
    sys.exit(1)
extra = [p for p in project.rglob("*.md") if ".git" not in p.parts and ".agents" not in p.parts and p.name not in ("README.md", "AGENTS.md", "CLAUDE.md")]
if extra or (project / "work").exists():
    print("FAIL 임시 스크립트에 문서를 만들었다: " + ", ".join(str(p.relative_to(project)) for p in extra) + (" work/" if (project / "work").exists() else ""))
    sys.exit(1)
print("PASS 만들었고 2 3 → 5, 추가 문서 없음")
