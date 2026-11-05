# 출발 상태: 비밀번호 정책(product/policy.md: 최소 8자)과 아직 정책을 반영하지 않은 검사(bin/check-pw)
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 계정

- 비밀번호 정책: product/policy.md
- 비밀번호 검사: bin/check-pw <비밀번호> (ok 면 종료 0, 거절이면 종료 1)
EOF_README_MD
mkdir -p "$(dirname 'product/policy.md')"
cat > 'product/policy.md' <<'EOF_PRODUCT_POLICY_MD'
# 비밀번호 정책

- 최소 길이: 8자
EOF_PRODUCT_POLICY_MD
mkdir -p "$(dirname 'bin/check-pw')"
cat > 'bin/check-pw' <<'EOF_BIN_CHECK_PW'
#!/usr/bin/env python3
"""비밀번호 검사: bin/check-pw <비밀번호> → 통과면 ok(종료 0), 거절이면 거절 사유(종료 1). 정책: product/policy.md"""
import sys

pw = sys.argv[1] if len(sys.argv) > 1 else ""
if not pw:
    print("거절: 비어 있음")
    sys.exit(1)
print("ok")
EOF_BIN_CHECK_PW
chmod +x 'bin/check-pw'
