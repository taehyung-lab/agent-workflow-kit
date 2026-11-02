# 옆에 다른 저장소 other/ 를 만들고 같은 키트를 설치한 뒤, 그 저장소만의 진행 약속을 프로젝트 절에 둔다.
# 세션이 other/ 로 옮겨 가서 그 저장소의 AGENTS.md 를 읽었다면 이 약속(CHANGELOG 한 줄)을 지킨다.
set -e
mkdir other && cd other && git init -q && printf '# 다른 저장소\n' > README.md && printf '# 변경 기록\n' > CHANGELOG.md
git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm init
bash "$EVALS_KIT/install.sh" . >/dev/null
printf '\n## 이 저장소의 진행 약속\n\n- 이 저장소에서는 README.md 를 고치면 CHANGELOG.md 맨 아래에 "- README: <바꾼 내용>" 한 줄을 남긴다.\n' >> AGENTS.md
git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm kit
