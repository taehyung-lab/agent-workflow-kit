# agent-workflow-kit
요구와 현재 연결에서 관찰 조건을 만들고 구현·검증·원인 교정으로 잇는 얇은 작업 기준이다.
> A thin workflow: request and current dependencies → observable conditions → checks.
> Choose steps by uncertainty, impact, and risk; correct the cause when checks fail.
> Korean is canonical. No reuse license is currently specified.

## 설치
확인한 버전의 로컬 키트에서 `bash /path/to/agent-workflow-kit/install.sh /path/to/target-repository`를 실행한다.

기존 설치 대상·루트 work 경로·부모 심링크·부모 비디렉터리는 쓰기 전에 거절한다. .gitignore는 일반 파일만 허용하고 기존 내용에 `/work/` 줄이 없으면 덧붙인다.
다른 설치·편집이 없는 대상에서 실행한다. 권한·I/O 실패 때 일부 신규 파일이 남을 수 있으므로 종료 코드와 대상을 확인하고 병합 범위를 정한다.
설치 후 AGENTS.md 지도를 저장소 근거로 채우고 새 세션에서 wf-design·wf-implement·wf-verify가 발견되는지 확인한다.
CLAUDE.md는 `@AGENTS.md`, `.claude/skills`는 `.agents/skills`를 가리킨다. 이 키트는 세션을 자동 생성하지 않는다.
에이전트에게 맡길 때: "https://github.com/taehyung-lab/agent-workflow-kit 를 clone해 install.sh로 이 저장소에 설치하고, AGENTS.md 지도를 이 저장소를 조사해 채워줘. 설치기가 멈추면 병합안을 먼저 보여줘."

## 무게 예시
예시는 보통의 연결을 가정한다. 실제 조건·소유자·소비자를 확인하고 질문과 독립 검증의 필요를 각각 판단한다.
| 요청 | 보통의 판단 | 진행 |
| --- | --- | --- |
| 버튼 문구 변경 | 조건 확정·영향 좁음·가역 | 직접 수정·렌더 확인 |
| 목록 필터 추가 | 제품 공백·URL과 조회 연결 | 짧은 설계·구현; 공용 경계 변경 시 독립 검증 |
| 일괄 삭제 버튼 | 삭제 계약·권한·비가역 | 필요한 질문·설계·구현·독립 검증 |
| 화면 전체 | 진입·조회·액션 연결이 넓음 | 설계·구현·독립 검증; 확정된 정적 화면처럼 연결이 좁으면 가볍게 |

## 역할 스킬
반복 판단의 실제 소유자가 필요할 때 `.agents/skills/<이름>/SKILL.md`를 만든다. description으로 필요한 책임만 선택한다.
    ---
    name: list-search
    description: 목록 검색·필터·정렬·페이지의 상태 기준을 다룰 때 읽는다. 서버 파라미터는 외부 계약, 문구·옵션은 제품 원문을 본다.
    ---
    # 목록 검색 공용 기준
본문에는 출처 있는 확정 결정·관찰 조건과 미정을 구분한다. 필요한 요청·동의어·무관한 요청으로 선택을 확인한다.
외부 스킬은 본문·출처·고정 버전·권한·도구 의존성을 확인하고 필요한 능력만 채택한다.

## 라이선스
현재 별도 재사용 라이선스가 없다. 복제·수정·재배포 조건은 저장소 소유자에게 확인한다.
