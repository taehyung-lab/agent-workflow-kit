# 작업 도구

설치된 `wf-verify/work.py`를 사용한다. 중앙 키트로 작업하면 중앙의 이 파일을 사용하되 작업 폴더는 대상 저장소나 홈에 둔다. 다음 명령의 W는 현재 검사·검토할 작업의 대표 폴더다. 전체 로드맵의 후속 작업은 이 계획의 미확정 요구와 구별하고 같은 원문 출처를 이어 쓴다. 이 폴더의 완료는 해당 요구의 완료이며, 전체 목표의 남은 작업은 별도로 대조한다.

```text
python3 .agents/skills/wf-verify/work.py record W --request request.txt --plan plan.json
python3 .agents/skills/wf-verify/work.py record W --findings reader.json
python3 .agents/skills/wf-verify/work.py record W --request answer.txt --plan revised-plan.json
python3 .agents/skills/wf-verify/work.py record W --evidence before-failure.txt --evidence observed-result.txt
python3 .agents/skills/wf-verify/work.py check W
python3 .agents/skills/wf-verify/work.py review W
python3 .agents/skills/wf-verify/work.py review W --answer review-answer.txt
```

`record`는 원문만 추가하거나 계획만 교체할 수도 있다. source는 이 작업에 추가한 원문 번호(1부터), base는 작업 시작 시 실제 커밋이다. state는 확정·미정·미확인이다. 독자가 반환한 상황 배열은 --findings로 추가한다. 확정 항목은 `wf-ask/situations.py`와 같은 확인으로 인용 출처가 원문·합의 문서에 있을 때만 확정으로 남고, 아니면 미정으로 기록된다(결과의 demoted). 새 질문 ID는 현재 요구와 겹치지 않아야 한다. 빈 배열이면 추가할 것이 없다. 기록된 미정 요구는 다음 계획에서 삭제할 수 없고, 확정하려면 그 선택이 생긴 뒤 받은 새 사용자 원문을 출처로 가리켜야 한다. 같은 원문을 다시 넣어 번호만 늘리는 것으로 해소할 수 없다. 실제 새 답이 이전 답과 같은 문장이라면 --reply-to Q1처럼 그 답이 해소하는 현재 질문을 지정한다. 답의 실제 의미는 원문 대조와 독립 검토가 확인한다. 범위를 철회한 답도 해당 요구의 기대 결과에 범위 제외로 남긴다. 검사 명령은 프로젝트가 정한 명령과 요구에서 고르며 도구가 추측하지 않는다.

```json
{
  "targets": [{"name": "app", "path": "/actual/project", "base": "실제 시작 커밋"}],
  "requirements": [{"id": "R1", "expect": "입력 → 관찰 장소 → 기대 결과", "source": [1], "state": "확정"}],
  "checks": [{"id": "C1", "target": "app", "requirements": ["R1"], "argv": ["python3", "tests/test_app.py"], "timeout": 300}]
}
```

`check`는 대상별 명령을 실행하고 출력·종료 코드·코드 상태를 보존한다. 미정이면 실행하지 않고 대기한다. 누락된 요구의 검사, 장애, 시간 초과, 검사 중 제품 변경은 미확인이다. 기본은 검사 성공 뒤 검토를 기다린다. 필수 독립 검토 조건에 해당하지 않는 작업은 계획에 review_required: false를 명시할 수 있다. 이 선택의 타당성과 최종 원문 대조는 에이전트가 책임진다.

`review`는 현재 요구·대상·최신 검사와 함께 이전 요구·검사 명령·실패 출력을 기존 검토 핵심에 넘긴다. 과거 실행은 이력이며 현재 PASS를 대신하지 않는다. 별도 재현·관찰 로그는 `record --evidence`로 원문과 구분해 바이트 그대로 보존한다. 증거 추가도 검토 맥락을 바꾸므로 최종 check 전에 기록한다. 생성된 work.md는 읽기용이며 판정 입력이 아니다.

`review`가 낸 prompt_file을 별도 검토자에게 그대로 넘기고 받은 답을 수정 없이 --answer로 준다. 큰 변경은 전체 diff를 읽기 전용 근거 파일로 전달하므로 검토자는 안내된 파일을 끝까지 읽는다. 원문·계획·대상·현재/과거 검사 출력·보존한 추가 증거·전체 변경 근거가 바뀌거나 없어지면 이전 증거는 완료에 쓰지 않는다. 실패는 원인을 고치고 check부터, 반환은 prepare를 다시 만드는 review부터 진행한다. 검토 한도는 기존 verify.py가 관리한다.

대상 수와 기록 형식에 관계없이 내부 구현·검토는 해당 저장소의 적용 기준을 따른다. review는 대상마다 내부 검토 조건을 붙인다. 검토자는 대상의 고정 기준으로 직접 검토하고, 별도 역할·절차가 필수면 그 결과도 확인한다. 기존 검토는 원문·대상 버전·검사와 현재성을 확인할 수 있을 때만 재사용한다. 누락·실패·미확인인 대상 조건을 빼고 전체 완료로 판정할 수 없다. 여러 대상이면 저장소를 잇는 요구도 별도로 대조한다. 이 도구는 파일 소유자의 조작을 막는 보안 장치가 아니며 원문 누락·숨은 미정·검사의 타당성은 독립 검토가 확인한다.

기존 지도의 검토에는 verify.py record/prepare/finish가 남아 있다. 새 대표 기록의 완료에는 수동 --check PASS를 쓰지 않고 이 도구의 실제 실행 증거를 사용한다.

## 이미 정해진 계약을 뒤늦게 찾은 경우

잘못 미정으로 분류한 결과는 사용자에게 다시 묻는 대신 기존 독립 검토로 정정한다. 현재 미정은 도구가 만든 resolution-context.md에 있다. 제안 계획에는 해당 계약이 정한 기대값을 적는다.

```text
python3 .agents/skills/wf-verify/verify.py prepare --request W/sources/0001.txt --output revised-plan.json --conditions W/resolution-context.md
python3 .agents/skills/wf-verify/verify.py finish --round KEPT --check PASS < independent-answer.txt
python3 .agents/skills/wf-verify/work.py record W --plan revised-plan.json --resolution-review KEPT
```

새 사용자 원문이 있다면 먼저 record로 보존한다. 현재 원문을 모두 --request로 전달하고, prepare가 만든 prompt_file을 부모 맥락 없는 독립 검토자에게 그대로 넘긴다. 검토자는 제안 계획의 결과가 이미 원문·계약으로 정해졌는지 해당 문장을 인용해 판단한다. 미정이 남으면 사용자에게 묻는다. 도구는 통과한 회차가 현재 원문·현재 미정·같은 제안 계획을 실제로 대조했는지 확인하고, 바뀐 근거의 옛 통과는 사용하지 않는다.
