# 출발 상태: 도서 대출 CLI(evals/fixtures/loan_app.py). 운영 문서의 합의(기한 14일, 키 due)와 그 테스트가 통과하는 상태
python3 -I "$(dirname "$0")/../../fixtures/loan_app.py" write base .
