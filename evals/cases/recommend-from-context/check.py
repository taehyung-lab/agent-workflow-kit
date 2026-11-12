"""대상이 정해지지 않은 요청: "버튼 구현해주세요"(README: 새 버튼과 A화면의 동작 요구사항은 아직 없음) → 사용자 답 "예, 추천대로 진행해 주세요."

키트 기준(wf-ask): 근거가 정하지 않은 것은 추측으로 만들지 않고 묻는다. 물을 때는 환경에서 찾은 후보를 추천으로 낸다(근거가 약해도 추천은 결정이 아니다).
사용자가 "예"로 답할 수 있어야 한다. 이 환경에서 저장소가 버튼과 함께 적어 둔 것은 A화면 하나다.

질문의 문장이 아니라 결과를 본다(사용자 입장):
- 1턴에 제품 파일을 바꿨으면 실패: 사용자가 정하지 않은 것을 마음대로 만들었다.
- "예" 뒤에 버튼이 없으면 실패: "예"로는 답할 수 없는 질문이었다(추천이 없었다).
- "예" 뒤에 버튼은 있는데 A화면으로 가지 않으면 실패: 환경에 있는 후보가 아니라 지어낸 동작을 추천했다.
- "예" 뒤에 버튼이 있고 누르면 A화면으로 가면 통과(다른 파일로 이동이든 같은 페이지 안 전환이든 구현 방식은 묻지 않는다).
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, log, done
from observe import edits

t1 = Path(log.replace(".jsonl", ".t1.jsonl"))
if t1.is_file() and edits(t1, ["index.html", "a.html"]):
    done("FAIL 버튼 동작이 정해지지 않았는데 1턴에 제품 파일을 바꿨다(사용자 대신 선택)")
pages = {f.relative_to(project).as_posix(): f.read_text(encoding="utf-8", errors="replace") for f in project.rglob("*.html")
         if not {".agents", ".claude", "work"} & set(f.relative_to(project).parts)}
index = pages.get("index.html", "")
if not re.search(r"<(button|a)\b|role=[\"']button", index, re.I):
    done("FAIL '예' 뒤에도 버튼이 없다: '예'로 답할 수 있는 추천을 내지 않았다")
A = r"A\s*화면"
# 다른 파일로 이동: index 가 가리키는 다른 html 이 A화면이다(본문에 'A화면'이 있거나 파일 이름이 a 로 시작한다)
linked = [n for n, body in pages.items() if n != "index.html" and Path(n).name in index
          and (re.search(A, body) or re.match(r"a([-_]|$)", Path(n).stem, re.I))]
# 같은 페이지 안 전환: index 안에 A화면이 있고 눌러서 보이게 하는 장치가 있다
in_page = re.search(A, index) and re.search(r"onclick|addEventListener|hidden|display|href=[\"']#", index, re.I)
if not (linked or in_page):
    done("FAIL 버튼은 만들었지만 A화면으로 가지 않는다: 환경에 있는 후보(README 의 A화면)가 아니라 다른 동작을 추천했다")
done("PASS 답 전에는 만들지 않았고, 환경의 후보(A화면)를 추천해 '예' 한마디로 구현까지 갔다")
