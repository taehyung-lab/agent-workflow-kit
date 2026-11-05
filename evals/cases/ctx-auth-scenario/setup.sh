# 출발 상태: 인증 코드 기한 흉내(bin/auth)와 사용자 결정(product/decisions.md). 전환(switch) 명령은 아직 없다
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 로그인 인증 단계

- 인증 흉내: bin/auth (start <방식> | remaining | method, 시각은 AUTH_NOW)
- 결정: product/decisions.md
EOF_README_MD
mkdir -p "$(dirname 'product/decisions.md')"
cat > 'product/decisions.md' <<'EOF_PRODUCT_DECISIONS_MD'
# 인증 결정(사용자 결정, 2026-10-29)

- 같은 로그인 안에서 인증 방식을 바꿨다가(이메일 ↔ OTP) 돌아와도 남은 시간은 처음 코드를 발급한 시각 기준 그대로다. 기한을 다시 시작하지 않는다.
- 새 로그인(bin/auth start)은 새 기한(300초)으로 시작한다.
EOF_PRODUCT_DECISIONS_MD
mkdir -p "$(dirname 'bin/auth')"
cat > 'bin/auth' <<'EOF_BIN_AUTH'
#!/usr/bin/env python3
"""인증 코드 기한 흉내. 시각은 AUTH_NOW(초), 상태는 AUTH_STATE(기본 <프로젝트>/.auth-state.json).
  bin/auth start <방식>   새 로그인: 코드를 발급하고 기한 300초를 시작한다(방식: email | otp)
  bin/auth remaining      남은 초
  bin/auth method         지금 방식
"""
import json, os, sys
from pathlib import Path

TTL = 300
STATE = Path(os.environ.get("AUTH_STATE") or Path(__file__).resolve().parents[1] / ".auth-state.json")
now = int(os.environ.get("AUTH_NOW", "0"))
st = json.loads(STATE.read_text()) if STATE.exists() else {}
cmd = sys.argv[1:]
if cmd[:1] == ["start"] and len(cmd) == 2:
    st = {"method": cmd[1], "issued_at": now}
    STATE.write_text(json.dumps(st))
    print("ok")
elif cmd == ["remaining"]:
    print(max(0, st["issued_at"] + TTL - now))
elif cmd == ["method"]:
    print(st["method"])
else:
    print("사용법: bin/auth start <방식> | remaining | method")
    sys.exit(2)
EOF_BIN_AUTH
chmod +x 'bin/auth'
printf '.auth-state.json\n' > .gitignore
