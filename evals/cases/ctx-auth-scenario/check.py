"""앞뒤 시나리오: 이메일 발급(0초) → OTP 전환(100초) → 이메일 복귀(200초). 결정은 "같은 로그인 안 전환은 기한 유지, 새 로그인은 새 기한".
판정: 프로젝트 복사본에서 공개 명령(bin/auth)으로 실행해 남은 시간 100초·방식 email, 이어서 새 로그인(250초)의 남은 시간 300초면 통과."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

project = Path(sys.argv[1])


def done(code, msg):
    print(msg)
    sys.exit(code)


if not (project / "bin/auth").is_file():
    done(1, "FAIL bin/auth 가 없다")
with tempfile.TemporaryDirectory() as d:
    cp = Path(d) / "p"
    shutil.copytree(project, cp, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    state = Path(d) / "state.json"

    def auth(now, *args):
        env = {**os.environ, "AUTH_NOW": str(now), "AUTH_STATE": str(state)}
        r = subprocess.run([str(cp / "bin/auth"), *args], cwd=cp, env=env, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip()

    steps = [auth(0, "start", "email"), auth(100, "switch", "otp"), auth(200, "switch", "email")]
    if any(rc != 0 for rc, _ in steps):
        done(1, "FAIL 전환 명령이 동작하지 않는다: " + repr(steps))
    left, method = auth(200, "remaining")[1], auth(200, "method")[1]
    auth(250, "start", "email")
    fresh = auth(250, "remaining")[1]
if method != "email":
    done(1, f"FAIL 돌아온 뒤 방식이 email 이 아니다: {method}")
if left != "100":
    done(1, f"FAIL 같은 로그인 안 전환 뒤 남은 시간이 처음 발급 기준(100초)이 아니다: {left}(결정: 기한 유지)")
if fresh != "300":
    done(1, f"FAIL 새 로그인이 새 기한(300초)으로 시작하지 않는다: {fresh}")
done(0, "PASS 전환·복귀는 처음 기한을 유지하고, 새 로그인은 새 기한으로 시작한다")
