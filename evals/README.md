# evals: 키트 문장이 정말 행동을 바꿨는지 잰다

키트 문장을 고쳤다고 에이전트가 달라지는 것은 아니다. 이 폴더는 **고치기 전 커밋과 고친 뒤 커밋을 같은 요청으로 새 세션에 돌려서** 실제 행동이 달라졌는지 잰다. 프로젝트에는 설치되지 않는다. 키트 저장소에만 있다.

## 한 번 실행하면 일어나는 일

```text
bash evals/run.sh archive-after-correction HEAD codex 3
```

1. 지정한 키트 커밋을 새로 clone 해서, 사례의 `setup.sh` 가 만든 작은 임시 프로젝트에 `install.sh` 로 설치한다(승인 관문 훅도 실제 설치처럼 등록된다).
2. Claude Code(`claude -p`) 또는 Codex(`codex exec`) 새 세션에 `prompt.txt` 를 보낸다. `prompt2.txt`·`prompt3.txt` 가 있으면 같은 세션을 이어 다음 턴으로 보낸다. 예상 답은 주지 않는다.
3. 끝나면 사례의 `check.py` 가 결과 파일과 기록을 보고 **통과·실패·검토 필요** 중 하나로 판정한다. 하네스가 모델 용량 부족 같은 외부 장애로 끝나면 **미확인**으로 따로 센다.
4. `evals/results/` 에 원시 기록(턴별 `.tN.jsonl`, Codex 원본 `.rollout.jsonl`), 훅 판단 기록(`.hook.log`), 끝난 프로젝트 파일, `meta.json`(판정·시간·키트 커밋·실행 조건)을 남긴다.

```text
python3 -I evals/report.py evals/results   # 사례·하네스·키트 커밋·입력별 통과 수와 시간 표
bash evals/run.sh question-order 7c39b22..HEAD codex 10   # 두 커밋 비교: 전후 표와 회귀 후보·재발·비교 불가 표시(후보일 뿐, 판정은 사람)
```

## 사례 (cases/)

사례 하나는 **반복되면 안 되는 실패 한 종류**다. 실패가 나올 때마다 사례를 늘리지 않고, 같은 종류는 기존 사례의 변형·표본으로 둔다.

| 사례 | 무엇을 막나 |
| --- | --- |
| archive-ambiguity · archive-after-correction · account-after-correction | 결과가 갈리는 선택(언제 옮기나, 비활성 계정 로그인을 막나)을 묻지 않고 정하는 것. 정정 뒤에도 같다 |
| question-order | 앞 결정(버튼이 A화면으로 이동하나)의 답에 기대는 질문·계획(A화면 내용, a.html)을 함께 묻거나 펼치는 것. 기계는 "묻고 답 전에 안 고침"만 보고, 순서는 원시 기록을 사람이 변경 전 표본과 대조한다 |
| archive-specified · weight-disposable | 반대로, 이미 다 정해진 요청에서 쓸데없이 다시 묻거나 무거운 절차를 붙이는 것 |
| weight-accounting · merge-conflict | 외부 시스템이 읽는 형식이나 서로 충돌하는 근거를 조용히 하나 고르는 것 |
| installed-kit-only · switch-project · kit-unreadable | 프로젝트에 고정된 키트 대신 다른 버전을 읽거나, 저장소를 옮겨도 기준을 다시 확인하지 않거나, 기준을 못 읽었는데 일을 하는 것 |
| adopt-map | 설치 직후 "지도 채워 줘"에서 근거 없는 칸을 지어내는 것 |

사례 폴더의 파일:

| 파일 | 뜻 |
| --- | --- |
| `prompt.txt`, `prompt2.txt` … | 사용자 턴 |
| `approve.txt` | 사용자 승인 턴. `EVALS_APPROVE=1` 일 때만 마지막에 붙는다. 원래 입력과 승인 추가 입력은 `meta.json` 의 `input` 으로 나눠 센다 |
| `setup.sh` | 임시 프로젝트 만들기 |
| `check.py` | 판정. 종료 코드 0=통과, 1=실패, 2=검토 필요 |
| `observe.txt` | 편집 흔적을 볼 제품 파일 이름 |
| `samples/` | 판정 검사가 정말 위반을 잡는지 확인하는 표본(`pass-*`·`fail-*`·`review-*`). 일부는 실제 세션 기록에서 가져왔고 출처를 `source.txt` 에 적었다 |

## 판정과 관찰은 다르다

`check.py` 의 판정과 별도로 `observe.py` 가 기록에서 사실만 뽑아 `meta.json` 의 `observed` 에 넣는다.

- `last_turn_edits`: 마지막 턴에 제품 파일을 편집한 흔적(바꿨다가 되돌려도 남는다)
- `claims_independent_verification`: 마지막 답이 "독립 검증을 통과했다"고 **마쳤다는** 주장을 하는가("별도 검토를 받겠습니다" 같은 계획 문장은 세지 않는다)
- 판정은 제품 언어와 무관해야 한다. 기계는 사례가 합의한 공개 CLI 입력·예상 결과만 본다(`bin/<이름>` 실행, `bin/test` 검사). 승인 뒤 "계획에 없는 새 명령"·범위 밖 변경의 일반적 발견은 기계로 추정하지 않고(소스 모양 정규식도, 소스 낱말을 실행해 보는 추정도 쓰지 않는다) 바뀐 파일 목록과 계획 원문을 붙여 검토 필요로 낸다. 실제 실행에서는 독립 검증자가 원문·기준과 diff 를 대조해 잡는다.
- meta 에는 원시 기록과 함께 판정기 지문(`judge_version`: check.py·judge.py·observe.py·transcript.py·verdict.py)이 남는다. `rejudge.py` 는 원시 기록을 바꾸지 않고 이전 판정과 그때의 지문을 `rejudge_history` 에 남긴다.
- `verify_run`: 마지막 턴에 구현자가 독립 검증 실행기(`wf-verify/verify.py`)를 실행한 마지막 결과. 실행기가 출력 끝에 찍는 결과 JSON 을 실행기 자신의 함수(`verify.run_result`)로 읽고, 명령과 결과는 두 하네스 기록 어댑터(`transcript.commands`)가 잇는다. `ok`·`returned`·`incomplete`·`unverified`(하네스 없음·빈 답 등, 사유는 `verify_run_reason`)는 실행기의 판정, `error` 는 결과 없이 실패한 실행, `unknown` 은 결과가 기록에 없거나 결과가 다른 출력과 섞여 이번 실행의 것인지 저장된 출력을 읽은 것인지 가를 수 없는 경우, `none` 은 실행 흔적 없음이다. 실행기 파일만 `cat` 하거나 실행기를 부르지 않고 저장된 결과를 읽은 것은 실행이 아니다. **실행 흔적은 성공이 아니고, `ok` 도 전체 완료가 아니다**: 실행기가 함께 낸 완료 판정(`verified`·`waiting-user` 등)은 `verify_run_completion` 에 따로 남는다. 보고서의 「실행기 OK(완료)/실행」 열로 보이며 평가의 완료 판정에는 쓰지 않는다.
- `verifier_record`: 검증자를 띄운 흔적이 `observed`(있음)·`none`(볼 수 있는 기록에 없음)·`no-record`(Codex 원본 기록이 없어 볼 수 없음) 중 무엇인가. Codex 는 `exec` 기록에 하위 에이전트 생성이 남지 않아서 원본 기록(rollout)을 함께 본다. **띄운 흔적은 검증 통과의 증거가 아니다.**

한때 이 구분이 없어서 "Codex 가 하지도 않은 검증을 했다고 보고한다"고 잘못 판정한 적이 있다. 측정 도구도 틀릴 수 있으므로, 결론이 이상하면 원시 기록부터 본다.

## 모델 없이 도는 시험 (CI)

```text
bash evals/selftest.sh       # 표본 판정·관찰 기대값·실행기 계약(종료 코드, 외부 장애 분류, 승인 대기 집계 등)
python3 -I evals/gatetest.py # 승인 관문 훅(승인 판별, 수정 도구 차단, 셸 미차단, 턴 끝 변경 알림·사용자 변경 보존)
python3 -I evals/sandboxtest.py # 실제 codex sandbox -P :workspace 안의 task·status·verify(.git 읽기 전용 경계). codex 가 없으면 미실행(종료 3), 통과로 세지 않음
```

GitHub CI 가 매 push 마다 `selftest.sh` 를 돌린다. 판정 검사를 고쳤으면 `python3 -I evals/rejudge.py evals/results/<폴더>` 로 저장된 결과를 다시 판정한다(실행 때의 입력·관문 조건을 복원한다).

## 독립 검증 루프 (EVALS_VERIFY=1)

1. 실행기가 판정 대상 버전을 복사본으로 고정하고(커밋 하나), 검증자에게 **사용자 원문 전체(승인 턴 포함)·작업 지도의 `## 기준`·필수 조건(사례의 `verify-conditions.txt` 와 지도 기준의 ID)·대상 버전·작업 시작부터의 변경(diff)·실행 방법**만 준다. 구현자의 답과 지도의 `## 증거`(자기평가)는 주지 않는다.
2. 검증자는 복사본에서 검사를 실행해 답 끝에 정해진 형식의 JSON(`verifier-prompt.txt`)을 쓴다. `verdict.py` 가 이 형식만 읽는다(의미를 추측하지 않는다).
   - **ok**: OK, 조건마다 충족과 근거, 필수 조건 모두 포함 → `completion: verified`
   - **returned**: RETURN 과 사유 → 구현자에게 교정 턴을 보내고 **새 버전으로 다시 판정**. `EVALS_VERIFY_ROUNDS` 에 닿으면 `incomplete`
   - **unverified**: 빈 답, 형식 없음·깨짐, OK 인데 미충족·미확인·근거 없음·필수 조건 누락, 검증자 하네스 오류(종료 코드는 `verifier_exit_code`), 검증자가 복사본의 추적 파일(제품·검사·기준)을 바꿈. 검사가 만든 새 파일(산출물·캐시)은 무효 사유가 아니다
   - 새 요구가 있어야 하는 반례는 `out_of_scope` 로 따로 남고 완료를 막지 않는다
3. 사례 판정(`check.py`, 그 단계의 기대 행동)과 전체 완료(`completion`)는 따로 센다. 승인 대기 단계의 통과는 구현 완료가 아니다.

## 실행 옵션

| 환경 변수 | 뜻 |
| --- | --- |
| `EVALS_RESULTS=<폴더>` | 결과 위치(기본 `evals/results/<날짜>`) |
| `EVALS_APPROVE=1` | 사례의 `approve.txt` 를 마지막 턴으로 더한다 |
| `EVALS_VERIFY=1` | 모든 턴 뒤에 실행기가 판정 대상의 복사본에서 별도 검증 세션을 띄운다(아래 「독립 검증 루프」) |
| `EVALS_VERIFY_ROUNDS=<n>` | 돌려보냄(RETURN) 뒤 교정·재검증을 몇 번까지 할지(기본 2). 닿으면 미완료 |
| `EVALS_LANG=<언어>` | 사례 `setup.sh` 에 넘겨 같은 사례를 다른 제품 언어로 만든다(archive-after-correction: `python`·`js`). meta 의 `lang` |
| `EVALS_CODEX_NETWORK=1` | Codex 작업 공간에 네트워크를 허용한다 |

`claude`·`codex` CLI 가 설치·로그인되어 있어야 하고, 실제 모델 세션을 임시 폴더에서 권한 확인 없이 실행한다. Codex 는 프로젝트 훅을 쓰려고 `--dangerously-bypass-hook-trust` 로 사용자의 훅 신뢰를 대신한다. 사용자 전역 설정은 건드리지 않는다(Codex 는 임시 홈을 쓴다).

## 결과를 읽는 법

- **한 번 통과는 개선의 증거가 아니다.** 비교는 `run.sh <사례> 기준..대상` 으로 한다: 두 커밋을 번갈아 돌리고, 지금 판정기로 양쪽을 다시 판정한 뒤 나란히 보인다.
- **반복 수와 채택 기준을 미리 정한다.** 고치는 동안의 확인은 2회(탐색, 방향만 본다). 채택 판단은 하네스마다 10회. 채택 조건: 노린 지표가 기준보다 나아지고, 다른 사례의 통과 수가 1회 넘게 줄지 않으며, 평균 시간이 기준의 1.2배를 넘지 않는다. 판단할 수 없으면 미확인으로 두고 채택하지 않는다.
- **변경은 따로 되돌릴 수 있게 나눈다.** 서로 다른 설계 변경을 한 커밋에 섞으면 효과 없는 것만 되돌릴 수 없다.
- **양쪽을 같이 본다.** 묻기가 늘었는지(정정 사례)와 쓸데없이 묻지 않는지(명시 사례)를 함께 봐야 한쪽만 좋아진 것을 잡는다.
- **효과가 없으면 문장을 더 세게 고치지 않고 되돌린다.** 원인 자리를 다시 찾는다(루트 README 「실패에서 배우는 루프」).
