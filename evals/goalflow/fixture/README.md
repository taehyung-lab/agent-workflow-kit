# 회차 신청 앱 (평가용)

요청 원문: request.txt. 운영 조건·계약: docs/environment.md.

- 실행: `python3 app.py submit --db /tmp/enrollment-demo.db --request req-1 --member alice --workshop morning`
- 결과 조회: `python3 app.py recover --db /tmp/enrollment-demo.db --request req-1 --member alice`
- 공개 검사: `python3 -m unittest discover -s tests -v`
- 공개 조사: `python3 bin/probe.py` (임시 DB에서 현재의 동시 신청·재시도 결과를 관찰)

서비스 진입은 service.py, 참가자에게 보여 주는 결과는 client.py, CLI는 app.py다. service.confirm/status와 client.submit/recover의 호출 인자·JSON 반환 형태를 유지한다. 서비스와 클라이언트 구현, 저장 구조, 새 검사 추가는 가능하다. 기존 공개 검사와 bin/probe.py, 요청·환경 문서는 수정하지 않는다. 실제 배포나 사람의 현장 인계 효과까지 측정한 앱은 아니다.
