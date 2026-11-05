# tests: 설치기가 약속을 지키는지

`install.sh` 는 다른 사람의 저장소에 파일을 쓰므로 실수하면 프로젝트 내용을 덮어쓸 수 있다. `install.test.sh` 는 그런 일이 없는지 매 push 마다(GitHub CI) 확인한다. 모델은 쓰지 않는다.

```text
bash tests/install.test.sh   # 끝줄: "N passed, 0 failed"
```

작업 트리의 키트를 임시 git 저장소로 복사해 버전 커밋을 몇 개 만들고, 빈 폴더·기존 프로젝트를 흉내 낸 폴더에 설치·업데이트해 본다.

| 확인하는 약속 | 예 |
| --- | --- |
| 처음 설치하면 키트 파일·링크·버전 기록이 생긴다 | `AGENTS.md`, `CLAUDE.md`, `.agents/skills/wf-*`, `.claude/skills` 링크, `.agents/agent-workflow-kit.version` |
| 이미 있는 것은 덮어쓰지 않고 쓰기 전에 멈춘다 | 기존 `AGENTS.md` 가 있으면 "Conflict" 로 멈추고 아무것도 바꾸지 않음 |
| 대상 밖으로 쓰지 않는다 | `.agents`·`.claude`·`.codex` 가 다른 곳을 가리키는 링크면 거절 |
| 업데이트는 키트 몫만 바꾼다 | AGENTS.md 의 키트 표시 영역만 교체하고, 그 아래 「프로젝트 지도」와 프로젝트 역할 스킬은 그대로 |
| 키트 몫을 프로젝트가 고쳤으면 멈춘다 | 같은 버전이어도 로컬 변경이 있으면 "Local change" 로 멈춤 |
| 훅·권한 설정을 설치하지 않는다 | 처음 설치는 `.claude/settings.json`·`.codex/hooks.json` 을 만들지 않고, 있으면 바이트 그대로 둔다 |
| v3.0.0 설치본 업데이트는 관문 훅 항목만 지운다 | 실제 `v3.0.0` 태그로 설치(그 설치기가 훅 등록)한 뒤 업데이트: `approval-gate.py` 항목·파일·바이트코드 캐시만 지우고, 포맷터 `PostToolUse` 훅·같은 그룹의 프로젝트 훅·`enabledPlugins`·권한은 그대로. 그 항목이 든 설정이 깨진 JSON 이면 쓰기 전에 멈춤. `v3.0.0` 태그가 필요하다(CI 는 `fetch-depth: 0`) |
| 미커밋 키트·오래된 버전으로는 설치하지 않는다 | 커밋하지 않은 키트, 설치된 것보다 오래된 커밋은 거절 |

사용자 전역 설정(`~/.claude`, `~/.codex`)은 설치기도 시험도 건드리지 않는다.
