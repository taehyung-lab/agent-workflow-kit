# 출발 상태: 회원 결정(product/decisions.md: 재가입은 90일 뒤)
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 회원 관리

- 결정: product/decisions.md
- 답변 문서: docs/
EOF_README_MD
mkdir -p "$(dirname 'product/decisions.md')"
cat > 'product/decisions.md' <<'EOF_PRODUCT_DECISIONS_MD'
# 회원 결정

- 탈퇴 회원 재가입: 탈퇴일로부터 90일이 지나야 가능하다(2026-10-20 사용자 결정).
- 탈퇴 회원 데이터: 재가입 때 복구하지 않는다.
EOF_PRODUCT_DECISIONS_MD
mkdir -p docs && printf '# 답변\n' > docs/README.md
