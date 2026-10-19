# agent-workflow-kit

어떤 언어·프로젝트에도 넣을 수 있는 얇은 에이전트 작업 기반이다. 요구를 정리해 설계하고, 다른 세션이 구현하고,
또 다른 세션이 실제 결과로 검증한다. 실패하면 원인(요구·설계·구현·검사·환경)이 있는 곳을 고쳐 다음 작업이 같은 실수를 덜 하게 한다.

이 키트가 정하는 것은 결과·근거·관찰·권한·인계의 경계다. 작업 방법은 모델이 고르며, 모델·도구가 바뀌면 아래
"규칙을 걷어내는 법"으로 낡은 방법 지시를 재평가한다. 시도 수나 비용이 줄었는지는 실제 비교 결과로 판단한다.

> A lightweight workflow kit for planning, implementation, and independent verification in separate agent sessions.
> The Korean instructions are the canonical version. Install the files into your repository, fill in the project map
> in AGENTS.md, and share one temporary work file between sessions. Sessions must have access to the same code and
> evidence; the kit does not launch sessions automatically. Check the license status before reusing or redistributing the kit.

## 구성

| 파일 | 역할 |
| --- | --- |
| `AGENTS.md` | 진입: 작업 경로, 질문 경계, 완료·인계, 안전, 프로젝트 지도(설치 시 채움) |
| `CLAUDE.md` | Claude Code의 AGENTS.md 연결(`@AGENTS.md`). 다른 런타임은 해당 런타임이 지원하는 방식으로 같은 정본을 읽게 한다 |
| `.agents/skills/wf-design/` | 요구와 설계. `work-template.md`는 세션 인계 양식 |
| `.agents/skills/wf-implement/` | 인계 구현, 직접 검사, 변경 기록 |
| `.agents/skills/wf-verify/` | 독립 판정, 실패 원인 회수, 재확인 |
| `work/<작업명>/work.md` | 작업 중에만 생기는 인계 파일. 선택한 임시 경로만 Git에서 제외하며, 완료 보고·정본 반영 후 해당 작업 자료만 삭제한다 |

## 에이전트에게 설치 맡기기

새 프로젝트든 기존 프로젝트든, 대상 저장소에서 에이전트에게 이 저장소 주소와 함께 이렇게 요청하면 된다.

```text
https://github.com/taehyung-lab/agent-workflow-kit 의 README "설치"대로 이 저장소에 키트를 설치하고,
AGENTS.md의 프로젝트 지도를 이 저장소를 조사해서 채워줘. 기존 진입 문서·스킬과 겹치면 쓰기 전에 병합안을 보여줘.
```

설치하는 에이전트는 다음 순서를 따른다.

1. 아래 "설치"를 실행한다. 충돌로 멈추면 기존 파일과 키트 파일을 비교한 병합안을 사용자에게 보이고 승인 뒤에 쓴다.
2. 저장소를 조사해 프로젝트 지도를 채운다: 패키지·빌드 설정에서 실행·검사 명령, README·docs에서 제품 원문과 결정 위치,
   API 명세·스키마 위치, 테스트·브라우저·시험 데이터 도구. 찾은 칸에는 근거 파일을 함께 적고, 못 찾은 칸은 "미확인"으로 둔다.
3. 조사로 정할 수 없는 것(제품 원문 위치, 결정권자, 보호 대상, 작업 한도)만 사용자에게 묻는다.
4. 기존 진입 문서(AGENTS.md·CLAUDE.md 등)에 있던 저장소 고유 사실은 지도나 해당 역할 스킬로 옮기고, 작업 절차만 이 키트로 대체한다.
   삭제할 기존 문서는 목록으로 보이고 승인 뒤에 지운다.
5. 새 세션에서 `wf-design`·`wf-implement`·`wf-verify`가 보이는지 확인하고 결과를 보고한다.

## 설치

먼저 사용할 키트 버전을 내려받고(재현성이 필요하면 tag나 commit을 checkout한다) 대상 저장소의 루트로 이동한다.
아래 명령은 AGENTS.md·CLAUDE.md와 세 wf-* 스킬의 설치 위치가 모두 없는 첫 설치용이다. 같은 이름의 파일·디렉터리·심링크가
있거나 .agents/.claude 경로가 심링크면 멈추므로, 실제 대상을 확인한 뒤 기존 내용을 비교·병합한다.
Claude Code를 쓰지 않으면 CLAUDE.md 복사와 .claude/skills 연결은 생략해도 된다.

```bash
# 아직 clone하지 않았다면 실행한다. 기존 clone에는 덮어쓰지 않는다.
git clone https://github.com/taehyung-lab/agent-workflow-kit.git "$HOME/.agents/kits/agent-workflow-kit"
# 아래는 별도 subshell에서 실행한다. /path/to/target-repository 를 실제 경로로 바꾼다.
(
  set -e
  KIT="$HOME/.agents/kits/agent-workflow-kit"
  cd /path/to/target-repository
  for p in AGENTS.md CLAUDE.md .agents/skills/wf-design .agents/skills/wf-implement .agents/skills/wf-verify .claude/skills/wf-design .claude/skills/wf-implement .claude/skills/wf-verify; do
    if [ -e "$p" ] || [ -L "$p" ]; then
      echo "기존 경로를 먼저 비교·병합하세요: $p" >&2
      exit 1
    fi
  done
  for p in .agents .agents/skills .claude .claude/skills; do
    if [ -L "$p" ]; then
      echo "심링크의 실제 설치 대상을 먼저 확인하세요: $p" >&2
      exit 1
    fi
  done
  cp "$KIT/AGENTS.md" "$KIT/CLAUDE.md" .
  mkdir -p .agents/skills .claude/skills
  for s in wf-design wf-implement wf-verify; do
    cp -R "$KIT/.agents/skills/$s" .agents/skills/
    ln -s "../../.agents/skills/$s" ".claude/skills/$s"
  done
)
```

대상 저장소의 루트 `work/`가 이 키트의 임시 작업 전용인지 먼저 확인한다. 전용이면 `.gitignore`의 기존 내용을 보존하고
줄을 분리해 `/work/`를 추가한다. 이미 다른 용도로 쓰는 경로라면 충돌 없는 임시 루트 경로를 정하고, AGENTS.md의 인계 경로와
wf-design의 출력 경로를 함께 맞춘 뒤 그 경로만 제외한다. 기존 `work/`의 자료는 이동·삭제하지 않는다.

그다음 `AGENTS.md`의 "프로젝트 지도"를 실제 위치로 채운다. 모르는 칸은 비워 두지 말고 "미확인"으로 적는다.
런타임 진입 파일과 스킬은 정본 하나를 가리키게 하고 본문을 복제하지 않는다.

Codex는 대상 저장소의 `.agents/skills`에서 세 스킬을 찾는다. 설치한 저장소에서 새 세션을 열어 wf-design·wf-implement·wf-verify가
보이는지 확인하고, 반영되지 않으면 재시작한다. 목록에서 찾지 못하면 AGENTS.md에 적힌 SKILL.md 경로를 직접 읽게 하고
런타임 설정을 확인한다. `.codex/skills`에 본문을 중복 복사하지 않는다.

## 쓰는 법

단순 질의·명령과 확정 값의 작은 수정은 관련 결과를 직접 확인하고, 별도 인계가 필요 없으면 한 세션에서 끝낸다.
사용자나 프로젝트가 별도 세션·독립 검증을 요구하면 그 조건을 따른다.

새 동작·제품 판단·구조 변경은 세션 A의 wf-design → 새 세션 B의 wf-implement → 새 세션 C의 wf-verify로 진행한다.
이 키트는 세션을 자동으로 열지 않으며 전체 담당자가 각 세션과 실패 회수를 연결한다.

다음 세션에 work 파일 경로와 맡을 단계를 전달하고 현재 작성자를 갱신한다. 경로만 전달하려면 다음 세션이 같은 코드·work 파일·증거에
접근할 수 있어야 한다. 다른 worktree·clone·실행 환경을 쓰면 필요한 변경과 임시 자료를 먼저 전달하고 기준 버전을 확인한다.
다음 작성자가 인계받은 뒤 이전 작성자는 같은 work 파일을 수정하지 않는다.

## 외부 스킬 선택

이 키트는 세션 인계·결과 판정·실패 회수의 경계를 제공한다. 언어·브라우저·테스트 등 개별 능력은 기존 도구나 외부 스킬을 필요할 때 연결한다.

먼저 필요한 능력과 관찰할 결과를 적는다. 복잡한 제품 공백에는 grill 계열, 반복 가능한 결함 검사에는 tdd, 구조 이유 조사에는 how·why 계열 등을 후보로 볼 수 있지만 이름만 보고 설치하지 않는다.

채택 전에 실제 본문·라이선스·도구 의존성·권한·자동 쓰기 동작을 확인한다. 필요한 요청, 같은 뜻의 다른 표현, 관계없는 요청으로 선택을 시험하고 대표 결과 하나를 실행해 본다. 불필요한 질문이나 전체 운영 절차를 중복 강제하면 제외한다.

채택한 스킬은 버전 또는 commit을 고정하고 AGENTS의 지도에 사용 상황과 위치를 적는다. 수정이 필요하면 출처와 변경 이유가 분명한 fork를 사용한다. 같은 본문을 여러 정본으로 복제하지 않는다.

직접 만드는 스킬은 기존 도구로 해결되지 않는 반복 판단이 확인됐을 때만 추가한다. 역할 이름이나 미래 요구를 채우기 위해 미리 만들지 않는다.

## 규칙을 걷어내는 법

모델·도구가 바뀌거나 안내가 자주 읽히고 비용이 크거나 다른 작업을 방해하면 그 안내를 재평가한다. 결과·근거·권한을 유지하고 방법 지시부터 고른다.

실패 대응으로 방법 문장을 바꿀 때는 `(출처: <추적 가능한 근거>, <날짜>; 재검토: <조건>)`를 붙인다. 완료 후 삭제할 work.md만 유일한 근거로 쓰지 말고 필요한 이유를 기존 결정·검사·변경 이력에 남긴다. 기존 문장으로 표현할 수 있으면 교체·통합한다.

같은 작업·시작 코드·모델·도구·데이터·권한을 두고 안내가 있는 경우와 없는 경우를 새 세션에서 비교한다. 필수 조건별 결과, 첫 시도 성공, 수정 횟수, 사람 개입, 시간·가능한 비용, 새 결함을 기록한다.

제거해도 필수 결과가 유지되고 비용이나 방해가 줄면 제거한다. 회귀하면 원인에 맞게 유지·축소하고, 차이가 불분명하면 효과 미확인으로 남긴다. 한 번의 성공을 모든 작업의 개선이라고 주장하지 않는다.

모든 규칙을 한꺼번에 비교하지 않는다. 시험의 대상·종료 조건·한도를 먼저 정하고, 수용 기준이나 필수 접근 제한을 낮춰 성공을 만들지 않는다.

## 라이선스

현재 이 키트에는 재사용 라이선스가 지정되어 있지 않다. 공개 열람과 GitHub fork 외의 복제·수정·재배포 조건은 저장소 소유자에게 확인한다.
