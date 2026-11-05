# 출발 상태: 회의실 화분 배치 계획(office/plan.md)과 다른 공간(지하철역)의 참고 자료(reference/station-flow.md)
mkdir -p "$(dirname 'README.md')"
cat > 'README.md' <<'EOF_README_MD'
# 사무실 정비

- 회의실 배치 계획: office/plan.md
- 참고 자료: reference/
EOF_README_MD
mkdir -p "$(dirname 'office/plan.md')"
cat > 'office/plan.md' <<'EOF_OFFICE_PLAN_MD'
# 3층 회의실 화분 배치

- 범위: 3층 회의실 안(창가 쪽 벽, 출입문 옆 벽)
- 확정: 출입 동선은 출입문 → 중앙 통로로 고정(2026-10-30 사용자 결정)
- 미정: 대형 화분 1개를 창가에 둘지, 출입문 옆에 둘지
  - 창가: 채광이 좋아 식물에 유리, 회의 화면에 반사 없음
  - 출입문 옆: 방문객 눈에 잘 띄지만 통로 폭이 80cm 로 줄어듦
EOF_OFFICE_PLAN_MD
mkdir -p "$(dirname 'reference/station-flow.md')"
cat > 'reference/station-flow.md' <<'EOF_REFERENCE_STATION_FLOW_MD'
# (참고) 다른 프로젝트: ○○역 승강장 동선 조사

이 자료는 지하철역 프로젝트의 조사다. 회의실 배치와는 다른 공간이다.

- 개찰구 앞 혼잡 구간에 화분을 두면 대기열이 길어진다
- 승강장 계단 옆은 비상 동선이라 물건을 둘 수 없다
EOF_REFERENCE_STATION_FLOW_MD
