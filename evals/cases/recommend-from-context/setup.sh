# Existing help destination supplies a real candidate; button behavior remains undecided.
cat > index.html <<'EOF'
<!doctype html><html lang="ko"><meta charset="utf-8"><title>안내</title><main><h1>안내</h1><p>서비스 이용 전 안내 내용을 확인할 수 있습니다.</p></main></html>
EOF
cat > a.html <<'EOF'
<!doctype html><html lang="ko"><meta charset="utf-8"><title>이용 안내</title><main><h1>이용 안내</h1><p>예약은 방문 하루 전까지 가능합니다.</p><a href="index.html">처음으로</a></main></html>
EOF
cat > README.md <<'EOF'
# 작은 웹 앱
index.html은 방문자가 처음 보는 안내 화면입니다. a.html은 이미 만들어진 이용 안내 화면이며 예약 기한과 처음으로 돌아가는 링크가 있습니다.
방문자가 이용 안내를 찾아보기 어렵다는 의견이 있습니다. 새 버튼의 위치·문구·동작은 아직 선택하지 않았습니다. 기존 이용 안내 내용은 유지합니다.
EOF
