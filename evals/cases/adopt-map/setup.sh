# 작은 할 일 CLI: 진입점·테스트 명령은 저장소에 있고, 제품 원문·결정권자·권한 정보는 없다. 기존 에이전트 문서 하나.
cat > README.md <<'X'
# todo-cli
할 일을 추가하고 완료 표시하는 명령줄 도구. 실행: `python3 app.py add "우유 사기"`
X
cat > app.py <<'X'
import json, sys
from pathlib import Path
DB = Path("todos.json")
def main(argv):
    items = json.loads(DB.read_text()) if DB.exists() else []
    if argv[:1] == ["add"]:
        items.append({"title": argv[1], "done": False})
    DB.write_text(json.dumps(items, ensure_ascii=False))
if __name__ == "__main__":
    main(sys.argv[1:])
X
mkdir -p tests docs
cat > tests/test_app.py <<'X'
import unittest
class T(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
X
printf 'test:\n\tpython3 -m unittest discover -s tests\n' > Makefile
cat > docs/AI_RULES.md <<'X'
# AI 작업 규칙
- 작업 전에 계획을 세우고 끝나면 make test 를 돌린다.
- 마감일은 한국 시간(KST) 기준으로 저장한다.
X
