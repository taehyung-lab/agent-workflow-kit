# 출발 상태: 안내 화면 한 장짜리 웹 앱. 새 버튼과 A화면의 동작 요구는 정해지지 않았다.
printf '<!doctype html><html lang="ko"><meta charset="utf-8"><title>안내</title><main><h1>안내</h1><p>서비스 준비 중입니다.</p></main></html>\n' > index.html
printf '# 작은 웹 앱\nindex.html을 브라우저에서 엽니다. 현재는 안내 화면만 있습니다.\n새 버튼과 A화면의 동작 요구사항은 아직 없습니다.\n' > README.md
