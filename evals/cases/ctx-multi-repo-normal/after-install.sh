# 옆에 라이브러리 저장소 두 개를 만든다(읽기만 할 근거). 앱은 각 라이브러리의 함수 하나씩만 쓴다.
set -e
for lib in lib-a lib-b; do
  mkdir "../$lib" && (cd "../$lib" && git init -q && mkdir src)
done
printf 'export retry_with_backoff(times, base_ms)\nexport jitter(ms)\n' > ../lib-a/src/index.txt
printf 'export format_amount(value, currency)\nexport parse_amount(text)\n' > ../lib-b/src/index.txt
for lib in lib-a lib-b; do (cd "../$lib" && git add -A && git -c user.name=evals -c user.email=evals@invalid commit -qm init); done
