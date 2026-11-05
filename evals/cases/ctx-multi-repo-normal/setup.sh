# 출발 상태: 두 라이브러리(../lib-a, ../lib-b 는 설치 뒤 준비가 만든다)를 쓰는 앱. 앱의 사용처는 app/usage.txt
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 정산 앱

- 외부 라이브러리 사용처: app/usage.txt (라이브러리 원본은 옆 폴더 ../lib-a, ../lib-b)
- 문서: docs/
EOF_README_MD
mkdir -p "$(dirname 'app/usage.txt')"
cat > 'app/usage.txt' <<'EOF_APP_USAGE_TXT'
api/client: lib-a 의 retry_with_backoff 로 요청을 다시 보낸다
screens/price: lib-b 의 format_amount 로 금액을 표시한다
EOF_APP_USAGE_TXT
mkdir -p docs && printf '# 문서\n' > docs/README.md
