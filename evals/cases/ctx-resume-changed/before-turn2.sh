# 재개 전에 다른 사람(보안팀)이 정책 파일을 바꿔 커밋한다. 세션은 다시 이어 갈 때 바뀐 근거를 확인해야 한다.
set -e
mkdir -p "$(dirname 'product/policy.md')"
cat > 'product/policy.md' <<'EOF_PRODUCT_POLICY_MD'
# 비밀번호 정책

- 최소 길이: 12자
- 특수문자(영문·숫자·공백이 아닌 문자) 1개 이상
EOF_PRODUCT_POLICY_MD
git add product/policy.md && git -c user.name=보안팀 -c user.email=sec@invalid commit -qm '보안팀: 비밀번호 정책 강화(최소 12자, 특수문자 1개)'
