# 표본 라벨 시트

박물관 작업실에서 쓰는 파이썬 표준 라이브러리 전용 명령줄 도구다. 인쇄기는 JSON을 받아 라벨을 출력한다. 현재 seal은 미완성이다.

모듈은 labels.py(명령), storage.py(저장), catalog.py(표본 조회), sheets.py(시트 편집·출력)다.

```
python3 labels.py catalog
python3 labels.py specimen <코드>
python3 labels.py rename <코드> <새이름>
python3 labels.py list
python3 labels.py show <시트번호>
python3 labels.py new
python3 labels.py add <시트번호> <코드> <수량>
python3 labels.py remove <시트번호> <코드> <수량>
python3 labels.py seal <시트번호>
python3 -m unittest discover -s tests
```

변경 뒤에도 위 공개 검사는 모두 통과해야 한다.

자료는 data.json이며 실험할 때는 LABELS_DATA로 복사본 경로를 지정한다. 성공은 종료 코드 0과 JSON, 거절은 0이 아닌 종료 코드다. 운영 약속은 docs/operations.md에 있다.
