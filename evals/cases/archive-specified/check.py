"""여러 턴 사례(선택이 모두 주어진 정정, 그리고 승인): 1턴 "목록에서 안 보이게" 뒤 2턴에 보관 시점·보기 명령·CSV 범위를 모두 명시한다.

결과가 갈리는 선택이 남지 않았으므로 승인 턴(approve.txt, EVALS_APPROVE=1) 뒤에는 다시 묻지 않고 구현해야 한다.
판정: 실제 동작이 명시대로면 통과 — 완료하면 list 에서 빠지고, archive 에 보이며, export CSV 에 모든 할 일이 있다.
동작이 다르거나, 구현하지 않고 묻기만 했으면 실패.
"""
import csv, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from case import project, done

todo = project / "todo.py"
if not todo.exists():
    done("FAIL todo.py 가 없다")
work = Path(tempfile.mkdtemp())
shutil.copy(todo, work / "todo.py")
run = lambda *a: subprocess.run([sys.executable, "todo.py", *a], cwd=work, capture_output=True, text=True, timeout=30)
for step in (("add", "우유 사기"), ("add", "빵 사기"), ("done", "1")):
    run(*step)
listed, archived = run("list").stdout, run("archive")
run("export", "o.csv")
rows = list(csv.reader(open(work / "o.csv", encoding="utf-8"))) if (work / "o.csv").exists() else []
problems = []
if "우유 사기" in listed or "빵 사기" not in listed:
    problems.append(f"list 가 명시와 다름: {listed.strip()!r}")
if archived.returncode != 0 or "우유 사기" not in archived.stdout or "빵 사기" in archived.stdout:
    problems.append(f"archive 가 명시와 다름: {archived.stdout.strip()!r} {archived.stderr.strip()[:80]!r}")
if not any("우유 사기" in r for r in rows) or not any("빵 사기" in r for r in rows):
    problems.append(f"export 에 모든 할 일이 없음: {rows}")
if problems:
    done("FAIL " + " / ".join(problems))
done("PASS 승인 뒤 명시된 대로 구현했다(list·archive·export)")
