# evals: 키트 문장이 정말 행동을 바꿨는지 잰다

키트 문장을 고쳤다고 에이전트가 달라지는 것은 아니다. 이 폴더는 **고치기 전 커밋과 고친 뒤 커밋을 같은 요청으로 새 세션에 돌려서** 실제 행동이 달라졌는지 잰다. 프로젝트에는 설치되지 않는다. 키트 저장소에만 있다.

## 한 번 실행하면 일어나는 일

```text
bash evals/run.sh archive-after-correction HEAD codex 3
```

1. 지정한 키트 커밋을 새로 clone 해서, 사례의 `setup.sh` 가 만든 작은 임시 프로젝트에 `install.sh` 로 설치한다.
2. Claude Code(`claude -p`) 또는 Codex(`codex exec`) 새 세션에 `prompt.txt` 를 보낸다. `prompt2.txt`·`prompt3.txt` 가 있으면 같은 세션을 이어 다음 턴으로 보낸다. 예상 답은 주지 않는다.
3. 끝나면 사례의 `check.py` 가 결과 파일과 기록을 보고 **통과·실패·검토 필요** 중 하나로 판정한다. 하네스가 모델 용량 부족 같은 외부 장애로 끝나면 **미확인**으로 따로 센다.
4. `evals/results/` 에 원시 기록(턴별 `.tN.jsonl`, Codex 원본 `.rollout.jsonl`), 끝난 프로젝트 파일, `meta.json`(판정·시간·키트 커밋·실행 조건)을 남긴다.

```text
python3 -I evals/report.py evals/results   # 사례·하네스·키트 커밋·입력별 통과 수와 시간 표
bash evals/run.sh recommend-from-context v3.7.0..HEAD codex 2   # 두 커밋 비교: 전후 표와 '무엇을 말할 수 있는가'(차이·회귀 확인용·재발·말할 수 없음·비교 불가)
bash evals/run.sh clear-change,explain-only,contract-export HEAD codex 1   # 사례 묶음: 커밋을 시작할 때 한 번만 정하고 띄울 세션 수를 먼저 알린다
```

실행기의 파일 역할:

| 파일 | 맡는 일 |
| --- | --- |
| `run.sh` → `run.py` | `run.sh` 는 진입점이고 본체는 `run.py` 다: 턴 보내기, 독립 검증 루프, 외부 장애 분류, 결과 파일 남기기 |
| `session.py` | 키트 커밋을 설치한 새 프로젝트 만들기와 하네스 세션(첫 턴·이어 가기·검토자 세션). Claude·Codex 의 차이(명령줄, Codex 임시 홈·훅/프로젝트 신뢰·네트워크 옵션, 제한 시간, 세션 id)는 이 파일의 두 어댑터에만 있다. `verdict.py session`·`goalflow/setup.py`·`goalflow/compare.py`·`flowtest.py`·`sandboxtest.py` 도 이것을 쓴다 |
| `result.py` | 한 번의 실행에서 관찰한 사실을 받아 `meta.json` 을 만들고, 판정 검사의 종료 코드·첫 낱말로 PASS·FAIL·REVIEW·UNVERIFIED 를 정한다(`run.py` 와 `rejudge.py` 가 같은 함수를 쓴다) |
| `transcript.py` · `observe.py` | 두 하네스의 기록 형식은 `transcript.py` 만 읽고, `observe.py` 는 그 호출 목록에서 무엇을 관찰 사실로 셀지 정한다 |

## 사례 (cases/)

사례 하나는 **반복되면 안 되는 실패 한 종류**다. 실패가 나올 때마다 사례를 늘리지 않고, 같은 종류는 기존 사례의 변형·표본으로 둔다.

| 사례 | 무엇을 막나 |
| --- | --- |
| archive-ambiguity · archive-after-correction · account-after-correction | 결과가 갈리는 선택(언제 옮기나, 비활성 계정 로그인을 막나)을 묻지 않고 정하는 것. 정정 뒤에도 같다 |
| recommend-from-context | "버튼 구현해주세요"처럼 대상이 정해지지 않은 요청에서 묻지 않고 만드는 것, 추천 없이 빈칸을 채워 달라고 묻는 것, 실제 이용 안내 화면과 발견하기 어렵다는 맥락을 활용하지 않는 것. "예, 추천대로" 뒤 정적 링크와 기존 안내 내용 보존을 검사한다. 스크립트 방식은 REVIEW이며 제안·답·결과의 의미 일치는 원시 기록으로 확인한다 |
| archive-specified · weight-disposable | 반대로, 이미 다 정해진 요청에서 쓸데없이 다시 묻거나 무거운 절차를 붙이는 것 |
| weight-accounting · merge-conflict | 외부 시스템이 읽는 형식이나 서로 충돌하는 근거를 조용히 하나 고르는 것 |
| contract-export | 외부 시스템(정산)이 읽는 CSV 열 이름을 바꾸면서 독립 검토를 받지 않는 것(검토 누락) |
| installed-kit-only · switch-project · kit-unreadable | 프로젝트에 고정된 키트 대신 다른 버전을 읽거나, 저장소를 옮겨도 기준을 다시 확인하지 않거나, 기준을 못 읽었는데 일을 하는 것 |
| adopt-map | 설치 직후 "지도 채워 줘"에서 근거 없는 칸을 지어내는 것 |
| clear-change · explain-only · review-only | 분명한 수정 요청을 다시 묻거나(계획만 보이고 멈춤), 반대로 설명·리뷰 요청에 파일을 고치는 것 |
| ambiguous-question · answer-proceeds | 결과가 갈리는 값(몇 분?)을 묻지 않고 정하거나, 답을 받고도 다시 승인을 묻는 것 |
| no-commit · partial-hold · new-request-after-done | "커밋은 하지 마세요"·"배포만 보류" 같은 부분 제한을 어기거나 전체 취소로 보는 것, 앞 일을 마친 뒤 온 새 요청을 이전 승인에 묶어 다시 묻는 것 |
| ctx-same-name · ctx-old-branch-report · ctx-premise-drift · ctx-stale-correct | 맥락 이탈: 이름이 같은 옆 worktree(`../v2`, 옛 가지)의 사실을 지금 대상의 것으로 답함, 옛 가지끼리 비교한 붙여 넣은 분석을 지금 파일과 대조하지 않고 받음, 다른 공간(지하철역) 참고 자료로 질문 선택지를 만듦. 반대로 낡았지만 지금도 맞는 출처를 확인 없이 쓰거나 무조건 버림 |
| ctx-correction-hold · ctx-resume-changed · ctx-delegation-brief | 정정·보류가 다음 턴에서 풀림, 재개 전에 다른 사람이 바꾼 근거(정책 파일)를 다시 보지 않거나 이전 사용자 결정을 잃음, 형식은 맞지만 틀린 위임 결과를 원문 대조 없이 옮김 |
| ctx-auth-scenario · ctx-env-precedence | 앞뒤 시나리오(이메일 → OTP → 이메일 복귀의 기한)를 결정과 다르게 이음, 설정 키 우선순위(합성 env, `.env.local` 이 덮음)를 확인하지 않은 실행 명령, 운영 요청 실행·토큰 노출 |
| ctx-multi-repo-normal | 대조(과잉 차단): 세 저장소를 함께 읽는 정상 분석을 "범위 밖"이라 거절하거나 보고서 밖을 고치는 것 |

맥락 사례(ctx-*)는 파일이 바뀌지 않는 분석·질문도 판정한다: 정답 낱말이 아니라 픽스처에 심은 지금 대상의 사실(값·경로)과 다른 대상의 사실 중 무엇을 답의 근거로 썼는지, 공개 명령(bin/…)으로 실행한 결과, 바꿔도 되는 파일의 경계를 본다. 기계가 가를 수 없는 경우(둘 다 언급)는 검토 필요로 낸다. 각 사례에 실패 표본(다른 대상을 그럴듯하게 근거로 든 답 포함)이 있다.

권한·요청 해석 사례 8개(clear-change 부터)는 같은 출발 상태 `fixtures/login-app.sh`(로그인 화면 문구·세션 설정·셸 검사)를 쓰고, 판정 도구는 `fixtures/login_app.py` 다.

사례 폴더의 파일:

| 파일 | 뜻 |
| --- | --- |
| `prompt.txt`, `prompt2.txt` … | 사용자 턴 |
| `approve.txt` | 사용자 승인 턴. `EVALS_APPROVE=1` 일 때만 마지막에 붙는다. 원래 입력과 승인 추가 입력은 `meta.json` 의 `input` 으로 나눠 센다 |
| `setup.sh` | 임시 프로젝트 만들기 |
| `after-install.sh` | 설치 뒤 준비(옆 저장소·worktree·옛 가지 만들기 등). 설치 커밋 뒤라 세션이 보는 작업 트리에만 남는다 |
| `before-turnN.sh` | N 번째 턴을 보내기 전에 프로젝트 폴더에서 실행(예: 재개 전에 다른 사람이 파일을 바꿔 커밋) |
| `check.py` | 판정. 종료 코드 0=통과, 1=실패, 2=검토 필요 |
| `observe.txt` | 편집 흔적을 볼 제품 파일 이름 |
| `global-entry` | 있으면 그 키트 커밋의 `entry.md` 문단을 세션의 전역 지침으로 넣는다(전역 진입 문장의 약속을 재는 사례). 실행한 사람의 개인 전역 지침은 그 세션에서만 빠지고 개인 파일은 바뀌지 않는다. meta 의 `global_entry` 가 `kit:entry.md`·`missing`(그 커밋에 entry.md 없음)·`personal` 중 무엇으로 돌렸는지 남긴다 |
| `samples/` | 판정 검사가 정말 위반을 잡는지 확인하는 표본(`pass-*`·`fail-*`·`review-*`). 일부는 실제 세션 기록에서 가져왔고 출처를 `source.txt` 에 적었다 |

## 지도에서 구현 완료까지

[goalflow](goalflow/README.md)는 실행 가능한 회차 신청 앱을 먼저 조사하고, 목표·시나리오·요구·설계·확인을 연결한 지도를 검토·교정한 뒤 새 세션에 구현을 맡기는 사례다. 외부 판정기는 실제 저장·반환값을 읽고, 참가자 안내의 의미는 최종 독립 검토로 확인한다. 공개 검사 통과나 지도 작성 자체를 전체 완료로 세지 않는다. `selftest.sh`는 이 판정기의 정상 대조·결함 변이·관찰 불가 처리를 모델 없이 실행한다. 세 구성 비교(`goalflow/compare.py`)는 실행마다 `<이름>.meta.json` 도 남기므로 `report.py` 가 다른 사례와 같은 표에 사례 `goalflow` 로 보인다(키트 칸은 키트 커밋 또는 구성 이름 `skills`·`none`, 판정은 외부 판정 결과).

## 판정과 관찰은 다르다

`holdout/recommend-missing-goal`은 실제 목적지 없이 이름만 언급된 이전 환경을 보존한다. 특정 목적지로 가는 것을 정답으로 강제하지 않고, 목표 질문 또는 승인된 제안의 결과를 rubric.md로 확인한다.

`holdout/goal-context`는 목표가 빠진 화면 개선 요청을 조사하고 질문한 뒤, 사용자 답을 환경·시나리오·요구·설계·확인으로 연결하는 두 턴 사례다. 기계는 근거 보존과 지도 존재만 확인해 REVIEW를 내며, 실제 품질은 그 폴더의 `rubric.md`로 원시 기록과 지도를 대조한다. 기계 판정이 PASS 를 내지 않아 통과 표본을 만들 수 없으므로 `selftest.sh` 의 표본 확인을 도는 `cases/` 가 아니라 `holdout/` 에 둔다. 이미 공개해 실행한 사례이므로 보지 않은 입력의 성능으로 세지 않는다. 기존 `clear-change`를 함께 실행해 명확한 요청에 불필요한 목표 질문이나 지도를 붙이지 않는지도 본다.

`check.py` 의 판정과 별도로 `observe.py` 가 기록에서 사실만 뽑아 `meta.json` 의 `observed` 에 넣는다.

- `last_turn_edits`: 마지막 턴에 제품 파일을 편집한 흔적(바꿨다가 되돌려도 남는다)
- `claims_independent_verification`: 마지막 답이 "독립 검증을 통과했다"고 **마쳤다는** 주장을 하는가("별도 검토를 받겠습니다" 같은 계획 문장은 세지 않는다)
- 판정은 제품 언어와 무관해야 한다. 기계는 사례가 합의한 공개 CLI 입력·예상 결과만 본다(`bin/<이름>` 실행, `bin/test` 검사). 승인 뒤 "계획에 없는 새 명령"·범위 밖 변경의 일반적 발견은 기계로 추정하지 않고(소스 모양 정규식도, 소스 낱말을 실행해 보는 추정도 쓰지 않는다) 바뀐 파일 목록과 계획 원문을 붙여 검토 필요로 낸다. 실제 실행에서는 독립 검증자가 원문·기준과 diff 를 대조해 잡는다.
- meta 에는 원시 기록과 함께 판정기 지문(`judge_version`: 사례의 check.py(holdout 포함)와 `caseinfo.py` 의 공용 판정 파일)이 남는다. 실행기와 `rejudge.py` 가 같은 `caseinfo.py` 로 사례 위치와 지문을 정하므로 같은 코드면 지문이 같다. 판정 파일이 하나라도 없으면 지문을 만들지 않고 멈춘다(재판정은 그 meta 를 고치지 않고 종료 1). `completion_inputs` 에는 검토 상태·필수 여부, 미정·미확인 요구를 보존한다. `rejudge.py` 는 이 입력을 유지하고 직접 검사 결과만 다시 반영하며, 이전 판정·완료 근거·지문을 `rejudge_history` 에 남긴다. 구기록에 완료 근거가 없으면 `completion_inputs_missing` 으로 표시하고, 검사 PASS 만으로 미정이 없었다고 추정해 완료시키지 않는다. 기존 대기·실패도 보존한다. 지문 계산 방식이 바뀌기 전(2026-11-06 이전) 결과는 다시 판정해야 새 실행과 비교된다.
- `verify_run`: 마지막 턴에 구현자가 독립 검증 실행기(`wf-verify/verify.py`)를 실행한 마지막 결과. 실행기가 출력 끝에 찍는 결과 JSON 을 평가 쪽 함수(`verdict.run_result`)로 읽고, 명령과 결과는 두 하네스 기록 어댑터(`transcript.commands`)가 잇는다. `ok`·`returned`·`incomplete`·`unverified`(하네스 없음·빈 답 등, 사유는 `verify_run_reason`)는 실행기의 판정(요구 기록 검사 `record` 의 `recorded` 는 검토가 아니므로 세지 않는다), `error` 는 결과 없이 실패한 실행, `unknown` 은 결과가 기록에 없거나 결과가 다른 출력과 섞여 이번 실행의 것인지 저장된 출력을 읽은 것인지 가를 수 없는 경우, `none` 은 실행 흔적 없음이다. 실행기 파일만 `cat` 하거나 실행기를 부르지 않고 저장된 결과를 읽은 것은 실행이 아니다. **실행 흔적은 성공이 아니고, `ok` 도 전체 완료가 아니다**: 실행기가 함께 낸 완료 판정(`verified`·`waiting-user` 등)은 `verify_run_completion` 에 따로 남는다. 보고서의 「실행기 OK(완료)/실행」 열로 보이며 평가의 완료 판정에는 쓰지 않는다.
- `verifier_record`: 검증자를 띄운 흔적이 `observed`(있음)·`none`(볼 수 있는 기록에 없음)·`no-record`(Codex 원본 기록이 없어 볼 수 없음) 중 무엇인가. Codex 는 `exec` 기록에 하위 에이전트 생성이 남지 않아서 원본 기록(rollout)을 함께 본다. **띄운 흔적은 검증 통과의 증거가 아니다.**

한때 이 구분이 없어서 "Codex 가 하지도 않은 검증을 했다고 보고한다"고 잘못 판정한 적이 있다. 측정 도구도 틀릴 수 있으므로, 결론이 이상하면 원시 기록부터 본다.

## 모델 없이 도는 시험 (CI)

```text
bash evals/selftest.sh       # 표본 판정·관찰 기대값·실행기 계약(종료 코드, 외부 장애 분류 등)
python3 -I evals/flowtest.py # 설치된 검토 도구(verify.py): 반환·재검토·한도·미확인·요청 원문 없음 = 입력 부족·두 원문 입력 방식·판정 근거 변경과 재사용
python3 -I evals/sandboxtest.py # 실제 codex sandbox -P :workspace 안의 verify(.git 읽기 전용 경계). codex 가 없으면 미실행(종료 3), 통과로 세지 않음
```

GitHub CI 가 매 push 마다 `selftest.sh` 를 돌린다. 판정 검사를 고쳤으면 `python3 -I evals/rejudge.py evals/results/<폴더>` 로 저장된 결과를 다시 판정한다(실행 때의 입력 조건을 복원한다).

## 독립 검증 루프 (EVALS_VERIFY=1)

1. 실행기가 설치된 검토 도구를 사용자와 같은 옵션(`--request`·`--map`·`--base`·`--conditions`·`--rounds`)으로 부른다. 작업 시작 상태는 가지·index 를 건드리지 않는 커밋 하나로 남겨 `--base` 로 주고, 지도는 프로젝트에 하나 있을 때 그것을 쓴다(여러 개면 미확인). 도구가 판정 대상 버전을 복사본으로 고정하고(커밋 하나), 검증자에게 **사용자 원문 전체(승인 턴 포함)·작업 지도의 `## 기준`·필수 조건(사례의 `verify-conditions.txt` 와 지도 기준의 ID)·대상 버전·작업 시작부터의 변경(diff)·실행 방법**만 준다. 구현자의 답과 지도의 `## 증거`(자기평가)는 주지 않는다.
2. 검증자는 복사본에서 검사를 실행해 답 끝에 정해진 형식의 JSON(`.agents/skills/wf-verify/verify.py` 의 `VERIFIER_PROMPT`)을 쓴다. `verdict.py` 가 이 형식만 읽는다(의미를 추측하지 않는다).
   - **ok**: OK, 조건마다 충족과 근거, 필수 조건 모두 포함. 전체 완료(`completion`)는 이것과 사례의 직접 검사(`check.py`)·작업 지도 요구 기록의 미정(`waiting-user`)·미확인 행을 `verify.completion` 한 규칙으로 합쳐, 모두 관찰로 확인됐을 때만 `verified`
   - **returned**: RETURN 과 사유 → 구현자에게 교정 턴을 보내고 **새 버전으로 다시 판정**. `EVALS_VERIFY_ROUNDS` 에 닿으면 `incomplete`
   - **unverified**: 빈 답, 형식 없음·깨짐, OK 인데 미충족·미확인·근거 없음·필수 조건 누락, 검증자 하네스 오류(종료 코드는 `verifier_exit_code`), 검증자가 복사본의 추적 파일(제품·검사·기준)을 바꿈. 검사가 만든 새 파일(산출물·캐시)은 무효 사유가 아니다
   - 새 요구가 있어야 하는 반례는 `out_of_scope` 로 따로 남고 완료를 막지 않는다
3. 회차 증거(판정 대상 복사본·검토 입력·답)는 끝난 뒤 결과 폴더의 `<이름>.rounds/` 로 옮긴다(프로젝트에 남기면 사례 판정이 구현자의 산출물로 읽는다).
4. 이 루프는 지금 도구의 옵션을 쓴다. v3.5 이하 커밋의 검토까지 비교하려면 그 태그를 꺼내 그 태그의 `evals/` 로 돌린다(검토 없는 일반 전후 비교는 그대로 된다).
5. 사례 판정(`check.py`, 그 단계의 기대 행동)과 전체 완료(`completion`)는 따로 센다. 승인 대기 단계의 통과는 구현 완료가 아니다.

## 실행 옵션

| 환경 변수 | 뜻 |
| --- | --- |
| `EVALS_RESULTS=<폴더>` | 결과 위치(기본 `evals/results/<날짜>`) |
| `EVALS_APPROVE=1` | 사례의 `approve.txt` 를 마지막 턴으로 더한다 |
| `EVALS_VERIFY=1` | 모든 턴 뒤에 실행기가 판정 대상의 복사본에서 별도 검증 세션을 띄운다(아래 「독립 검증 루프」) |
| `EVALS_VERIFY_ROUNDS=<n>` | 돌려보냄(RETURN) 뒤 교정·재검증을 몇 번까지 할지(기본 2). 닿으면 미완료 |
| `EVALS_LANG=<언어>` | 사례 `setup.sh` 에 넘겨 같은 사례를 다른 제품 언어로 만든다(archive-after-correction: `python`·`js`). meta 의 `lang` |
| `EVALS_CODEX_NETWORK=1` | Codex 작업 공간에 네트워크를 허용한다 |
| `EVALS_CLAUDE_SETTINGS=<JSON>` | 설치 뒤 프로젝트 `.claude/settings.json` 에 합친다(`enabledPlugins` 는 항목 단위). 실제 사용 조합 재현: `evals/profiles/real-plugins.json`(superpowers 를 프로젝트에서 끔, 사용자 설정의 compound-engineering 등은 그대로). 켜진 플러그인 목록 지문은 meta 의 `global_instructions.plugins`, 합친 내용은 `claude_project_settings` |

v3.2~v3.4 는 설치기가 두 하네스에 세션 시작 정보 훅을 두었고, v3.5 부터는 Claude 에만 둔다(Codex 에는 키트 훅이 없어 아래 신뢰 재현도 하지 않는다). Codex 는 프로젝트를 신뢰해야 프로젝트 훅을 읽으므로, 실행기가 정보 훅(wf-context)이 있는 커밋에서만 임시 홈의 `config.toml` 에 그 프로젝트의 `trust_level = "trusted"` 를 더하고(meta 의 `codex_project_trusted`), 훅 신뢰는 `--dangerously-bypass-hook-trust` 로 대신한다. 사용자 전역 설정은 바꾸지 않는다.

`claude`·`codex` CLI 가 설치·로그인되어 있어야 하고, 실제 모델 세션을 임시 폴더에서 권한 확인 없이 실행한다. 사용자 전역 설정은 건드리지 않는다.

실행 환경은 두 하네스가 다르다. **Claude** 는 사용자 홈(`~/.claude`)을 그대로 쓰므로 전역 지침·사용자 설정의 플러그인(예: superpowers·compound-engineering)·전역 훅이 함께 돈다(깨끗한 환경이 아니다). **Codex** 는 `auth.json`·`config.toml`·`AGENTS.md` 만 복사한 임시 홈을 쓴다(구현자 세션 하나에 하나, 검토자 세션은 회차마다 따로. `verdict.py session` 을 직접 불러도 같다). 프로젝트에 `.codex/hooks.json` 이 있을 때(정보 훅이 있던 v3.2~v3.4 커밋)만 `--dangerously-bypass-hook-trust` 로 사용자의 훅 신뢰를 대신한다.

승인 관문이 있던 v3.0 이하 커밋을 비교하려면 그 태그를 꺼내 그 태그의 `evals/` 로 돌린다(지금 `evals/` 는 관문을 다루지 않는다).

## 결과를 읽는 법

- **통과 수는 관찰이고, 두 커밋의 차이는 따로 확인해야 하는 주장이다.** 비교는 `run.sh <사례> 기준..대상` 으로 한다: 두 커밋을 번갈아 돌리고, 지금 판정기로 양쪽을 다시 판정한 뒤 나란히 보인다. 보고는 양쪽을 2회 이상 돌려 전부 뒤집힌 경우(0/n ↔ n/n)만 "차이"로 적는다. 1/3 대 0/3 같은 섞인 결과는 "말할 수 없음"이고, 양쪽이 모두 통과하는 사례는 "회귀 확인용"이라 두 커밋의 우열을 가르지 못한다. 2026-11-12 에 3회 중 1회 차이를 근거로 구조를 세 번 바꿨다가 모두 버렸다(그 사례는 시험 환경이 잘못돼 있었다).
- **사례가 요구하는 답의 근거가 출발 상태에 있는지 먼저 본다.** 통과 표본이 출발 상태에 없는 것을 지어내야 통과한다면 사례가 잘못된 것이다. 그런 사례의 실패는 키트의 실패가 아니다.
- **채택 원칙.** 승인·범위·데이터 같은 필수 보장을 지키면서 성공한 작업이 늘거나 사용자 개입이 줄면 채택한다. 결과가 비슷하면 더 짧고 빠른 쪽을 남긴다. 차이가 불확실하면 새 규칙을 더하지 않는다. 성공은 사용자 입장에서 본다(요구 충족, 정하지 않은 중요한 선택을 마음대로 하지 않음, 승인 범위 준수, 실패·미확인을 정확히 알림). 질문 수·답 길이·검토 횟수는 보조 지표다. 반복은 2회로 시작하고, 차이가 애매하며 채택에 중요한 사례만 늘린다. 작은 표본의 무회귀는 관찰이지 안전 증명이 아니다. 시간(기준의 1.2배)은 운영 한도로만 본다.
- **비교 대상은 main 만이 아니다.** 같은 모델·도구에서 키트 없음(빈 지침) / 최소 기준(지침 몇 줄) / 현재 키트를 함께 돌려, 절차가 결과를 실제로 바꾸는지 본다. 차이가 없는 절차는 걷어낸다.
- **사례는 `cases/` 에 두고 표본으로 판정 검사를 확인한다.** 숨겨 둔 평가 사례는 없다. `holdout/` 에는 기계 판정이 REVIEW·FAIL 만 내 통과 표본을 만들 수 없는 `goal-context`와 `recommend-missing-goal`이 있고, run.sh 는 `cases/` 에 없는 이름을 거기서 찾는다. 이미 본 사례의 통과를 보지 않은 입력의 성능으로 세지 않는다.
- **변경은 따로 되돌릴 수 있게 나눈다.** 서로 다른 설계 변경을 한 커밋에 섞으면 효과 없는 것만 되돌릴 수 없다.
- **양쪽을 같이 본다.** 묻기가 늘었는지(정정 사례)와 쓸데없이 묻지 않는지(명시 사례)를 함께 봐야 한쪽만 좋아진 것을 잡는다.
- **효과가 없으면 문장을 더 세게 고치지 않고 되돌린다.** 원인 자리를 다시 찾는다(루트 README 「실패에서 배우는 루프」).
