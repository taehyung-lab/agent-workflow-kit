# 옛 가지 두 개(old-a, feat/old-b)에는 max_attempts 가 없다. 붙여 넣은 분석은 이 두 가지를 비교한 것이다.
set -e
cur=$(git symbolic-ref --short HEAD)
for b in old-a feat/old-b; do
  git checkout -q -b "$b"
  mkdir -p "$(dirname 'app/auth.conf')"
cat > 'app/auth.conf' <<'EOF_APP_AUTH_CONF'
# 로그인 보안 설정
lock_minutes=15
EOF_APP_AUTH_CONF
  git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm "옛 설정($b)"
  git checkout -q "$cur"
done
