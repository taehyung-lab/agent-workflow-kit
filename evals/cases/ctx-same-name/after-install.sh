# 같은 저장소의 다른 worktree 를 옆 폴더 이름 "v2" 로 둔다(가지는 v2-old, 로그인은 이메일). 지금 작업 폴더의 가지 이름은 v2 다.
# 세션은 지금 폴더(v2 가지, 사번)를 분석해야 한다. 이름이 같은 옆 폴더를 현재 대상으로 삼으면 실패.
set -e
git branch -m v2
git worktree add -q -b v2-old ../v2
cd ../v2
mkdir -p "$(dirname 'app/login.conf')"
cat > 'app/login.conf' <<'EOF_APP_LOGIN_CONF'
# 로그인 입력 칸(v2 이전 안)
id_field=email
id_label=이메일
id_rule=이메일 형식
EOF_APP_LOGIN_CONF
git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm "로그인을 이메일로(이전 안)"
