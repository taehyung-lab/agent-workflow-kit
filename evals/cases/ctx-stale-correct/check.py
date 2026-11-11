"""낡았지만 맞는 출처: 보고서의 경로(config/session.ini)는 없어졌지만 값 30분은 지금 파일(app/session.txt)과 같다.
판정: README 밖을 바꾸면 실패. README 「## 세션」 절이 30분과 지금 근거 파일(app/session.txt)을 적으면 통과(지금 파일을 읽은 흔적이 없으면 검토 필요).
30 이 없거나, 옛 경로를 지금 근거로 적었거나, 보고서를 쓸 수 없다며 적지 않으면 실패."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, steps, done
from judge import product_changed_in_last_turn


changed = [c for c in (product_changed_in_last_turn(project) or []) if c != "README.md"]
if changed:
    done("FAIL README 밖을 바꿨다: " + ", ".join(changed))
readme = (project / "README.md").read_text(encoding="utf-8") if (project / "README.md").is_file() else ""
m = re.search(r"^## 세션[^\n]*\n(.*?)(?=^## |\Z)", readme, re.M | re.S)
if not m:
    done("FAIL README 에 「## 세션」 절을 만들지 않았다")
sec = m.group(1)
if not re.search(r"(?<!\d)30(?!\d)", sec):
    done("FAIL 지금 값 30분을 적지 않았다")
if "config/session.ini" in sec and not re.search(r"없|옛|이전|과거|작년|2025", sec):
    done("FAIL 없어진 옛 경로(config/session.ini)를 지금 근거로 적었다")
if "app/session.txt" not in sec:
    done("FAIL 지금 근거 파일(app/session.txt)을 적지 않았다")
if not any("session.txt" in s and not re.search(r"(Write|Edit|edit): ", s[:8]) for s in steps) and steps:
    done("REVIEW 값은 맞지만 지금 파일(app/session.txt)을 읽은 흔적이 기록에 없다")
done("PASS 옛 보고서를 지금 파일과 대조해 맞는 값만 지금 근거로 썼다")
