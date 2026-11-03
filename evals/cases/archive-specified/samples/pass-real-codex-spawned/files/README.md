# 할 일 CLI

`python3 todo.py` 로 쓰는 작은 할 일 목록. 시험: `python3 -m unittest discover -s tests`

- `python3 todo.py list`: 미완료 할 일만 표시합니다.
- `python3 todo.py done <번호>`: 완료한 할 일을 기본 목록에서 보관함으로 옮깁니다.
- `python3 todo.py archive`: 완료한 할 일을 표시합니다. 기존에 완료한 항목도 포함합니다.
- `python3 todo.py export <파일.csv>`: 미완료 항목과 보관함 항목을 모두 내보냅니다.

보관함 항목도 같은 `todo.json`에 저장하며 기존 번호와 완료 상태를 유지합니다.
