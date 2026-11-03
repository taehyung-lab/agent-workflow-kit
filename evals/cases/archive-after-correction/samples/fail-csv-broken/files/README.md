# 할 일 CLI

`python3 todo.py` 로 쓰는 작은 할 일 목록. 시험: `python3 -m unittest discover -s tests`

- `python3 todo.py list`: 미완료 할 일을 보여 줍니다.
- `python3 todo.py done <번호>`: 완료한 할 일을 보관함으로 옮깁니다.
- `python3 todo.py archive`: 보관함의 완료한 할 일을 보여 줍니다.
- `python3 todo.py export <파일.csv>`: 보관함을 포함한 모든 할 일을 내보냅니다.

보관함으로 옮겨도 할 일의 번호와 저장 기록은 유지됩니다.
