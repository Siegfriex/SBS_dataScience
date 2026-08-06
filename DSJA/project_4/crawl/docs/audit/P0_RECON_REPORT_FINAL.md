# P0 정찰 최종 보고 (RECON_20260806_01)

- 담당: Agent 1 (인세인서치 에이전트) — 브라우저리스 HTTP/GraphQL 실측 전담
- 기준일: 2026-08-06
- 원칙: 이 문서에 등재된 수치는 전부 실제 HTTP 요청으로 재현된 결과다. 추정은 "추정"으로 명시한다.

---

## 0. 요약 — 사람 결정이 필요한 항목 (우선순위순)

| # | 항목 | 긴급도 | 요지 |
|---|---|---|---|
| 1 | **2019년 recruit(채용) 카테고리 데이터 사실상 부재** | 🔴 최우선 | 2019년 1·3·6·9월 recruit totalCount=0~1. activity(공모전 등)는 정상 존재. RQ1·RQ2 분석 시작연도 재검토 필요 |
| 2 | 표본 35건 중 35건(100%) 외부 ATS 링크 | 🔴 | 링커리어 자체 자격요건 원문은 짧은 요약(49~1262자)뿐, 상세 지원은 전부 외부 사이트. RQ2 표본이 예상보다 크게 줄어들 수 있음 |
| 3 | 캘린더 API 일(day) 단위 6건 하드캡 | 🔴 | 고빈도 시기(월 100+건/일)는 단순 조회로 14%만 회수됨. 수집기가 하루totalCount>6일 때 반드시 추가 페이지네이션해야 함 |
| 4 | `/list/recruit` 페이지네이션의 깊이 한계 | 🟠 | 2023-11-17까지만 도달(약 2,782건). 2019~2023-11 구간 백필엔 부적합, 최근 구간 교차검증용으로만 사용 |
| 5 | recruitStartAt/recruitCloseAt 이중 range 결합 방식 미확정 | 🟠 | totalCount API와 entries API 합계가 불일치, AND/OR 결합 방식 재검증 필요 |
| 6 | 이용약관 "명시적 허용" 판정 정정 필요 | 🟡 | 조건부 허용(서버부하 유발 시 금지)이지 전면 허용 조항이 아님 — `SOURCE_POLICY_DECISION.md` 참조 |

---

## 1. 수집 방식 권고 (최종 확정)

브라우저(Playwright) 없이 **순수 HTTP만으로 목록·상세 전량 수집이 가능함을 실증**했다.

### 우선순위 재정렬 (사용자 지시 반영, Agent 1 실측으로 확정)

1. **Calendar APQ 날짜범위 조회** — `CalendarScreen_ActivityCalendarEntries` (persisted GET), 월 단위로 순회. `status` 필터는 **생략**(§APQ_DATE_SEMANTICS.md 참조 — `OPEN` 명시 시 8건/887건 정도 손실).
2. **일자별 totalCount 확인 후 필요시 추가 페이지네이션** — `start.totalCount`/`end.totalCount` > 6인 날짜만 `nodePagination.page`를 2,3...로 늘려 완전 회수. (§APQ_PAGINATION_AUDIT.csv)
3. **`CalendarScreen_Activities`(totalCount)로 완전성 교차검증** — 단, range 결합 의미론 재검증 전까지는 참고치로만 사용.
4. **상세 SSR `__NEXT_DATA__` 회수** — `https://linkareer.com/activity/{id}` 단일 GET으로 구조화 필드 + 본문(ActivityText, Apollo 캐시)까지 한 번에 확보. 추가 요청 불필요.
5. **`/list/recruit?page=N` 은 최근 ~2,782건(2023-11 이후)의 교차검증/누락탐지 보조 수단으로만 사용** — 주 수집경로 아님.
6. **APQ 누락·삭제 공고에 한해서만 ID 순차열거 사용** — coverage 감사 및 생존율(survival rate) 추정 목적.
7. **Wayback CDX는 원문 수집이 아니라 "생존편향 감사"(과거엔 존재했으나 현재 삭제된 공고 규모 추정) 전용으로 사용.**

### 전송계층 실측 근거

- `curl_cffi(impersonate='chrome')` + `Referer: https://linkareer.com/` 헤더만으로 목록(APQ)·상세(SSR HTML) 전부 200 정상 수신. **Playwright/브라우저 자동화 불필요.**
- Persisted Query라 GraphQL 쿼리 본문 없이 `operationName`+`variables`+`extensions.persistedQuery.sha256Hash`만으로 GET 재현됨.

---

## 2. 페이지 구조 (SSR/CSR, 필드 위치)

| 항목 | 결과 |
|---|---|
| 캘린더 목록 페이지(`/calendar`) | Next.js CSR — `pageProps` 비어있음, 목록은 전부 클라이언트 사이드 APQ 호출로 로드 |
| 상세 페이지(`/activity/{id}`) | **완전 SSR** — `__NEXT_DATA__.props.pageProps.data.activityData.activity`에 전 구조화 필드 내장 |
| 본문(담당업무/자격요건/우대사항) | 별도 위치: `__NEXT_DATA__.props.pageProps.__APOLLO_STATE__["ActivityText:{id}"].text` (원문 HTML, 시맨틱 태그 없이 `<div>라벨</div><p>내용</p>` 반복 패턴) |
| `/list/recruit` (SEO 리스트) | 완전 SSR, `pageProps.activityItems`(id/제목/이미지만, thin) — `?page=N`으로 페이지네이션, 20건/페이지, 최대 140페이지(≈2,782건) |

### 필드 매핑 (DATASET_SPEC §2 요구 항목 대응)

| 요구 필드 | 실제 소스 |
|---|---|
| 제목 | `activity.title` |
| 기업명 | `activity.organizationName` (구조화, `company` 필드도 별도 존재하나 null인 경우 다수) |
| 게시일 | `activity.createdAt` (epoch ms) |
| 마감일 | `activity.recruitCloseAt` |
| **채용유형** | `activity.jobTypes`(공고 전체), `activity.duties[].jobType`(포지션별) — **저자가 직접 태깅한 구조화 enum**(`INTERN`/`NEW`/`EXPERIENCED`/`CONTRACT`). postingKind/careerClass 판정 1순위 근거로 승격 권고 |
| 경력요건/학력 | `activity.educationTypes`, `activity.skills`, `activity.targets` — **존재하나 실제로는 대부분 빈 배열**(§4 참조), 실질 내용은 ActivityText 본문에 자연어로만 존재하는 경우가 많음 |
| 담당업무/필수요건/우대요건 | `ActivityText.text` (원문 HTML) — 섹션 헤더가 시맨틱 마크업이 아니라 스타일 속성 기반 `<div>` 텍스트라 정규식/DOM 순서 기반 파싱 필요 |
| 이미지(포스터) | `activity.files[]` (`type.name`: "포스터"/"썸네일"/"로고") |
| 담당자 연락처 | `activity.managerName/managerPhoneNumber/managerEmail` — **평문 노출 확인, 마스킹 필수** |

---

## 3. 과거분 접근성 (PROMPT 0 원래 C항목)

- id는 연도에 따라 대체로 단조 증가: 2020(~34~36천) → 2021(~57~58천) → 2022(~80~82천) → 2023(~118~123천) → 2024(~171천) → 2025(~227천) → 2026(~306~340천). **id 순차성 가설과 정합** — id-date 보간 모델(선형)이 실용적일 것으로 판단됨.
- 2020-03 등 마감된 지 오래된 과거 공고도 캘린더 APQ로 **정상 조회 가능** — 삭제되지 않는 한 API 레벨에서 생존.
- **2019년은 recruit 카테고리 자체가 사실상 비어있음**(§0-1 참조) — 이는 "생존편향"이 아니라 "애초에 그 시기엔 해당 카테고리로 데이터가 거의 없었다"는 다른 종류의 문제. PROMPT 4의 `coverageStatus` 판정 로직(`survivalRate` 기반)만으로는 이 원인을 구분하지 못하므로, monthlyCoverageAudit에 원인 구분 플래그 추가를 권고(§6 스키마 변경 참조).

---

## 4. 표본 성격 — 구조화 필드 커버리지 (n=35, 2020~2026년 3월 표본)

전체 데이터: `DETAIL_FIELD_COVERAGE.csv`, 집계: `EXTERNAL_ATS_COVERAGE.csv`

| 지표 | 값 |
|---|---|
| 표본 수 | 35건 (연도별 5건 × 7개년, 2019 제외—표본 자체가 없었음) |
| `jobTypes` 채워짐 | 35/35 (100%) |
| 외부 ATS 지원(`isExternalApply`) | **35/35 (100%)** |
| `ActivityText` 존재 | 35/35 (100%, 단 길이 편차 큼: 49~1262자) |
| `bodyTextLength < 120자` (validPosting 기준 미달) | 5/35 (14.3%) |
| `skills`/`targets`/`benefits` 실제 채워짐 | 표본 내 0건 — 필드는 존재하나 사실상 미사용 |

**해석**: 이 표본은 극소표본(n=35)이라 통계적 확정치가 아니라 **PROMPT 0 D(표본 성격 조사)를 본격 진행하기 전의 파일럿 시그널**이다. 그럼에도 "외부 ATS 100%"는 우연이라 보기 어려울 만큼 일관적이라, RQ2·NCS 매핑 분모가 RQ1 분모보다 상당히 작아질 것을 강하게 시사한다. **정식 D항목(무작위 100건 이상, 층화추출)을 PROMPT 2 파일럿 단계에서 반드시 재확인해야 한다.**

---

## 5. 접근 허용성 — 요약 (전문은 `SOURCE_POLICY_DECISION.md`)

- robots.txt: calendar/activity/list 경로 차단 없음. STEM(학습) 경로만 차단.
- 이용약관: 크롤링 금지 조항은 STEM 콘텐츠 저작권 보호 맥락. 자동접속 금지는 "서버 부하·서비스 방해" 조건부. **"명시적 전면 허용"이 아니라 "상식적 속도 준수 시 조건부 허용"으로 정정.**

---

## 6. 스키마 변경 (사용자 지시 반영, 실증으로 뒷받침됨)

다음은 이번 실측 결과가 직접 근거가 되어 `P4_DATASET_SPEC_v2.0.md` / `P4_WAREHOUSE_DDL_v2.0.sql`에 반영 완료된 변경사항이다 (상세는 해당 문서의 변경 이력 참조):

1. **분모 4분리**: `postingEligibleFlag` / `rq1EligibleFlag` / `rq2EligibleFlag` / `ncsEligibleFlag` — 외부 ATS 전용 공고를 RQ1에서는 살리고 RQ2·NCS에서는 별도 제외율로 보고하기 위함. 근거: §4의 "외부 ATS 100%" 실측.
2. **외부 ATS 필드**: `externalApplyUrl`, `externalAtsDomain`, `externalDetailOnlyFlag`, `linkareerBodyAvailableFlag`, `rq2ExclusionReason` — 근거: `EXTERNAL_ATS_COVERAGE.csv`.
3. **jobTypes/duties[].jobType을 postingKind/careerClass 판정 1순위로 승격** — 단, 골드셋 검증 없이 무조건 정답 취급하지 않는다(사용자 지시). 검증 절차는 기존 `qa.goldSample`/`qa.evalRun` 게이트 체계를 그대로 사용.
4. **`raw.queryRegistry` 신설** — APQ 해시가 프런트엔드 배포로 바뀔 수 있으므로 수집기가 하드코딩 대신 레지스트리를 참조하게 함. 필드: `operationName`, `sha256Hash`, `transportType`, `httpMethod`, `frontendBuildId`, `discoveredAt`, `lastVerifiedAt`, `responseSchemaVersion`, `activeFlag`, `verificationStatus`.

---

## 7. 미확정 항목 (다음 단계로 이관)

| 항목 | 상태 |
|---|---|
| 월별 완전성(pagination 전수) — 96개월 전체 | 미확정 (2026-08 1개월만 심층 검증) |
| recruitStartAt/recruitCloseAt range 결합 의미론 | 미확정 |
| APQ 해시 장기 안정성(프런트 배포 시 변경 여부) | 미확정 — `queryRegistry.lastVerifiedAt`으로 상시 모니터링 필요 |
| Wayback CDX 생존편향 규모 | 미착수 |
| NCS 원천(공공데이터포털 API) 필드 확인 | 미착수 |
| D항목 정식 표본(층화 100건+) | 미착수 — 이번 §4는 파일럿 시그널일 뿐 |

---

## 8. 핸드오프

`releases/RECON_20260806_01/HANDOFF.json`, `CHECKSUMS.sha256` 참조.
