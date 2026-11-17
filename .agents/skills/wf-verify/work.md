# 작업 도구

설치된 `wf-verify/work.py`를 사용한다. 중앙 키트로 작업하면 중앙의 이 파일을 사용하되 작업 폴더는 대상 저장소나 홈에 둔다. 다음 명령의 W는 대표 작업 폴더다.

```text
python3 .agents/skills/wf-verify/work.py record W --request request.txt --plan plan.json
python3 .agents/skills/wf-verify/work.py record W --request answer.txt --plan revised-plan.json
python3 .agents/skills/wf-verify/work.py check W
python3 .agents/skills/wf-verify/work.py review W
python3 .agents/skills/wf-verify/work.py review W --answer review-answer.txt
```

`record`는 원문만 추가하거나 계획만 교체할 수도 있다. source는 이 작업에 추가한 원문 번호(1부터), base는 작업 시작 시 실제 커밋이다. state는 확정·미정·미확인이다. 이전 결정을 바꾸는 계획은 새 답의 번호를 가리킨다. 검사 명령은 프로젝트가 정한 명령과 요구에서 고르며 도구가 추측하지 않는다.

```json
{
  "targets": [{"name": "app", "path": "/actual/project", "base": "실제 시작 커밋"}],
  "requirements": [{"id": "R1", "expect": "입력 → 관찰 장소 → 기대 결과", "source": [1], "state": "확정"}],
  "checks": [{"id": "C1", "target": "app", "requirements": ["R1"], "argv": ["python3", "tests/test_app.py"], "timeout": 300}]
}
```

`check`는 대상별 명령을 실행하고 출력·종료 코드·코드 상태를 보존한다. 미정이면 실행하지 않고 대기한다. 누락된 요구의 검사, 장애, 시간 초과, 검사 중 제품 변경은 미확인이다. 기본은 검사 성공 뒤 검토를 기다린다. 필수 독립 검토 조건에 해당하지 않는 작업은 계획에 review_required: false를 명시할 수 있다. 이 선택의 타당성과 최종 원문 대조는 에이전트가 책임진다.

`review`는 구조화한 현재 요구·대상을 기존 검토 핵심에 직접 넘긴다. 생성된 work.md는 읽기용이며 판정 입력이 아니다.

`review`가 낸 prompt_file을 별도 검토자에게 그대로 넘기고 받은 답을 수정 없이 --answer로 준다. 원문·계획·대상·검사 출력이 바뀌면 이전 증거는 완료에 쓰지 않는다. 실패는 원인을 고치고 check부터, 반환은 prepare를 다시 만드는 review부터 진행한다. 검토 한도는 기존 verify.py가 관리한다.

여러 대상의 내부 구현·검사는 해당 저장소의 고정 기준을 따른다. 전체 검토는 요청을 잇는 요구를 확인한다. 이 도구는 파일 소유자의 조작을 막는 보안 장치가 아니며 원문 누락·숨은 미정·검사의 타당성은 독립 검토가 확인한다.

기존 지도의 검토에는 verify.py record/prepare/finish가 남아 있다. 새 대표 기록의 완료에는 수동 --check PASS를 쓰지 않고 이 도구의 실제 실행 증거를 사용한다.
