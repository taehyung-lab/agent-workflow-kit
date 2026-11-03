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
```

## 사례 (cases/)

사례 하나는 **반복되면 안 되는 실패 한 종류**다. 실패가 나올 때마다 사례를 늘리지 않고, 같은 종류는 기존 사례의 변형·표본으로 둔다.

| 사례 | 무엇을 막나 |
| --- | --- |
| archive-ambiguity · archive-after-correction · account-after-correction | 결과가 갈리는 선택(언제 옮기나, 비활성 계정 로그인을 막나)을 묻지 않고 정하는 것. 정정 뒤에도 같다 |
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
- `verifier_record`: 검증자를 띄운 흔적이 `observed`(있음)·`none`(볼 수 있는 기록에 없음)·`no-record`(Codex 원본 기록이 없어 볼 수 없음) 중 무엇인가. Codex 는 `exec` 기록에 하위 에이전트 생성이 남지 않아서 원본 기록(rollout)을 함께 본다. **띄운 흔적은 검증 통과의 증거가 아니다.**

한때 이 구분이 없어서 "Codex 가 하지도 않은 검증을 했다고 보고한다"고 잘못 판정한 적이 있다. 측정 도구도 틀릴 수 있으므로, 결론이 이상하면 원시 기록부터 본다.

## 모델 없이 도는 시험 (CI)

```text
bash evals/selftest.sh       # 표본 판정·관찰 기대값·실행기 계약(종료 코드, 외부 장애 분류, 승인 대기 집계 등)
python3 -I evals/gatetest.py # 승인 관문 훅(승인 판별, 쓰기·읽기 셸 구분, 턴 끝 상태 검사)
```

GitHub CI 가 매 push 마다 `selftest.sh` 를 돌린다. 판정 검사를 고쳤으면 `python3 -I evals/rejudge.py evals/results/<폴더>` 로 저장된 결과를 다시 판정한다(실행 때의 입력·관문 조건을 복원한다).

## 실행 옵션

| 환경 변수 | 뜻 |
| --- | --- |
| `EVALS_RESULTS=<폴더>` | 결과 위치(기본 `evals/results/<날짜>`) |
| `EVALS_APPROVE=1` | 사례의 `approve.txt` 를 마지막 턴으로 더한다 |
| `EVALS_VERIFY=1` | 모든 턴 뒤에 실행기가 별도 검증 세션을 띄운다. 검증자는 사용자 원문·변경·구현자의 마지막 답만 받는다 |
| `EVALS_CODEX_NETWORK=1` | Codex 작업 공간에 네트워크를 허용한다 |

`claude`·`codex` CLI 가 설치·로그인되어 있어야 하고, 실제 모델 세션을 임시 폴더에서 권한 확인 없이 실행한다. Codex 는 프로젝트 훅을 쓰려고 `--dangerously-bypass-hook-trust` 로 사용자의 훅 신뢰를 대신한다. 사용자 전역 설정은 건드리지 않는다(Codex 는 임시 홈을 쓴다).

## 결과를 읽는 법

- **한 번 통과는 개선의 증거가 아니다.** 하네스마다 여러 번 돌리고, 바꾸기 전 커밋과 비교한다.
- **양쪽을 같이 본다.** 묻기가 늘었는지(정정 사례)와 쓸데없이 묻지 않는지(명시 사례)를 함께 봐야 한쪽만 좋아진 것을 잡는다.
- **효과가 없으면 문장을 더 세게 고치지 않고 되돌린다.** 원인 자리를 다시 찾는다(루트 README 「실패에서 배우는 루프」).
