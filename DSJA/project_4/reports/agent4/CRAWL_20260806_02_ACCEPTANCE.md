# CRAWL_20260806_02 독립 Acceptance Audit

- agentId: `P4-A4-NCS`
- agentName: `P4 NCS Source & Duty-Level Mapping Engineer`
- 감사 대상: `CRAWL_20260806_02` (origin/agent/p4-crawl-release-v2 @ `825ba03d0a7c46880e9aeba86078eb750a8a36b5`)
- 감사 방법: `git archive`로 release 트리를 스크래치패드에 추출해 독립 재계산. `DSJA/project_4/crawl/**`는 이 worktree에서 전혀 수정하지 않음.
- statusCode: **PARTIALLY_READY**

## Executive verdict

| 항목 | 판정 |
|---|---|
| Source adapter input | **ACCEPT** |
| NCS ncsUnit source | **ACCEPT** |
| Full Linkareer corpus | **REJECT** |
| RQ2-B final mapping | **BLOCKED_BY_DUTY_INPUT_AND_GOLD** |

체크섬 실패가 하나도 없으므로 `RELEASE_INTEGRITY_FAILED`는 아니다. 다만 아래 3.4/3.6에서 재계산으로 드러난 두 건의 실질적 결함(§3.4 complete월 mismatch, §3.6 lineage 부재)이 있어 "완전 통과"는 아니다.

---

## 3.1 Checksum 검증

```text
listedFiles   = 14
verifiedFiles = 14
failedFiles   = 0
missingFiles  = 0
unlistedFiles = 0
```

`sha256sum -c` 전체 PASS. `CHECKSUMS.sha256` 자신은 관례상 목록에서 제외(이상 아님). `asset_manifest.jsonl`의 해시는 빈 문자열의 SHA-256(`e3b0c44...`)과 일치 — 파일이 의도적으로 0바이트임을 의미하며 손상이 아니다.

## 3.2 HANDOFF 검증

필수 필드(`manifest_paths`, `coverage_path`, `checksum_path`) 모두 비어있지 않음. `release_id`/`contract_version` 일치.

**발견 사항 — `HANDOFF_HEAD_COMMIT_EMPTY`**: `head_commit` 필드값이 빈 문자열(`""`)이다. 실제 `origin/agent/p4-crawl-release-v2`의 HEAD는 `825ba03d0a7c46880e9aeba86078eb750a8a36b5`(`release(crawl): publish CRAWL_20260806_02 ...` 커밋)이다. 체크섬/필수경로 실패는 아니므로 integrity failure로 격상하지 않지만, 이 필드가 비어 있으면 소비자가 브랜치 HEAD를 별도로 조회하지 않는 한 release 재현성(reproducibility)을 검증할 수 없다 — 다음 release에서 수정 권고.

## 3.3 Coverage 재계산 (`monthly_coverage.csv`에서 직접)

```text
totalRows              = 85
targetMonths2020to2026 = 79   (missing = 0)
completeMonths         = 11
partialMonths          = 1    (2026-08, target window 밖, 현재 진행 중인 월)
unverifiedMonths       = 68
insufficientMonths     = 5    (2019, platformPreLaunch)
duplicatePeriodMonths  = 0
```

85 = 79(target, complete+unverified) + 5(2019) + 1(2026-08). Agent 1 보고값(target=79, complete=11, unverified=68, 2019 insufficient=5)과 정확히 일치 — 파일에서 재계산한 결과다.

## 3.4 Complete월 ID 수 검증 — **불일치 발견**

11개 complete 월의 `returnedDistinctCount` 합계(`sumOfMonthlyDistinctIds`) = **11,825** (재계산 확인, Agent 1 수치와 일치).

그러나 `globalDistinctIdsAcrossCompleteMonths`는 **계산 불가**로 판정한다: release는 월별 `firstPostingId`/`lastPostingId` 범위만 제공하고 실제 ID 목록을 제공하지 않는다. 이 범위들이 월 간에 심하게 겹친다(예: `2020-02`의 29589–38086이 `2020-01`의 24563–40878 안에 완전히 포함). 따라서 11,825를 "월별 합계"로만 취급해야 하며, 이것이 진짜 cross-month dedup된 전역 distinct count와 같다고 가정할 수 없다.

**추가 발견 — `COMPLETE_MONTH_EXPECTED_VS_RETURNED_MISMATCH`**: 11개 complete 월 전부에서 `returnedDistinctCount < expectedTotalCount`다(차이 10~611건, 최대 약 24%).

| periodMonth | expectedTotalCount | returnedDistinctCount | difference | paginationCompleteFlag |
|---|---|---|---|---|
| 2020-01 | 264 | 254 | 10 | True |
| 2020-02 | 1234 | 896 | 338 | True |
| 2020-04 | 1699 | 1268 | 431 | True |
| 2020-05 | 1422 | 1105 | 317 | True |
| 2020-06 | 1676 | 1205 | 471 | True |
| 2021-01 | 1320 | 918 | 402 | True |
| 2021-02 | 1125 | 815 | 310 | True |
| 2021-03 | 1381 | 949 | 432 | True |
| 2021-04 | 1228 | 882 | 346 | True |
| 2022-01 | 2103 | 1592 | 511 | True |
| 2022-02 | 2552 | 1941 | 611 | True |

각 행의 자유서술 `note`는 "n/m distinct ids collected == expected"라고 주장하지만, 나열된 숫자 자체가 이 주장과 모순된다(n≠m). `discoveredCount == returnedDistinctCount`는 모든 행에서 성립하므로 dedup 로직 자체는 일관적이다 — 문제는 수집된 집합과 `expectedTotalCount` 사이의 간극이다. Agent 1에게 `expectedTotalCount`가 실제 수집 범위(recruit 카테고리)와 다른 쿼리 스코프(예: 다른 activityType 포함)를 반영하는 것인지 확인이 필요하다. 이 확인 전까지는 "complete" 라벨을 coverage 주장의 분모로 그대로 신뢰하지 않는 것을 권고한다.

## 3.5 n=126 층화표본 재계산

```text
sampleCount = 126
detailSuccessCount / detailFailureCount = NOT_DETERMINABLE_FROM_ARTIFACT
  (이 파일은 이미 성공한 126건의 상세수집 결과만 담고 있으며, 실패 시도 기록이 없음)
```

| metric | numerator | denominator | rate | definition | sourceColumn |
|---|---|---|---|---|---|
| activityTextAvailabilityRate | 126 | 126 | 1.0000 | hasActivityText=true 비율 | hasActivityText |
| externalApplyShare | 125 | 126 | 0.9921 | externalApplyFlag=true 비율 | externalApplyFlag |
| externalDetailOnlyShare | 24 | 126 | 0.1905 | externalDetailOnlyFlag=true 비율(상세페이지가 외부로 완전 리다이렉트, 본문 없음) | externalDetailOnlyFlag |
| rq1EligibilityRate | 126 | 126 | 1.0000 | rq1EligibleFlag=true 비율 | rq1EligibleFlag |
| rq2EligibilityRate | 102 | 126 | 0.8095 | rq2EligibleFlag=true 비율 | rq2EligibleFlag |
| ncsEligibilityRate | 27 | 126 | 0.2143 | ncsEligibleFlag=true 비율 | ncsEligibleFlag |
| jobTypeConflictRate | 1 | 126 | 0.0079 | jobTypeConflictFlag=true 비율 | jobTypeConflictFlag |
| imageOcrRoutingRate | 113 | 126 | 0.8968 | activityTextEmbeddedImageFlag=true 비율 | activityTextEmbeddedImageFlag |
| posterFileShare | 0 | 126 | 0.0000 | hasPosterFile=true 비율 | hasPosterFile |
| activityTextEmbeddedImageShare | 113 | 126 | 0.8968 | imageOcrRoutingRate와 현재 스키마상 동일 지표/컬럼 — 구분되는 분모가 없음. Agent 1/3에 의도된 차이가 있는지 확인 필요 | activityTextEmbeddedImageFlag |

전부 HANDOFF.json의 `additional_metrics`/top-level rate와 반올림 오차 내에서 일치 — 파일에서 직접 재계산한 결과다.

**확인됨 — `externalApplyFlag ≠ externalDetailOnlyFlag`**:

| | externalDetailOnlyFlag=False | externalDetailOnlyFlag=True |
|---|---|---|
| externalApplyFlag=False | 1 | 0 |
| externalApplyFlag=True | 101 | 24 |

101/126건은 외부 지원 URL이 있으면서도 자체 상세 본문(RQ2 대상)을 갖는다. `rq2EligibleFlag`는 정확히 `externalDetailOnlyFlag=true`인 24건에서만 False이고 나머지 102건은 True — 외부 지원 URL의 유무가 아니라 "상세페이지 자체가 외부로만 리다이렉트되는지"가 RQ2 제외 기준임을 확인.

## 3.6 Raw lineage 검증

`crawl_manifest.jsonl` = 6행. 각 행 정체:

1. artifact-level — NCS CSV 다운로드
2. artifact-level — n=126 파생 요약 번들(raw HTML 아님)
3~5. record-level — PII 마스킹된 단건 fixture 3건(CRAWL_20260806_01 이월)
6. request-level — GraphQL calendar index 샘플(CRAWL_20260806_01 이월)

전체 corpus(수천 건의 공고)에 대한 record-level per-posting manifest(‎`sourceUrl`/`rawPath`/`rawSha256`/`httpStatus`/`fetchedAt`/`collectorVersion`/`crawlRunId`/`sourcePostingId`)는 존재하지 않는다.

**판정: `FULL_CORPUS_LINEAGE_NOT_READY`** — Agent 1의 HANDOFF `known_gaps` 자체 공개 내용과 일치하며, 이번에 파일을 직접 열어 독립적으로 재확인했다.

## 3.7 NCS 파일 검증 (`data/ncs/ncsUnit_20260806.csv`)

```text
rows                  = 13,442  (헤더 제외, Agent 1 보고와 일치 — 헤더 포함 라인수 13,443과 혼동하지 않음)
columns               = 4  (분류번호, 명칭, 수준, 훈련시간)
uniqueNcsUnitCodes     = 13,442
duplicateNcsUnitCodes  = 0
nullNcsLevel           = 0
invalidNcsLevel        = 0  (전부 1~8 범위)
sourceVersion          = 2026-02-20 (ncs_manifest.jsonl) / 원자료 기준일 20251231 (crawl_manifest.jsonl)
```

level1to8Distribution:

| level | count |
|---|---|
| 1 | 4 |
| 2 | 1,411 |
| 3 | 3,315 |
| 4 | 3,318 |
| 5 | 3,577 |
| 6 | 1,278 |
| 7 | 475 |
| 8 | 64 |

합계 13,442로 총 행수와 일치. `ncs_manifest.jsonl`의 `levelDistribution`과도 정확히 일치.

**발견 — missingHierarchyRate**: 원본 CSV는 leaf 능력단위 코드(`분류번호`, 예: `0101010101_17v2`)와 그 이름(`명칭`)만 갖고 있다. major/middle/minor/sub의 **코드**는 10자리 코드 접두부(2+2+2+2+2자리 + `_17v2` 버전 접미부)를 파싱해 추출할 수 있으나, major/middle/minor/sub의 **이름**은 이 파일 어디에도 없다 — 별도의 NCS 분류체계 참조 테이블이 이번 release에 포함되어 있지 않다. Phase B 정규화 스키마에서 `majorName`/`middleName`/`minorName`/`subName`을 채우려면 이 참조 테이블을 별도로 확보해야 하며, 확보 전까지는 해당 name 필드를 null로 유지한다(허구 생성 금지).

## 3.8 NCS manifest 검증 (`ncs_manifest.jsonl`, 2행)

- Row 1 (능력단위, datasetId `15083321`): `recordCount=13,442`(파일과 일치), `sourceVersion=2026-02-20`, `license=공공저작물 자유이용허락 제1유형(출처표시)`, `redistributable=true`.
- Row 2 (KSA, datasetId `15157542`): `recordCount=null`, `accessMethod=restApi_keyRequired_NOT_CALLED`, `redistributable=null`, `status=NOT_INGESTED`.

→ `KSA_SOURCE_STATUS = UNVERIFIED` 표기가 정확함을 확인. 사람이 data.go.kr API 키를 등록해야 다음 단계 진행 가능.

---

## Recalculated release metrics 요약

| 지표 | Agent 1 보고 | 독립 재계산 | 일치 |
|---|---|---|---|
| target months | 79 | 79 | ✓ |
| complete months | 11 | 11 | ✓ |
| unverified months | 68 | 68 | ✓ |
| 2019 insufficient | 5 | 5 | ✓ |
| complete월 distinct ID 합계 | 11,825 | 11,825 (월별 합계로만 유효) | ✓ (단, global distinct 아님) |
| NCS rows | 13,442 | 13,442 | ✓ |
| NCS level distribution | (동일) | (동일) | ✓ |
| externalApplyShare | 0.992 | 0.9921 | ✓ |
| rq2EligibilityRate | 0.81 | 0.8095 | ✓ |
| ncsEligibilityRate | 0.214 | 0.2143 | ✓ |

## Git

- branch: `agent/p4-ncs-mapping-v2`
- worktree: `/home/sieg/projects-wsl/worktrees/p4-agent4`
- 감사 대상 커밋: `origin/agent/p4-crawl-release-v2@825ba03`
- cherry-pick된 canonical contract 커밋: `97f9c04`(vendor P4 contract v2.1.2), `2e69380`(publish Agent 3 handoffs) — 둘 다 clean cherry-pick, 충돌 없음

## Remaining blockers (Phase B 이후 RQ2-B 최종 매핑까지)

1. 전체 corpus record-level raw lineage 부재 (126-표본 파생요약 + 3개 fixture만 존재)
2. 68/79 target월 pagination 미검증
3. KSA 원천(15157542) 미수집 — 정밀 NCS 수행준거 매칭 불가
4. Agent 2 duty-level input 계약 아직 미수신
5. gold mapping label 전무 (목표 n=300, 미착수)
6. complete월 `expectedTotalCount` vs `returnedDistinctCount` 불일치 — Agent 1 확인 필요, 확인 전까지 "complete" 라벨을 coverage 주장의 근거로 그대로 사용하지 않을 것을 권고
7. NCS 계층 이름(major/middle/minor/subName) 참조 테이블 부재 — 코드만 파싱 가능, 이름은 별도 소스 필요

## Precision/coverage 상태

```text
precision        = NOT_EVALUATED
coverage          = NOT_EVALUATED
lowConfidenceShare = NOT_EVALUATED
```

실제 duty input과 gold label이 없으므로 어떤 fixture 점수도 empirical 성능으로 보고하지 않는다.
