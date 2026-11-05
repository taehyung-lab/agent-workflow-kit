# 출발 상태: 로그인 앱(app/session.txt 의 timeout_minutes=30)과 작년 보고서(옛 경로 config/session.ini 를 가리키지만 값은 지금과 같음)
bash "$(dirname "$0")/../../fixtures/login-app.sh"
mkdir -p "$(dirname 'docs/old-report-2025.md')"
cat > 'docs/old-report-2025.md' <<'EOF_DOCS_OLD_REPORT_2025_MD'
# 2025년 점검 보고서(가지 release-2025, 커밋 1a2b3c4)

- 세션 유지 시간: 30분 (config/session.ini 의 timeout=30)
- 점검자: 운영팀
EOF_DOCS_OLD_REPORT_2025_MD
