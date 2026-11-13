"""과제 판정기들이 같이 쓰는 틀: 끝난 프로젝트를 임시 폴더에 복사해 공개 명령으로만 관찰하고, 항목별 통과·실패를 JSON 으로 낸다.

판정기(<과제>/oracle.py)는 Judge 를 만들어 항목마다 check(이름, 종류, 함수)를 부른다. 함수가 AssertionError 를 내면 실패, 그 밖의 예외도 실패다
(공개 명령이 죽는 것은 사용자가 보는 실패다). 종류는 given(요청·운영 문서가 글자 그대로 정한 것)과 decision(사용자 답이 정한 것)이다.
출력의 automated_valid·observation_complete·cases 는 goalflow/oracle.py 와 같은 뜻이라 compare.py·table.py 가 그대로 읽는다.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path


class Judge:
    def __init__(self, project, script, data_env):
        self.cases, self.script, self.data_env = [], script, data_env
        self.tmp = Path(tempfile.mkdtemp(prefix="taskcheck-"))
        self.root = self.tmp / "p"
        shutil.copytree(project, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__", "work", ".claude", ".agents", ".codex"))
        self.pristine = (self.root / "data.json").read_bytes()

    def fresh(self):
        """끝난 프로젝트의 자료 파일로 되돌린다(항목끼리 서로 영향을 주지 않게)."""
        (self.root / "data.json").write_bytes(self.pristine)

    def run(self, *args):
        """공개 명령 한 번. (종료 코드, 표준 출력의 JSON 또는 None)."""
        p = subprocess.run([sys.executable, self.script, *[str(a) for a in args]], cwd=self.root, capture_output=True, text=True, timeout=20,
                           env={**os.environ, self.data_env: str(self.root / "data.json")})
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = None
        return p.returncode, out

    def ok(self, *args):
        code, out = self.run(*args)
        assert code == 0 and out is not None, {"args": args, "exit": code}
        return out

    def refused(self, *args):
        code, _ = self.run(*args)
        assert code != 0, {"args": args, "expected": "거절(0 이 아닌 종료 코드)"}

    def check(self, name, kind, fn):
        self.fresh()
        try:
            fn()
            passed, detail = True, None
        except AssertionError as e:
            passed, detail = False, str(e.args[0] if e.args else "")[:400]
        except Exception as e:
            passed, detail = False, repr(e)[:400]
        self.cases.append({"name": name, "kind": kind, "passed": passed, "detail": detail})

    def public_tests(self):
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=self.root, capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-300:]

    def finish(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        c = self.cases
        result = {"automated_valid": all(x["passed"] for x in c), "observation_complete": True,
                  "passed": sum(x["passed"] for x in c), "failed": sum(not x["passed"] for x in c), "total": len(c),
                  "failed_given": [x["name"] for x in c if not x["passed"] and x["kind"] == "given"],
                  "failed_decision": [x["name"] for x in c if not x["passed"] and x["kind"] == "decision"], "cases": c}
        print(json.dumps(result, ensure_ascii=False, indent=1))
        sys.exit(0 if result["automated_valid"] else 1)
