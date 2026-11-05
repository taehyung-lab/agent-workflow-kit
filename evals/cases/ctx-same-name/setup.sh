# 출발 상태: 사내 관리자 v2. 로그인 입력 칸 정의는 app/login.conf
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 사내 관리자 v2

- 로그인 화면 입력 칸: app/login.conf
EOF_README_MD
mkdir -p "$(dirname 'app/login.conf')"
cat > 'app/login.conf' <<'EOF_APP_LOGIN_CONF'
# 로그인 입력 칸(v2)
id_field=employee_no
id_label=사번
id_rule=6자리 숫자
EOF_APP_LOGIN_CONF
