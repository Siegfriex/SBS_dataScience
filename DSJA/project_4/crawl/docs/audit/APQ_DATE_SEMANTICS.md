# APQ 날짜/상태 필터 의미론 — 실증 결과

- 기준일: 2026-08-06 / 검증 에이전트: Agent 1(인세인서치)
- 대상: `CalendarScreen_ActivityCalendarEntries`, `CalendarScreen_Activities` (both persisted GET, `api.linkareer.com/graphql`)

## 1. `status` 필터 의미 — "OPEN"은 문서 최초 가정과 다르게 동작

2020-03(activityTypeIDs=["5"]) 동일 구간에 대해 4가지 변형을 실측:

| 변형 | HTTP | sum(start.totalCount) |
|---|---|---|
| `status:"OPEN"` | 200 | 887 |
| `filterBy`에 `status` 키 자체 생략 | 200 | 895 |
| `status:null` | 200 | 895 |
| `status:"CLOSED"` | 200 (GraphQL 레벨 에러) | `ActivityStatus` enum에 `CLOSED` 없음 — 유효하지 않은 값 |

**결론**:
1. `status`는 무시되는 파라미터가 아니다 — `OPEN`을 명시하면 895→887로 **8건이 실제로 걸러진다**(약 0.9%). 이 8건이 무엇인지는 미확인이나, "마감된 공고"가 걸러지는 게 아님은 이미 확인됨(§2 참조) — 아마 신고/삭제 대기 등 컨텐츠 상태로 추정.
2. `status` 키를 생략하거나 `null`을 넘기면 필터 없이 더 포괄적인 결과(895)를 얻는다.
3. `ActivityStatus` enum은 `CLOSED`를 값으로 갖지 않는다 — 즉 이 필드는 "모집마감 여부"가 아니라 **공고 자체의 게시 상태**(정상/삭제 등)를 나타내는 것으로 보인다. **PROMPT 2 이후 실제 수집기는 `status` 키를 생략(또는 null)해서 더 포괄적인 결과를 받아야 한다.**

## 2. `status:"OPEN"`이 "모집 중"을 의미하지 않음 — 과거 마감 공고도 반환됨

2020-03 범위 조회에서 `status:"OPEN"`을 걸어도 `recruitCloseAt`이 이미 2020-03에 지난(2026년 기준 6년 전 마감) 공고가 정상적으로 반환됨. 즉 **"OPEN"은 "현재 지원 가능"이 아니라 "정상 게시 상태(비삭제)"를 의미하는 것으로 잠정 결론**. 이는 PROMPT 0 C(과거분 접근성)의 핵심 질문에 대한 긍정적 근거 — 마감된 과거 공고가 캘린더 API로 조회 가능함을 뜻한다.

## 3. `from`/`to` 범위 파라미터

- `CalendarScreen_ActivityCalendarEntries.variables.from/to`: epoch milliseconds, UTC 기준. 월 단위 조회 시 그 달의 1일 00:00~말일 23:00(UTC)를 넣으면 해당 월의 모든 날짜 버킷(28~31개)이 정확히 반환됨 — 날짜 경계 자체는 신뢰 가능.
- `CalendarScreen_Activities.variables.rangeBy`는 `recruitStartAt`과 `recruitCloseAt` 두 개의 별도 범위를 동시에 받는다. 2026-08 테스트에서 `totalCount=1681`이 나왔는데 이는 `CalendarScreen_ActivityCalendarEntries`의 start측 합계(326)와 직접 비교 불가 — **두 range 조건이 AND/OR 중 무엇으로 결합되는지 미확정**. 실제 수집기 구현 전에 별도 스키마 introspection 또는 단일 range만 채운 요청으로 재검증 필요 (미확정 항목으로 이관).

## 4. 2019년 recruit(채용) 카테고리 데이터 사실상 부재 — 최우선 결정 필요

`activityTypeIDs=["5"]`(채용)로 2019년 1/3/6/9/12월을 조회한 결과:

| 월 | recruit(5) totalCount | activity(1) totalCount |
|---|---|---|
| 2019-01 | 0 | 512 |
| 2019-03 | 0 | 496 |
| 2019-06 | 1 | 523 |
| 2019-09 | 0 | 457 |
| 2019-12 | 23 | 331 |

`activityType=1`(대외활동/공모전류)은 2019년 내내 정상적으로 존재하는 반면, RQ1·RQ2가 다루는 `recruit`(채용) 카테고리는 **2019년 한 해 동안 사실상 데이터가 없다**(12월에야 23건). 이는 API 접근성 문제가 아니라 **링커리어의 "채용" 서비스 자체가 2019년에는 초기/미가동 단계였을 가능성**을 강하게 시사한다.

**→ RQ1/RQ2 분석 구간을 "2019-2026 그대로"로 확정하면 2019년 구간이 사실상 공백(coverage insufficient)이 되어 분석에 왜곡을 줄 수 있음. PROMPT 4(분석구간 확정) 이전에라도 사람 확인이 필요한 최우선 사항으로 격상 권고.**
