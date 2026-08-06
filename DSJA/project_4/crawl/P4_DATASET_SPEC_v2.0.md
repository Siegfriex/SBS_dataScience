# P4 데이터셋·산출물 명세 (Dataset Spec)

- 버전: `v2.0.0` / 기준일: `2026-08-06`
- 준거: `P4_PROJECT_SSOT_v2.md`, `USER_REVIEW_DECISIONS.md`, `P4_WAREHOUSE_DDL_v2.0.sql`
- 목적: SSOT의 테이블 목록을 **실제 파일·타입·키·수락기준**까지 확정한다

---

## 0. SSOT v2에서 비어 있던 지점과 이 문서의 결정

| # | 공백 | 이 문서의 결정 |
|---|---|---|
| G1 | `validPosting`이 §15.1 수식에 쓰이지만 정의가 없다 | §2에 4조건으로 확정 |
| G2 | 링커리어 캘린더에는 공모전·대외활동·교육과정이 섞여 있는데 이를 배제하는 필드가 없다 | `postingKind` enum 신설, `recruit*`만 분모 |
| G3 | 재시작 가능한 수집 상태 테이블이 없다 | `raw.crawlFrontier` 신설 |
| G4 | "월별 coverage status 확정"이 게이트인데 담을 테이블이 없다 | `qa.monthlyCoverageAudit` 신설 |
| G5 | precision·F1 게이트를 재려면 골드셋이 필요한데 규격이 없다 | `qa.goldSample`, `qa.evalRun` + §6 표본 크기 |
| G6 | "모든 기사 수치가 manifest에서 파생"의 manifest 실체가 없다 | `qa.resultManifest` 신설 |
| G7 | 수행준거·KSA를 쓰겠다고 했으나 담을 테이블이 없다 | `ncs.ncsUnitElement` 신설 |
| G8 | dedup 판정 근거가 소실된다 | `core.postingDedupEdge` 신설 |
| G9 | 키 생성 규칙이 없어 재실행 시 행이 중복된다 | §3 결정적 키 규칙 |

`highDemandScore`는 UR13에 따라 컬럼만 두고 DDL에 `CHECK (highDemandScore IS NULL)`을 걸어 **물리적으로 채울 수 없게** 했다. 산식 확정 시 이 제약만 해제한다.

---

## 1. 스토리지 레이아웃

```text
data/
├─ raw/                              # 불변. 덮어쓰기·삭제 금지
│  ├─ linkareer/index/{yyyy}/{mm}/{sha256}.json.gz
│  ├─ linkareer/detail/{yyyy}/{mm}/{sha256}.html.gz     # 또는 .json.gz
│  ├─ linkareer/assets/{sha256[:2]}/{sha256}.{ext}
│  └─ ncs/{dataset}/{sourceVersion}/{originalFileName}
├─ manifests/
│  ├─ fetch_manifest.jsonl                              # 1요청 1줄, append only
│  ├─ asset_manifest.jsonl
│  └─ ncs_manifest.jsonl
├─ warehouse/p4.duckdb                                  # 정본 웨어하우스
├─ interim/
│  ├─ ocr/{assetSha256}.json
│  ├─ parsed/postingNormalized.parquet
│  ├─ parsed/postingTrack.parquet
│  ├─ parsed/postingSection.parquet
│  ├─ parsed/requirementFact.parquet
│  └─ dedup/dedupEdge.parquet
├─ gold/
│  ├─ careerLabels/gold_careerClass_v1.csv
│  ├─ careerLabels/gold_boundary_v1.csv
│  └─ ncsMappings/gold_ncsMapping_v1.csv
├─ processed/
│  ├─ careerLabel.parquet
│  └─ postingNcsMatch.parquet
└─ marts/
   ├─ postingAnalysisMart.parquet
   ├─ timeSeriesMart.parquet
   ├─ caseStudyRegistry.parquet
   └─ similarityPair.parquet          # 선택
```

`fetch_manifest.jsonl` 1줄 스키마:

```json
{"crawlRunId":"01J...","url":"https://...","entityType":"detail","discoveryRoute":"idEnumeration",
 "httpStatus":200,"fetchedAt":"2026-08-07T10:12:33+09:00","contentSha256":"...","bytes":48210,
 "rawPath":"data/raw/linkareer/detail/2024/03/ab12...html.gz","userAgent":"SBS-P4-Research-Bot/0.1",
 "elapsedMs":412,"collectorVersion":"0.3.1"}
```

**Git 정책**: `data/raw/**`, `data/warehouse/**`, `data/interim/**`은 `.gitignore`. `manifests/**`, `data/gold/**`, `data/marts/**.parquet`(≤50MB)는 커밋. 대용량은 해시로만 참조한다(SSOT §21).

---

## 2. `validPosting` 확정 정의

```text
validPosting = 1  ⟺  모두 참
  (a) postingKind ∈ {recruitIntern, recruitNewGrad, recruitExperienced, recruitUnknown}
  (b) postedAt IS NOT NULL AND postedAtSource ≠ 'unknown'
  (c) bodyTextLength ≥ 120
  (d) canonicalRecordFlag = TRUE
```

- (a)가 없으면 공모전·대외활동·교육과정이 분모에 섞여 `internPostingRate`가 통째로 왜곡된다. **RQ1의 최대 단일 위험**이며 `postingKind`는 반드시 골드셋으로 정확도를 잰다.
- (c)의 120자는 파일럿에서 재조정하되, 조정하면 `decisionLog`에 기록한다.
- `invalidReason`은 위 조건 위반 코드를 그대로 문자열로 남긴다: `kindNotRecruit`, `noPostedAt`, `bodyTooShort`, `nonCanonicalRepost`.

`postingKind` 판정 우선순위 (RECON_20260806_01 반영 — 링커리어 `activity.jobTypes`/`duties[].jobType`가 저자 태깅 구조화 enum임을 실측 확인, 최우선순위로 승격. 단 구조화 필드라는 이유만으로 무검증 정답 취급하지 않으며 골드셋으로 정확도를 검증한다):
1. **`activity.jobTypes` / `duties[].jobType`(INTERN/NEW/EXPERIENCED/CONTRACT) — 구조화 필드**
2. 상세 페이지의 채용유형 태그·필드가 명시적일 때 → 그 값
3. 제목·본문의 모집구분 문구(인턴/신입/경력/공모전/서포터즈/교육생)
4. 지원자격에 요구경력이 존재하면 채용 성격으로 가중
5. 판정 불가 → `recruitUnknown`이 아니라 `other`. **모르면 분모에 넣지 않는다**

> `recruitUnknown`은 "채용공고인 것은 확실하나 신입/인턴/경력 구분이 불명"에만 사용한다. 채용공고 여부 자체가 불명이면 `other`.

## 2.1 분모 4분리 (`postingEligibleFlag` / `rq1EligibleFlag` / `rq2EligibleFlag` / `ncsEligibleFlag`)

RECON_20260806_01(`docs/audit/P0_RECON_REPORT_FINAL.md`)에서 표본 35건 중 35건(100%)이 지원 절차 전부를 외부 ATS(사람인·잡코리아·인크루트·기업 자체 채용사이트 등)로 넘기고, 링커리어 자체 본문(`ActivityText`)은 49~1262자 수준의 짧은 요약뿐임을 실측했다. `validPosting` 하나로 분모를 묶으면 본문 보존 여부에 따라 RQ1의 신입·인턴 비율까지 왜곡되므로 다음 네 변수로 분리한다.

```text
postingEligibleFlag = 채용공고임이 확인됨 AND 게시일 존재 AND 기본 메타데이터(기업명 등) 존재

rq1EligibleFlag = postingEligibleFlag
                  AND 채용형태(jobTypes 등)가 판정 가능함
                  AND canonical 공고 여부가 결정됨(90일 dedup 판정 완료)

rq2EligibleFlag = postingEligibleFlag
                  AND 필수요건 또는 우대요건 경계가 판정 가능한 원문 존재
                  AND 트랙 단위 분리 가능

ncsEligibleFlag = postingEligibleFlag
                  AND 담당업무 문장 존재
                  AND NCS 매핑 가능한 최소 텍스트 존재
```

**분석 분모는 반드시 다음 뷰를 통해서만 센다** (DDL 반영 완료):

- RQ1 분모 = `mart.vValidPostingMonthly`(내부적으로 `rq1EligibleFlag=1` 사용) 기준 distinct `canonicalPostingId`
- RQ2 분모 = `mart.vRq2Eligible`(`rq2EligibleFlag=1`) 기준 eligible `trackId`
- NCS 분석 분모 = `mart.vNcsEligible`(`ncsEligibleFlag=1`) 기준 eligible `trackId`

외부 ATS 전용 공고는 RQ1에는 남기되(채용형태·게시일·기업명만으로 충분), RQ2·NCS 분석에서는 `rq2ExclusionReason='externalAtsBodyUnavailable'`로 별도 제외율을 반드시 보고한다. 외부 사이트는 UR01(원천을 링커리어·NCS로 고정)에 따라 **따라가서 수집하지 않는다** — `externalApplyUrl`/`externalAtsDomain`은 링크만 보존한다.

## 2.2 APQ 쿼리 레지스트리 (`raw.queryRegistry`)

링커리어 목록 API는 Apollo Persisted Query(GET, `operationName`+`variables`+`extensions.persistedQuery.sha256Hash`)로 동작하며, 이 해시는 프런트엔드 배포마다 바뀔 수 있다(RECON_20260806_01). 수집기는 해시를 코드에 하드코딩하지 않고 `raw.queryRegistry`에서 조회하며, 주기적으로 `verificationStatus`를 갱신해 해시 만료를 감지한다.

---

## 3. 결정적 키 규칙 (재실행 멱등성)

| 키 | 생성식 |
|---|---|
| `postingId` | `'lk_' + sha1(sourceName + '|' + sourcePostingId)[:16]` |
| `rawPostingId` | `sha1(sourceName + '|' + sourcePostingId + '|' + rawSha256)[:20]` |
| `trackId` | `postingId + '#t' + zfill(trackIndex,2)` |
| `sectionId` | `trackId + '#s' + zfill(sectionOrder,2)` |
| `requirementId` | `sha1(sectionId + '|' + requirementType + '|' + normalize(evidenceText))[:20]` |
| `assetId` | `sha1(assetSha256)[:20]` |
| `ocrId` | `sha1(assetSha256 + '|' + ocrEngine + '|' + ocrModel + '|' + ocrVersion)[:20]` |
| `matchId` | `sha1(trackId + '|' + ncsUnitCode + '|' + mappingBasis + '|' + sha1(evidenceText)[:8])[:20]` |
| `duplicateGroupId` | `'dg_' + sha1(min(정렬된 그룹 postingId 목록))[:16]` |
| `companyKey` | `'co_' + sha1(normalizeCompany(companyNameRaw))[:12]` |
| `metricId` | `sha1(metricName + '|' + cohortType + '|' + periodLabel + '|' + jobCode + '|' + dedupApplied)[:20]` |

`normalize()`: NFKC → 소문자 → 연속공백 1개 → 앞뒤 공백 제거 → 이모지·제어문자 제거.
`normalizeCompany()`: 위 + `주식회사|㈜|(주)|inc|corp|co\.,?\s?ltd` 제거.

UPSERT는 항상 `INSERT ... ON CONFLICT DO UPDATE`. 같은 입력을 두 번 돌려도 행 수가 변하지 않아야 하고, 이걸 통합테스트로 강제한다.

---

## 4. 버전 컬럼 규약

| 컬럼 | 언제 올리는가 |
|---|---|
| `collectorVersion` | 수집 로직·셀렉터·요청 방식 변경 |
| `parseVersion` | 섹션 분리·트랙 분리·본문 정규화 변경 |
| `extractorVersion` | requirementFact 추출 규칙 변경 |
| `labelVersion` | careerClass·internAccessClass 규칙 변경 |
| `ncsMapVersion` | 매핑 우선순위·사전·임베딩 모델 변경 |
| `dedupVersion` | 90일 판정 임계값 변경 |
| `dataVersion` | 위 중 하나라도 변경되면 `YYYYMMDD.n`으로 갱신 |

**기사 숫자는 하나의 `dataVersion`에서만 나온다.** 버전 섞인 마트로 그린 그래프는 폐기한다.

---

## 5. NCS 원천 조달

| 대상 | 조달 경로 | 채우는 테이블 |
|---|---|---|
| 능력단위코드·명칭·**수준(1~8)**·훈련시간 | 공공데이터포털 「한국산업인력공단_국가직무능력표준 정보」 파일데이터. 분류번호/명칭/수준/훈련시간 4종, 약 1.3만 건 | `ncs.ncsUnit` |
| 대·중·소·세분류 계층 | 「NCS 기준정보 조회」 API (분류 7개 오퍼레이션) | `ncs.ncsUnit` 계층 컬럼 |
| 능력단위요소·KSA·요소 레벨 | 「고교직업교육과정 정보 서비스」 API (능력단위요소번호·설명·KSA명·KSA설명·능력단위레벨 제공) | `ncs.ncsUnitElement` |
| 능력단위 정의·수준 교차검증 | 「NCS 관련 정보 서비스」 API | `ncs.ncsUnit` 검증 |
| 학습모듈 과업 문장 | ncs.go.kr 학습모듈 파일 검색 | `ncs.ncsLearningModule` |

**라이선스 주의**: NCS 학습모듈은 출처 표시 후 교육 목적 활용은 가능하지만, 내부에 공단이 저작재산권을 갖지 않는 도표·사진이 포함되어 변형·복제·배포에 원작자 동의가 필요하다. 따라서 학습모듈은 **로컬 참조·매핑 근거 추출 전용**으로 쓰고 `redistributable=FALSE`로 고정하며 레포에 원본 PDF를 올리지 않는다.

`coreAiItCodeSet`은 **수집 전에** 확정하고 버전을 박는다. 결과를 보고 코드 집합을 조정하면 RQ1이 순환논리가 된다.

---

## 6. 골드셋 규격 (게이트 측정용)

| 골드셋 | 대상 | n | 층화 | 이중코딩 | 게이트 |
|---|---|---|---|---|---|
| `postingKind_v1` | 공고 성격 | 300 | 연도 × indexCategoryRaw | 20% | precision ≥ 0.95 (분모 오염 방지) |
| `careerClass_v1` | E0~E3/U | 400 | 연도 × trackType | 20% | MacroF1 ≥ 0.85, **E0 precision ≥ 0.90** |
| `boundary_v1` | 필수·우대 경계 | 300 | 연도 × sectionType | 30% | precision ≥ 0.90 |
| `internAccess_v1` | I0/I1/IU | 300 | 연도 | 20% | MacroF1 ≥ 0.85 |
| `ncsMapping_v1` | 능력단위 매핑 | 300 | NCS 세분류 | 30% | precision ≥ 0.85, coverage ≥ 0.80, lowConfidence ≤ 0.20 |
| `trackSplit_v1` | 트랙 분리 정확도 | 150 | recruitmentScope | 30% | 분리 정확도 ≥ 0.90 |

- 층화 표본, 시드 고정, `samplingFrame`·`samplingSeed`를 `goldSample`에 기록
- 이중코딩 구간에서 **Cohen κ ≥ 0.70** 미달이면 라벨 정의부터 수정한다. 모델 튜닝으로 덮지 않는다
- 골드셋은 학습·프롬프트 튜닝에 쓰지 않는다. 튜닝용은 별도 dev 표본을 뽑는다

---

## 7. 최종 산출물

### 7.1 데이터셋

| 파일 | grain | 예상 행수 | 용도 |
|---|---|---|---|
| `postingAnalysisMart.parquet` | trackId | 공고수 × 1.2~1.5 | 모든 하위 집계의 유일한 원천 |
| `timeSeriesMart.parquet` | periodMonth × cohortType × jobCodeLevel × jobCode × dedupApplied | 월 96개 × 조합 | 그래프·회귀 입력 |
| `monthlyCoverageAudit.parquet` | periodMonth × sourceName | ~96 | 어느 달을 믿을 수 있는지 |
| `resultManifest.parquet` | metricId | 기사 숫자 수 | 기사 검증·정정 대응 |
| `evalRun.parquet` | evalRunId | 게이트 실행 수 | 품질 근거 |
| `caseStudyRegistry.parquet` | caseId | 5~15 | RQ5 |
| `similarityPair.parquet` | pairId | 선택 | RQ3 |

### 7.2 표 (`reports/tables/`)

| 파일 | 내용 |
|---|---|
| `T01_monthly_rates.csv` | 월별 `entryPostingRate`, `internPostingRate`, 분모 |
| `T02_exclusive_rates.csv` | entryOnly/internOnly/mixed/experiencedOnly 민감도 |
| `T03_segmented_regression.csv` | β0~β3, HAC SE, p, 기준점 3종(2022-12·2023-01·2023-04) |
| `T04_entry_barrier_shares.csv` | E0/E1 비중, 제한형 인턴 비중, 필수요건별 비율 |
| `T05_ncs_band_shares.csv` | level1to2~7to8, advancedDutyShare, medianNcsLevel |
| `T06_coverage_audit.csv` | 월별 생존율·coverageStatus |
| `T07_quality_gates.csv` | 게이트별 목표·실측·통과여부 |
| `T08_sensitivity_dedup.csv` | dedup 전/후 주요 지표 대조 |

### 7.3 그림 (`reports/figures/`)

`F01` 월별 두 비율 라인 + 2023 분절선 / `F02` `internRelativeIndex` 추이 / `F03` E0·E1 구성 스택 / `F04` 제한형 인턴 비중 / `F05` NCS 밴드 구성 100% 스택 / `F06` `advancedDutyShare` 추이 / `F07` 직무별 밴드 상승폭 / `F08` 월별 coverage 히트맵 / `F09`(RQ4) 전 직무 집중도 / `F10`(RQ3) `senioritySimilarityGap`

모든 그림은 캡션에 `dataVersion`, `asOfDate`, 분모 n, coverage 미달 구간 음영을 포함한다. 2026년 구간은 점선 + "YTD" 표기.

### 7.4 릴리스 번들 (`RELEASE/p4_release_{YYYYMMDD}/`)

```text
marts/*.parquet
qa/resultManifest.csv, evalRun.csv, monthlyCoverageAudit.csv
schema/P4_WAREHOUSE_DDL_v2.0.sql
configs/*.yaml (인증키 제외)
docs/P4_PROJECT_SSOT_v2.md, DECISION_LOG.md
CHECKSUMS.sha256
REPRODUCE.md
```

원문 공고 텍스트·이미지는 번들에 넣지 않는다.

---

## 8. 수락 기준 (`ANALYSIS_READY`)

```sql
SELECT * FROM qa.vAnalysisReadyGate;
```

전부 충족해야 통과:

1. `monthlyCoverageAudit`가 2019-01~2026-07 전 구간 기록되고, `insufficient` 월이 RQ1 분석구간에서 제외 처리됨
2. `careerClass` MacroF1 ≥ 0.85, E0 precision ≥ 0.90
3. boundary precision ≥ 0.90
4. NCS mapping precision ≥ 0.85, coverage ≥ 0.80, lowConfidenceShare ≤ 0.20
5. `postingKind` precision ≥ 0.95
6. `postingAnalysisMart`·`timeSeriesMart` 생성 + 단일 `dataVersion`
7. `resultManifest`에 기사 숫자 전부 등재, `inputMartSha256` 일치
8. dedup 전/후 두 버전 산출 완료
9. 재실행 멱등성 통합테스트 통과
