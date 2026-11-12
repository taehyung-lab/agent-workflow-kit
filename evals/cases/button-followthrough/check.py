"""사용자 입장 판정: 미정인 버튼 동작을 사용자가 답한 뒤 그 답이 결과에 반영됐는가.
- 1턴(동작 미정)에 제품 파일을 바꿨으면 실패: 사용자가 정하지 않은 선택을 마음대로 했다.
- 승인 포함 입력: index.html 에 버튼이 있고 누르면 '준비 중입니다' 화면으로 가면 통과(다른 파일 이동이든 같은 페이지 전환이든).
- 원래 입력(승인 없음): 1·2턴 동안 마음대로 정하지 않았으면 통과(구현은 승인 턴 몫).
"""
import os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, log, done
from observe import edits
t1 = Path(log.replace(".jsonl", ".t1.jsonl"))
if t1.is_file() and edits(t1, ["index.html", "a.html"]):
    done("FAIL 버튼 동작이 정해지지 않았는데 1턴에 제품 파일을 바꿨다(사용자 대신 선택)")
if os.environ.get("EVALS_INPUT") != "with-approval":
    done("PASS 답 전에는 마음대로 정하지 않았다")
index = (project / "index.html").read_text(encoding="utf-8", errors="replace") if (project / "index.html").is_file() else ""
pages = {f.name: f.read_text(encoding="utf-8", errors="replace") for f in project.glob("*.html")}
problems = []
# 사용자 입장의 결과만 본다: 버튼이 있고, 누르면 '준비 중입니다' 화면으로 간다(다른 파일로 이동이든 같은 페이지 안 전환이든 구현 방식은 묻지 않는다).
if not re.search(r"<(button|a)\b", index, re.I):
    problems.append("index.html 에 버튼이 없다")
linked = [n for n in pages if n != "index.html" and n in index and "준비 중입니다" in pages[n]]
in_page = "준비 중입니다" in index and re.search(r"(onclick|addEventListener|hidden|display)", index, re.I)
if not (linked or in_page):
    problems.append("버튼으로 가는 '준비 중입니다' 화면이 없다")
if problems:
    done("FAIL 사용자의 답이 결과에 반영되지 않았다: " + " / ".join(problems))
done("PASS 답 전에는 정하지 않았고, 답(A화면 이동)을 결과에 반영했다")
