# APQ recruitStartAt/recruitCloseAt range 결합 의미론 — 확정

- 기준일: 2026-08-06 / 테스트: `CalendarScreen_Activities` totalCount, 2021-03(689~949 규모 known-complete 월) 및 2019-2027 wide window 대조

## 결론: OR(합집합)

| 테스트 | rangeBy 구성 | totalCount |
|---|---|---|
| A | recruitStartAt=2021-03만 | 692 |
| B | recruitCloseAt=2021-03만 | 689 |
| C | 둘 다 2021-03(원래 관측치) | 949 |
| D | recruitStartAt=2021-03(좁음), recruitCloseAt=2019~2027(넓음) | 126,902 |
| E | recruitStartAt=2019~2027(넓음), recruitCloseAt=2021-03(좁음) | 126,910 |
| F | 둘 다 2019~2027(넓음) | 126,914 |

**AND라면** D는 "recruitCloseAt 조건이 사실상 무제약이므로 recruitStartAt 조건(692)과 같아야" 하지만 실제로는 126,902(F와 거의 동일)로 폭증했다. 이는 **한쪽이 무제약(wide)이면 그 자체로 전체를 반환**하는 OR 패턴과 정확히 일치한다. C(949)도 692·689 각각보다 크므로(합집합 특성) AND(교집합, 반드시 둘 중 작은 값 이하)와 모순되고 OR과 일치한다.

## 실무 함의

1. `CalendarScreen_Activities.totalCount`는 "이번 달에 시작 OR 마감된 공고 수(합집합)"다. `CalendarScreen_ActivityCalendarEntries`의 start-day-bucket 합계(교집합적 개념이 아니라 "이번 달에 시작한 공고"만 센 것)와 **직접 비교할 근거가 없다** — 애초에 다른 것을 세고 있었다.
2. **completeness 판정은 totalCount 대조가 아니라, 이미 구현된 대로 "각 (날짜,side) bucket이 자기 자신의 totalCount에 도달했는가"를 기준으로 유지한다.** 이번 실측으로 이 기준의 타당성이 재확인됐다 — CRAWL_20260806_02/03의 `complete` 판정 로직은 이미 이 옳은 기준을 쓰고 있었으므로 재작업 불필요.
3. 한 달 안에 시작하고 마감한 공고는 start-bucket과 end-bucket 양쪽에 나타나므로, `distinct_ids`(중복제거 후)가 두 bucket totalCount 합계(`expected`)보다 작게 나오는 것은 **버그가 아니라 정상**이다.

## 다음 단계

`raw.queryRegistry`의 `CalendarScreen_Activities` 항목에 이 OR 의미론을 note로 반영 완료(`query_registry.yaml`). Agent 3 계약의 range 결합 관련 미확정 이슈는 이걸로 해소 — `AGENT1_TO_AGENT3_ISSUES.json`에서 해당 항목을 resolved로 갱신.
