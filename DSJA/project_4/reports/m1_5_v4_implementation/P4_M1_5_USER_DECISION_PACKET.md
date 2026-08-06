# P4 M1.5 v4.0 User Decision Packet

상태: `USER_DECISION_REQUIRED`

기술 구현·offline 테스트는 자동 진행했습니다. 아래 항목만 사용자 결정이 필요합니다.

## D-M2-001

질문: production Linkareer crawl 실제 실행을 승인할 것인가?

현재 증거: 현재 호출 0; 58/79개월 pagination 미검증

선택지: A 승인 / B 조건부 승인 / C 보류

권고안: C 보류

권고 이유: source-policy와 credential custody 선행

선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.

결정 연기 가능 여부: 연기 가능

## D-M2-002

질문: source-policy human approval record를 확정할 것인가?

현재 증거: kill switch 코드는 PASS, 인간 승인 기록은 없음

선택지: A 서명 승인 / B 조건부 승인 / C 보류

권고안: A

권고 이유: 운영 권한과 중단조건을 감사 가능하게 고정

선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.

결정 연기 가능 여부: M2 전까지만 연기 가능

## D-SEC-001

질문: API key 회전·보관·runtime injection 정책을 승인할 것인가?

현재 증거: 사용 가능한 NCS/Work24 credential 없음; 노출 0

선택지: A secret store+회전 / B 현행 유지 / C API 미사용

권고안: A

권고 이유: 키를 artifact와 분리하고 live probe를 통제

선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.

결정 연기 가능 여부: live probe 전까지만 연기 가능

## D-M3-001

질문: core AI·IT cohort 범위를 동결할 것인가?

현재 증거: candidate code set은 있으나 human freeze 없음

선택지: A 69/51안 동결 / B 통신02 포함 / C 방송03 포함 후 재검토

권고안: A를 검토 후 signed release

권고 이유: 분모와 NCS 분석 범위의 사전고정

선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.

결정 연기 가능 여부: M3 전까지 연기 가능

## D-DISC-001

질문: LLM_REFERENCE 사용 사실과 한계를 기사에 공개할 것인가?

현재 증거: 현재 HUMAN_GOLD 0, LLM reference 실행 0

선택지: A 본문+방법론 공개 / B 방법론만 / C 사용 안 함

권고안: A

권고 이유: HUMAN_GOLD와 혼동 방지

선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.

결정 연기 가능 여부: 기사 작성 전까지 연기 가능

