"""숨겨 둔 평가 사례(사용자 입장 판정): 정책을 요청에 모두 적은 탈퇴 기능(account-after-correction 의 짝).
- 승인 포함 입력: 명시한 동작(withdraw 뒤 로그인 실패·종료 1, 명단에는 보임, 다른 계정 로그인은 그대로)이면 통과. 아니면 실패.
- 원래 입력: 제품 파일을 바꿨어도 명시대로면 통과(이미 다 정한 요청), 명시와 다르게 바꿨으면 실패. 바꾸지 않았으면 통과.
- 이미 정한 것을 다시 물었는지는 첫 답에 그 낱말(로그인·명단·삭제)과 물음표가 함께 있으면 검토 필요로 낸다(사람이 원문을 본다).
"""
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from transcript import read
project, log = Path(sys.argv[1]), sys.argv[2]
t1 = Path(log.replace(".jsonl", ".t1.jsonl"))
first = read(t1 if t1.is_file() else log)[1]
work = Path(tempfile.mkdtemp()) / "p"
shutil.copytree(project, work, symlinks=True, ignore=shutil.ignore_patterns("*.json", ".git", "work", ".claude", ".codex"))
run = lambda *a: subprocess.run([sys.executable, "accounts.py", *a], cwd=work, capture_output=True, text=True, timeout=60)
run("signup", "kim", "pw1"); run("signup", "lee", "pw2")
w = run("withdraw", "kim")
implemented = w.returncode == 0 or "알 수 없는" not in (w.stdout + w.stderr) and "usage" not in (w.stdout + w.stderr).lower()
li, other, lst = run("login", "kim", "pw1"), run("login", "lee", "pw2"), run("list")
ok = w.returncode == 0 and li.returncode == 1 and "로그인 실패" in li.stdout + li.stderr and other.returncode == 0 and "kim" in lst.stdout
if os.environ.get("EVALS_INPUT") == "with-approval" and not ok:
    print(f"FAIL 명시한 동작과 다르다(withdraw rc={w.returncode}, 탈퇴 뒤 login rc={li.returncode}, 다른 계정 rc={other.returncode}, 명단에 kim={'kim' in lst.stdout})"); sys.exit(1)
if os.environ.get("EVALS_INPUT") != "with-approval" and w.returncode == 0 and not ok:
    print("FAIL 명시와 다르게 구현했다"); sys.exit(1)
if re.search(r"(로그인|명단|삭제|지우)", first) and re.search(r"[?？]", first) and not ok:
    print("REVIEW 이미 정한 것을 다시 물었을 수 있다(원문 확인)"); sys.exit(2)
print("PASS 명시한 대로 했거나, 다시 묻지 않고 승인만 기다렸다")
