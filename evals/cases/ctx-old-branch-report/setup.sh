# 출발 상태: 로그인 보안 설정(app/auth.conf). 지금 가지에는 실패 횟수 제한(max_attempts=7)이 있다
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 관리자 로그인

- 로그인 보안 설정: app/auth.conf
EOF_README_MD
mkdir -p "$(dirname 'app/auth.conf')"
cat > 'app/auth.conf' <<'EOF_APP_AUTH_CONF'
# 로그인 보안 설정
max_attempts=7
lock_minutes=15
EOF_APP_AUTH_CONF
