# 공동 제분소

파이썬 표준 라이브러리만 쓰는 명령줄 도구다. run의 제분 처리가 미완성이다.
mill.py는 명령과 저장 경계를, storage.py는 파일을, inventory.py는 통 조회·보충·차감을, milling.py는 작업과 잔고를 맡는다.

```
python3 mill.py stock
python3 mill.py accounts
python3 mill.py list
python3 mill.py show <작업번호>
python3 mill.py new <고객id> <곡물> <투입g>
python3 mill.py restock <통id> <보충g>
python3 mill.py run <작업번호>
python3 mill.py cancel <작업번호>
python3 -m unittest discover -s tests
```

자료는 data.json이다. MILL_DATA로 실험용 복사본 경로를 지정한다. 성공은 종료 코드 0과 JSON, 거절은 0 아닌 종료 코드와 JSON이다. 변경 뒤에도 공개 검사는 모두 통과해야 한다. docs/operations.md의 운영 약속을 따른다.
