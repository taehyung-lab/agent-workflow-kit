# 변경 기록

버전마다 설치되는 파일에서 무엇이 바뀌는지와 그 버전으로 업데이트할 때 알아 둘 것을 최신 순으로 둔다. 업데이트 방법은 [README.md](README.md) 「업데이트」에 있다.

**v3.5 → v3.6.** AGENTS.md·훅은 그대로다. 검토 도구(`verify.py`)에 `record` 명령이 생긴다: `verify.py record --map <지도> --check <직접 검사 결과>` 가 독립 검토 없이 작업 지도 `## 기준` 의 `요청 원문` 항목과 요구 기록 표 형식을 검사하고 전체 완료(`completion`)를 낸다(파일을 쓰지 않는다). guide.md 「작업 지도」에 이 명령을 쓰는 때(지도를 쓰거나 고친 뒤, 완료 전)가 들어가고, 「독립 검토」에서 AGENTS.md 와 겹치던 "사용자 요구·검사 약화는 반드시 받는다" 문장이 빠진다(AGENTS.md 「선택」에 그대로 있다). 검토자 입력의 「필수 조건」 칸에 판정할 조건 ID 가 적힌다. `verify.py` 가 평가 실행기만 쓰던 옵션(`--reviewer`·`--criteria`·`--plan`·`--base-dir`·`--state`·`--keep`·`--log`·`--answer`·`--exit-code`)을 받지 않는다. 일반 사용 옵션(`--map`·`--request`·`--base`·`--output`·`--conditions`·`--rounds`, `finish --round`·`--check`)은 그대로다. 업데이트 전에 `prepare` 만 해 둔 검토 회차는 미확인이 되므로 `prepare` 부터 다시 한다. 평가 실행기의 검토 루프(`EVALS_VERIFY=1`)는 v3.6 이후 커밋만 돌린다(그 전 커밋의 검토 비교는 그 태그의 `evals/` 로).

**v3.4 → v3.5.** AGENTS.md·guide.md·검토 도구는 그대로다. 설치기가 Codex(`.codex/hooks.json`)에 세션 시작 정보 훅을 두지 않고, 업데이트 때 v3.2~v3.4 가 둔 키트 항목만 지운다. 같은 파일의 프로젝트 훅·순번·다른 설정은 그대로이고, 키트 항목만 있던 파일은 지운다. Claude 정보 훅은 그대로다. Codex 는 프로젝트 훅을 경로·명령마다 따로 신뢰받아야 실행하고 신뢰 전에는 경고 없이 건너뛰어, 새 워크트리·자동 실행(Orca 등)에서는 정보를 넣지 못한 채 확인창만 띄웠다. Codex 에서는 시작·대상 변경·재개 때 `python3 .agents/skills/wf-context/context.py inspect` 로 같은 정보를 본다. 맥락 사례 10개를 Codex 로 v3.4.3(훅이 실제로 맥락을 넣음)과 비교해 둘 다 10/10 이었다(사례당 1회). 세션 시작 칸에 프로젝트 훅이 같이 있던 Codex 설정은 그 훅의 신뢰를 한 번 다시 물을 수 있다.

**v3.4.2 → v3.4.3.** AGENTS.md·guide.md·훅은 그대로다. 검토 도구(`verify.py`)가 추적하지 않는 파이썬 캐시(`__pycache__`·`.pyc`·`.pyo`)를 판정 대상·원본 지문에서 뺀다. 전에는 프로젝트의 무시 목록에 캐시가 없으면 구현자의 검사 실행이 만든 캐시가 대상에 복사돼, 검토자가 검사를 돌리기만 해도 "검토자가 대상을 바꿨다"로 미확인이 났다. 검토 도구의 미확인 사유 설명을 v3.4.2 동작(전달한 근거 파일·지도 기준·맥락·비교 기준 폴더 대조)에 맞게 고쳤다.

**v3.4.1 → v3.4.2.** AGENTS.md·guide.md·훅은 그대로다. 검토 도구(`verify.py`)가 `prepare` 에서 읽은 근거(원문·계획·조건·산출물 파일, 지도 `## 기준`·`## 맥락`, 비교 기준 폴더)를 한 기록으로 남기고 `finish`·끝난 회차 재조회·한도 뒤 재사용 때 현재와 대조한다. 전에는 제품 파일과 지도 `## 기준` 만 대조해, 예를 들어 `work/` 안 원문 파일을 검토 중에 바꿔도 이전 판정이 `ok`·`verified` 로 남았다. 근거 기록이 없는 옛 회차는 현재 결과로 인정하지 않고 `unverified` 로 낸다. 지도 `## 기준` 의 요청 원문 인용과 `--request` 두 입력 방식은 그대로 받는다. 저장소 안의 평가 도구는 재판정이 미정·미확인 근거를 잃어 답 대기를 완료로 바꾸던 문제를 고쳤다(`evals/result.py`).

**v3.4.0 → v3.4.1.** 문서만 바뀐다(README 소개·docs/direction.md 의 목적과 v3.4 실측, evals/goalflow/criteria.md 의 Q3 판정 정정). 설치되는 파일은 v3.4.0 과 같다.

**v3.3 → v3.4.** AGENTS.md 기본 2 가 바뀐다: 이번 작업에 사용자 결정이 남아 있으면 조사·재현까지만 하고 제품 파일은 답 뒤에 고친다(무관해 보이는 부분도 먼저 구현하지 않는다). 질문에는 근거가 정한 것과 남은 선택을 함께 보이고 독립 질문만 묶는다. guide.md 「질문」의 한 문장이 같은 뜻으로 바뀐다. 훅·설정 파일·`verify.py`·`context.py` 는 바뀌지 않으므로 Codex 훅 신뢰 확인은 다시 나오지 않는다.

**v3.2 → v3.3.** AGENTS.md 는 그대로다. guide.md 「작업 지도」의 `## 기준` 이 요구 기록 표(`ID | 요구 | 출처·위치 | 의존 | 확인 방법 | 상태`: 확정·미정·미확인)로 바뀌고, 「독립 검토」 3단계가 `verify.py finish --round <kept> --check <직접 검사 결과 PASS|FAIL|REVIEW>` 로 바뀐다. 전체 완료(`completion`)는 검토 OK·직접 검사 PASS·미정·미확인 행 없음이 모두 맞을 때만 `verified` 다: `--check` 를 주지 않으면 통과로 가정하지 않고 `unverified`, 직접 검사 REVIEW 는 `needs-review`(전에는 `verified`), 미정 행이 남으면 `waiting-user`. 표의 형식 문제는 검토자 없이 `returned` 로 돌아온다. 표가 없는 기존 지도는 그대로 동작한다(형식 검사를 건너뛴다). 훅·설정 파일은 바뀌지 않는다.

**v3.1 → v3.2.** AGENTS.md 기본 1 이 "결과를 둘 대상과 읽는 근거를 구별하고, 요청 원문·유효한 결정·앞뒤 시나리오로 결과·범위를 정한다"로 바뀌고, guide.md 에 「맥락 봉투」가 생긴다. 맥락 확인 도구(`.agents/skills/wf-context/context.py`)가 설치되고, 업데이트가 `.claude/settings.json`·`.codex/hooks.json` 의 `SessionStart` 에 정보 훅 항목 하나를 더한다(다른 훅·설정은 그대로, 파일이 없으면 만든다). `verify.py prepare` 는 지도 `## 맥락` 과 맥락 도구 출력을 검토 입력에 넣고, 분석만 한 작업은 `--output <파일>` 을 받는다(바뀐 파일도 산출물도 없으면 입력 부족). Codex 를 쓰면 업데이트 뒤 첫 실행에서 프로젝트·훅 신뢰를 확인한다.

```bash
git -C /path/to/agent-workflow-kit fetch --tags && git -C /path/to/agent-workflow-kit checkout v3.2.0
bash /path/to/agent-workflow-kit/install.sh --update /path/to/target-repository
```

**v3.0 → v3.1.** 승인 관문(`.agents/skills/wf-design/approval-gate.py`)과 그 훅이 없어진다. 업데이트가 그 파일과 그 파일의 바이트코드 캐시(`wf-design/__pycache__/approval-gate.*.pyc`), 그리고 `.claude/settings.json`·`.codex/hooks.json` 에서 명령에 `approval-gate.py` 가 든 훅 항목만 지운다. 같은 파일의 다른 훅(예: 저장 뒤 포맷터 훅)·`enabledPlugins`·권한 설정은 그대로 둔다. 사용자 전역에 관문을 등록했다면(`~/.codex/hooks.json` 등) 설치기는 건드리지 않으므로 직접 지운다(남겨 두어도 파일이 없으면 아무것도 하지 않는다). AGENTS.md 기본 3이 바뀌었고, `verify.py prepare` 는 관문 기록 대신 지도 `## 기준` 의 `요청 원문` 항목이나 `--request <파일>` 을 쓴다.

```bash
git -C /path/to/agent-workflow-kit fetch && git -C /path/to/agent-workflow-kit checkout v3.1.0
bash /path/to/agent-workflow-kit/install.sh --update /path/to/target-repository
```

**v2 → v3.** 단계 스킬(`wf-design`·`wf-implement`·`wf-verify` 의 `SKILL.md`)과 지도 양식(`work-template.md`)이 없어지고 `.agents/skills/guide.md` 하나로 바뀐다. 업데이트가 키트 파일은 지우지만, 프로젝트 절·역할 스킬·문서가 `wf-*` 스킬을 가리키면 그 설명은 프로젝트가 직접 고친다. 승인 관문 경로(`.agents/skills/wf-design/approval-gate.py`)는 그대로라 사용자 전역 훅 등록은 바꿀 필요가 없다. 검토 도구 사용법은 `verify.py prepare`·`finish` 로 바뀌었다(guide.md 「독립 검토」).
