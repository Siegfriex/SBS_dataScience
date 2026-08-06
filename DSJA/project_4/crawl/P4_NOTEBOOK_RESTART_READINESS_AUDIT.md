# P4 Notebook 재기동 통합 정보제공 감사

`auditMode = READ_ONLY_AUDIT`

`auditAt = 2026-08-06T16:14:12+09:00`

`agent1Status = AGENT1_NOTEBOOK_INFORMATION_READY`

`agent2Status = AGENT2_NOTEBOOK_INFORMATION_READY`

`empiricalAnalysisAllowed = false`

이 문서는 Prompt A와 Prompt B의 요구사항을 한 파일로 합친 현시점 스냅샷이다. 감사 중 신규 수집, API key 사용, raw 수정, release 재발행, warehouse 생성, 실데이터 mart·분석·figure 생성은 하지 않았다. 숫자는 보고서 복사가 아니라 filesystem·Parquet·JSONL·DuckDB·Git을 직접 읽어 재계산했다.

## 0. Executive verdict

1. Agent 1의 커밋된 `crawl/**`에는 재실행 가능한 Python 모듈·CLI·테스트가 없다. release·fixture·YAML·감사문서만 있다.
2. Agent 1 worktree에는 미커밋 Notebook `notebooks/P4_A1_LINKAREER_FULL_CORPUS_E2E.ipynb`가 존재하며 수집·resume·policy client 로직을 포함하지만, 19 cells/11 code cells/0 outputs이고 실행·테스트 증거가 없다. 안정된 entrypoint로 취급할 수 없다.
3. 최신 release `CRAWL_20260806_03`은 16/16 checksum PASS, 79개월 중 21개월 complete로 진전됐지만 full-corpus input은 아니다.
4. Agent 2 committed pipeline은 contract v2.1.2, canonical warehouse, parser·normalize·dedup·label·NCS·mart·provenance 기반을 갖췄다. Production Notebook 15개는 모두 4 cells/3 code cells/0 outputs의 placeholder다.
5. Agent 2 committed parser는 실제 raw HTML 29/29를 SSR로 열 수 있으나 standalone `ActivityText`를 0/29만 복원한다. 별도 dirty worktree의 미커밋 보완 코드는 29/29 ActivityText와 OCR 후보 30건을 복원했다고 기록하지만 아직 branch 계약이 아니다.
6. canonical `p4.duckdb`는 26 tables 전부 0행이며 `NOT_EVALUATED`다. 실증 분석은 계속 차단한다.

---

# Part A — P4-A1-SOURCE 감사

## A1. Repository 복원

| 항목 | 관측값 |
|---|---|
| repository root | `/home/sieg/projects-wsl/SBS_dataScience` |
| remote | `origin = https://github.com/Siegfriex/SBS_dataScience.git` |
| worktree | `/home/sieg/projects-wsl/worktrees/p4-agent1` |
| branch | `agent/p4-crawl-release-v2` |
| local HEAD | `379fc1fc138fc8e84da2dd431a02ed5fcd866bed` |
| remote HEAD | `379fc1fc138fc8e84da2dd431a02ed5fcd866bed` |
| ahead/behind | `0 / 0` |
| dirty | `?? DSJA/project_4/crawl/notebooks/` |
| known dirty file | `notebooks/P4_A1_LINKAREER_FULL_CORPUS_E2E.ipynb` (62,814 bytes, 미커밋) |

기준 HEAD보다 최신 원격은 없었다. dirty Notebook은 감사 이전부터 존재했고 수정하지 않았다.

## A2. Release inventory

| Release | status | contract | source period | coverage | manifest rows | raw/asset | checksum | 핵심 gap |
|---|---|---:|---|---|---|---|---|---|
| `RECON_20260806_01` | `RECON_ONLY` | 없음 | 2019~2026 spot-check | 정식 coverage 없음 | 정식 manifest 없음 | raw 0, asset 0 | 14항목 중 11 PASS, 3 missing | `configs/sources.yaml`, `docs/ssot/P4_DATASET_SPEC_v2.0.md`, `docs/ssot/P4_WAREHOUSE_DDL_v2.0.sql` 부재 |
| `CRAWL_20260806_01` | `PARTIALLY_READY` | null | 2020-01~2026-07 | target 79: complete 1, unverified 78; 전체 85: insufficient 5, partial 1 | crawl 4, asset 0, NCS 0 | masked fixture 4, real raw HTML 0 | 13/13 PASS | pagination 78개월, n=35 pilot, range semantics 당시 미확정 |
| `CRAWL_20260806_02` | `PARTIALLY_READY` | 2.1.2 | 2020-01~2026-07 | target: complete 11, unverified 68 | crawl 6, asset 0, NCS 2 | derived sample 126, real raw HTML 0 | 14/14 PASS | per-record HTML lineage 없음, assets 0 |
| `CRAWL_20260806_03` | `CRAWL_RELEASE_CANDIDATE` | 2.1.2 | 2020-01~2026-07 | target: complete 21, unverified 58; 전체 85: insufficient 5, partial 1 | fetch 33, posting 137, asset 0, NCS 2 | local real HTML 29, asset 0 | 16/16 PASS | full pagination·full detail·commit lineage·asset·KSA schema 미완료 |

월별 `returnedDistinctCount` 합계는 `_01=949`, `_02=11,825`, `_03=40,551`이다. 이는 월별 distinct의 합계이며, 전체 기간 global distinct ID는 `posting_discovery_index`가 release에 없으므로 계산할 수 없다.

### CRAWL_03 manifest 정합성

- `fetch_manifest.jsonl`: 33행 = 실제 detail raw 29 + 이전 masked SSR fixture 3 + APQ fixture 1.
- 실제 detail raw unique ID 29개 중 `posting_manifest`에 포함된 ID는 29개다.
- derived sample 126개와 실제 raw의 교집합은 18개이며 union은 `126 + 29 - 18 = 137`이다.
- `posting_manifest.hasDetailRawHtml=true`는 11개뿐이다. derived와 겹치는 raw 18개가 flag에 반영되지 않았다.
- HANDOFF의 “8 overlapping” 문구와 직접 조인 결과 18이 불일치한다.
- `fetch_manifest`는 `requestUrl/contentSha256`을 사용하여 Agent 2 strict field `sourceUrl/rawSha256`과 이름이 다르다.
- 실제 raw는 release 내부가 아니라 `crawl/data/raw/**`에 있고 release checksum 목록에 포함되지 않는다.
- `HANDOFF.json.head_commit`은 빈 문자열이다.

## A3. 코드 module inventory

### A3.1 Committed branch

`crawl/**`에서 `.py` 파일, Python package, CLI, `pyproject.toml`, test 파일은 모두 0개다.

| 요구 기능 | committed 상태 | implementationPath | testPath | 재시작성 |
|---|---|---|---|---|
| APQ query builder | `NOT_IMPLEMENTED` | `configs/queryRegistry.yaml`은 registry일 뿐 실행 코드 아님 | 없음 | 불가 |
| pagination loop | `NOT_IMPLEMENTED` | 결과 CSV만 존재 | 없음 | 불가 |
| range semantics | `EVIDENCE_ONLY` | `docs/audit/APQ_RANGE_SEMANTICS_FINAL.md` | 관측 CSV만 존재 | 로직 재실행 불가 |
| transparent httpx client | `NOT_IMPLEMENTED` | committed code 없음 | 없음 | 불가 |
| rate limiter | `NOT_IMPLEMENTED` | committed code 없음 | 없음 | 불가 |
| concurrency limiter | `NOT_IMPLEMENTED` | committed code 없음 | 없음 | 불가 |
| HTTP 403 kill switch | `NOT_IMPLEMENTED` | committed code 없음 | 없음 | 불가 |
| success-rate kill switch | `NOT_IMPLEMENTED` | committed code 없음 | 없음 | 불가 |
| raw/gzip store | `ARTIFACT_ONLY` | `data/raw/linkareer/detail/**` | 없음 | writer 복원 불가 |
| SHA-256 | `ARTIFACT_ONLY` | manifests/checksum 파일 | 없음 | 함수 복원 불가 |
| fetch manifest writer | `ARTIFACT_ONLY` | `_03/fetch_manifest.jsonl` | 없음 | append/resume 불가 |
| posting manifest builder | `ARTIFACT_ONLY` | `_03/posting_manifest.parquet` | 없음 | 재생성 불가 |
| asset collector | `NOT_IMPLEMENTED` | asset manifest 0행 | 없음 | 불가 |
| release builder | `NOT_IMPLEMENTED` | release 결과만 존재 | 없음 | 불가 |
| Agent 2 validator adapter | `NOT_IMPLEMENTED` | Agent 2 경로에만 존재 | Agent 2 tests | Agent 1 단독 불가 |

### A3.2 Dirty uncommitted Notebook

`notebooks/P4_A1_LINKAREER_FULL_CORPUS_E2E.ipynb`에 다음 구현이 들어 있으나 미커밋·미실행·무테스트 상태다.

| cell | class/function(signature) | purpose | I/O·side effect | network/raw/manifest | idempotent/resume |
|---:|---|---|---|---|---|
| 2 | `locate_project_root(start: Path)` | root·env·phase 설정 | 실행 즉시 run/raw directory 생성 | 없음/dir write | phase env 지원 |
| 4 | `atomic_write_bytes`, `atomic_write_text`, `atomic_write_json`, `write_parquet_atomic`, `append_jsonl_once`, `verify_checksum_file` | atomic I/O·hash·manifest | 파일 생성/교체 | raw/manifest write | key 기반 append-once |
| 9 | `RateLimiter(minimum=1.0,jitter=(.15,.45))` | ≤1 req/sec | sleep | 없음 | 결정적이지 않은 jitter |
| 9 | `PolicyHttpClient.get(url, ..., entity_type, period, ...)` | transparent sync HTTP, retry, raw store | HTTP·gzip·fetch manifest | network=yes, raw=yes, manifest=yes | 최대 4회 retry |
| 9 | `PolicyHttpClient._check_health(status,body)` | 403/challenge/200-window kill | 예외 발생 | network result 검사 | 최근 200건 상태 유지 |
| 11 | `month_bounds_ms(period)` | 월 경계 | 순수 함수 | 없음 | yes |
| 11 | `apq_params(operation,query_hash,variables)` | APQ GET params | 순수 함수 | 없음 | yes |
| 11 | `apq_json(...)` | APQ response 요청 | HTTP | network=yes | client retry |
| 11 | `collect_month(period)` | date/side bucket pagination | checkpoint/discovery parquet | network/raw/manifest=yes | 월 checkpoint 지원 |
| 15 | `extract_detail_record(source_id,body,manifest)` | SSR `__NEXT_DATA__`/Apollo parse | posting parquet | 없음 | source ID key |
| 15 | `persist_frontier(df)` | detail frontier 저장 | CSV/parquet write | manifest-like state | status resume |
| 17 | `is_linkareer_hosted(url)` | 외부 ATS 차단 | 순수 함수 | 외부 host 요청 억제 | yes |

Notebook은 19 cells, 11 code cells, output 0, execution count 전부 null이다. `P4_A1_PHASE`, `P4_A1_RUN_ID`, `P4_A1_MAX_MONTHS`, `P4_A1_MAX_DETAILS`, `P4_A1_MAX_ASSETS`, `P4_A1_PROBE_INSANE`, `P4_A1_RETRY_FINAL_MONTHS`를 사용한다. `restore` phase도 directory와 audit 파일을 쓸 수 있으므로 현재 상태에서 read-only safe가 아니다.

## A4. Source-policy 구현 증거

| 정책 | committed | dirty Notebook | test | exercisedInRun | evidence | 판정 |
|---|---|---|---|---|---|---|
| ≤1 request/sec | 없음 | `RateLimiter`, minimum 1.0 + jitter | 없음 | `_03` 실제 29건 최소 간격 1.418초, median 1.655초, 1초 미만 0 | `fetch_manifest.jsonl` timestamps | `OBSERVED_COMPLIANT / UNCOMMITTED_CODE` |
| concurrency ≤2 | 없음 | sync `httpx.Client`, 사실상 concurrency 1 | 없음 | concurrency telemetry 없음 | Notebook cell 9 | `POLICY_ONLY` |
| HTTP 403 immediate stop | 없음 | status 403 즉시 `SourcePolicyBlocked` | 없음 | 실제 29건 모두 200, 403 미발생 | Notebook cell 9 | `POLICY_ONLY_NOT_EXERCISED` |
| success-rate kill switch | 없음 | 최근 200건 success <0.90 중단 | 없음 | 200-response window 미도달 | Notebook cell 9 | `POLICY_ONLY_NOT_EXERCISED` |
| external ATS 미추적 | enforcement 없음 | `is_linkareer_hosted` | 없음 | fetch manifest 요청은 Linkareer/APQ fixture뿐 | cell 17, fetch manifest | `OBSERVED_COMPLIANT / UNTESTED` |
| no impersonation | committed client 없음 | httpx UA는 투명함 | 없음 | RECON은 `curl_cffi(impersonate='chrome')` 사용 기록 | `RECON HANDOFF.transparentClientNote` | `REVIEW_REQUIRED` |

따라서 canonical Source Policy Gate는 여전히 `REVIEW_REQUIRED`다. 코드 설명만으로 PASS를 부여하지 않는다.

## A5. 실제 데이터 inventory

| 지표 | filesystem 재계산값 |
|---|---:|
| monthly coverage rows | 85 |
| target rows 2020-01~2026-07 | 79 |
| complete months | 21 |
| partial months | 1 (`2026-08`, target 밖) |
| insufficient months | 5 (`2019` spot checks) |
| unverified months | 58 |
| target monthly distinct ID sum | 40,551 |
| global distinct IDs | `NOT_COMPUTABLE` — discovery index release 부재 |
| posting manifest rows/unique IDs | 137 / 137 |
| actual raw HTML gzip files | 29 |
| raw HTML compressed bytes | 922,111 |
| decompressed SHA match | 29/29 |
| asset files | 0 |
| asset manifest rows | 0 |
| formal OCR candidate manifest | `NOT_IMPLEMENTED` |
| n=126 derived embedded-image candidates | 113 |
| dirty Agent 2 observed OCR queue | 30, `UNCOMMITTED_OBSERVED_DEV` |

## A6. Source schema inventory

`contractField`는 direct/alias/none로 표기한다. URL·path 예시는 마스킹한다.

### monthly_coverage.parquet

| name | type | nullable | definition | exampleMasked | contractField |
|---|---|---:|---|---|---|
| periodMonth | string | no | 관측 월 | `2019-01` | `qa.monthlyCoverageAudit.periodMonth` direct |
| sourceName | string | no | 원천 | `linkareer` | direct |
| activityTypeID | string | no | Linkareer activity type | `5` | producer-local |
| discoveredCount | float64 | yes(58) | 발견 건수 | `254` | alias observedItemCount |
| returnedDistinctCount | float64 | yes(63) | 월 distinct 반환 수 | `254` | producer-local |
| expectedTotalCount | float64 | yes(58) | bucket 기대 합 | `0` | producer-local |
| paginationCompleteFlag | bool | no | bucket exhaustion | `false` | direct concept |
| requestCount | int64 | no | 월 요청 수 | `1` | producer-local |
| firstPostingId | string | yes(65) | 첫 ID | `[ID]` | none |
| lastPostingId | string | yes(65) | 마지막 ID | `[ID]` | none |
| errorCount | int64 | no | 오류 요청 수 | `0` | direct concept |
| coverageStatus | string | no | complete/partial/... | `insufficient` | direct |
| coverageReason | string | no | 상태 근거 | `platformPreLaunch` | evidence alias |
| platformCoverageRegime | string | no | 플랫폼 시기 | `preStableRecruitService` | producer-local |
| note | string | no | 감사 메모 | `[MASKED_NOTE]` | evidence alias |

### fetch_manifest.jsonl

| name | type | nullable | definition/exampleMasked | contractField |
|---|---|---:|---|---|
| crawlRunId | string | no | run ID | `raw.crawlRun.crawlRunId` |
| entityType | string | no | index/detail | producer-local |
| requestUrl | string | no | `[LINKAREER_URL]` | **alias required: sourceUrl** |
| operationName | string | yes(29) | APQ/manualSeed | query registry relation |
| variablesHash | null-only | yes(33) | 변수 hash 미기록 | producer-local |
| httpStatus | int | no | HTTP status | direct |
| fetchedAt | ISO string | no | fetch timestamp | direct |
| contentSha256 | string | no | decompressed HTTP bytes SHA | **alias required: rawSha256** |
| rawPath | string | no | `[RAW_PATH]` | direct but release-root portable 아님 |
| bytes | int | yes(4) | HTTP body bytes | fileSize alias |
| elapsedMs | int | yes(4) | latency | producer-local |
| collectorVersion | string | no | collector version | direct |

### posting_manifest.parquet

| name | type | nullable | definition/exampleMasked | contractField |
|---|---|---:|---|---|
| sourcePostingId | string | no | `[ID]` | direct |
| sourceName | string | no | `linkareer` | direct |
| discoverySource | string | no | capture lineage | producer-local |
| hasDetailRawHtml | bool | no | raw detail 존재 flag | producer-local; 현재 18건 false-negative |
| hasDerivedFields | bool | no | derived sample 존재 | producer-local |
| jobTypes | string | yes(11) | pipe-delimited list | `jobTypesRawJson`으로 보존 필요 |
| activityTextAvailable | object/bool | yes(11) | body availability | alias |
| externalApplyFlag | object/bool | yes(11) | 외부 지원 URL 존재 | direct concept |
| externalDetailOnlyFlag | object/bool | yes(11) | Linkareer body 없음 | direct concept |
| rq1EligibleFlag | object/bool | yes(11) | RQ1 후보 | contract direct, Agent 2 재판정 필요 |
| rq2EligibleFlag | object/bool | yes(11) | RQ2 후보 | contract direct, Agent 2 재판정 필요 |
| ncsEligibleFlag | object/bool | yes(11) | NCS 후보 | contract direct, Agent 2 재판정 필요 |

### Other source objects

| object | actual schema/status |
|---|---|
| posting_discovery_index | release에 없음; dirty Notebook runtime 산출 설계만 존재 |
| asset_manifest | 0-byte JSONL, schema row 없음 |
| ocr_candidate_manifest | `NOT_IMPLEMENTED` |
| NCS manifest | 2행 heterogeneous JSONL; `sourceDataset,sourceUrl,datasetId,sourceVersion,license,fieldList,recordCount,accessMethod,redistributable,encoding,rawPath,utf8NormalizedPath,levelDistribution,ingestedAt,confirmedEndpoint,endpointStatus,note,keyStoredInGit` |

NCS manifest의 list/dict (`fieldList`, `levelDistribution`)는 CSV로 내릴 때 canonical JSON string과 별도 child table을 함께 보존해야 한다.

## A7. 현재 검증된 실행 명령

Committed collector/CLI가 없으므로 다음 수집 명령은 `NONE_VERIFIED`다.

| 요구 명령 | 현재 상태 | workingDirectory / resume |
|---|---|---|
| 월 한 개 index 수집 | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| 연도 단위 resume | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| 상세 20건 dry run | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| 상세 batch | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| asset batch | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| release staging | `NOT_IMPLEMENTED_COMMITTED` | 없음 |
| checksum | 검증만 가능: release dir에서 `sha256sum -c CHECKSUMS.sha256` | read-only, network 0 |

미커밋 E2E Notebook은 env phase로 실행할 후보 코드가 있으나 실제 실행 성공이 입증되지 않았으므로 “동작하는 명령”으로 제공하지 않는다. API key를 요구하지 않지만 network와 raw write가 발생할 수 있다.

## A8. Agent 1 Notebook 연결 계획

| notebook | cellStage | calledModule/function | input | output | status | missingImplementation |
|---|---|---|---|---|---|---|
| 00RecoverSourceState | Git/release/raw audit | committed module 없음; dirty Notebook cell 4/6 utilities | releases/raw/contracts | restart inventory | `BLOCKED` | utilities를 `.py`로 추출·test·commit |
| 01CollectLinkareerIndex | month plan/APQ/pagination/checkpoint | dirty `apq_params`, `apq_json`, `collect_month` | month, registry | discovery parquet, coverage checkpoint | `UNCOMMITTED_UNTESTED` | CLI, pagination tests, exact schema |
| 02CollectPostingDetail | frontier/fetch/SSR parse | dirty `PolicyHttpClient.get`, `extract_detail_record`, `persist_frontier` | discovery IDs | raw gzip, fetch/posting manifest | `UNCOMMITTED_UNTESTED` | dry-run, resume test, portable raw lineage |
| 03CollectPostingAssets | Linkareer-host filter/download | dirty `is_linkareer_hosted` + cell 17 | asset candidates | assets, asset manifest | `UNCOMMITTED_UNTESTED` | asset schema, MIME/hash tests, OCR candidate manifest |
| 04BuildCrawlRelease | coverage merge/checksum/handoff | dirty cell 19 | run state/manifests | staged release | `UNCOMMITTED_UNTESTED` | immutable staging builder, Agent 2 validator invocation |

## A9. PII-masked sample

### monthly_coverage 5 rows

| periodMonth | expected | status | reason | requestCount |
|---|---:|---|---|---:|
| 2019-01 | 0 | insufficient | platformPreLaunch | 1 |
| 2019-03 | 0 | insufficient | platformPreLaunch | 1 |
| 2019-06 | 1 | insufficient | platformPreLaunch | 1 |
| 2019-09 | 0 | insufficient | platformPreLaunch | 1 |
| 2019-12 | 23 | insufficient | platformPreLaunch | 1 |

### posting_manifest 5 rows

| sourcePostingId | jobTypes | raw | derived | RQ1 | RQ2 | NCS |
|---|---|---:|---:|---:|---:|---:|
| `[ID-1]` | NEW\|EXPERIENCED | false | true | true | true | false |
| `[ID-2]` | NEW | false | true | true | true | false |
| `[ID-3]` | NEW\|EXPERIENCED\|CONTRACT | false | true | true | true | false |
| `[ID-4]` | INTERN\|NEW\|CONTRACT | false | true | true | true | false |
| `[ID-5]` | INTERN | false | true | true | true | false |

### fetch/raw metadata 5 rows

| posting | status | fetchedAt | source bytes | SHA prefix | raw path |
|---|---:|---|---:|---|---|
| `[ID-1]` | 200 | 14:56:56+09 | 153,615 | `a0f7f6bfcd41…` | `[MASKED]` |
| `[ID-2]` | 200 | 14:56:58+09 | 169,284 | `8ff4fe824127…` | `[MASKED]` |
| `[ID-3]` | 200 | 14:56:59+09 | 167,152 | `ee961629b7cb…` | `[MASKED]` |
| `[ID-4]` | 200 | 14:57:01+09 | 153,948 | `7db73da84d23…` | `[MASKED]` |
| `[ID-5]` | 200 | 14:57:02+09 | 164,519 | `d08c890ca45f…` | `[MASKED]` |

HTML 본문과 manager/연락처는 포함하지 않았다.

---

# Part B — P4-A2-PIPELINE 감사

## B1. Repository

| 항목 | committed 기준 | active dirty worktree |
|---|---|---|
| branch | `agent/p4-pipeline-v2` | 동일 |
| HEAD | `71edc867a8e869b78340e4fe253ced9312894077` | 동일 |
| remote HEAD | 동일 | 동일 |
| ahead/behind | 0/0 | 0/0 |
| worktree | main checkout는 detached HEAD | `/tmp/p4-agent2-observed` |
| dirty | Agent 2 소유 경로 clean | observed-development 관련 modified 5 + untracked 10 이상 |

Dirty worktree의 주요 신규 파일은 `run_observed_development.py`, `manifest_cursor.py`, `release_validation.py`, `observed_batch.py`, `warehouse/observed.py`, observed report/DB/handoffs다. 이 감사에서는 읽기만 했으며 branch 구현으로 간주하지 않는다.

## B2. Warehouse 상태

| DB | classification | bytes | SHA-256 | schemas/tables/views | rows | provenance | empiricalUseAllowed |
|---|---|---:|---|---|---|---|---:|
| `p4.synthetic.duckdb` | `SYNTHETIC_FIXTURE_ONLY` | 10,760,192 | `4e08b5645747cfd21742480c32d87e50dcf5187ba5a1fa30f0e5bbca3883e03e` | 5/11/0 | raw 6, normalized 6, tracks 6, sections 10, req 10, labels 6, NCS 3/4, marts 6/10 | SYNTHETIC | false |
| `p4.duckdb` | `CANONICAL_EMPTY` | 2,895,872 | `d1e33086ccbd10249d90e9cea5fce58a3205db92a078a1d198920a6d87a8d9a0` | 5/26/6 | **26 tables 모두 0행** | contract 2.1.2 / NOT_EVALUATED | false |
| `p4.observed-dev.duckdb` (committed worktree) | `ABSENT` | - | - | - | - | - | false |
| `p4.observed-dev.duckdb` (dirty `/tmp` worktree) | `UNCOMMITTED_OBSERVED_DEVELOPMENT_ONLY` | 3,158,016 | `931b0cf610bba01e7d687d9aec232e0580cb5d0a16e3c4c65ce657ca7c3a1f57` | observed-local schema | raw/normalized/track/eligibility 137, sections 84, req 35, OCR queue 30, cursor 29 | OBSERVED_DEVELOPMENT_ONLY | false |

Canonical DB에는 synthetic·observed row가 유입되지 않았다.

## B3. Production Notebook inventory

모든 Notebook은 `cellCount=4`, `codeCellCount=3`, `outputCount=0`, execution count null이다. 실제 pipeline 함수를 import/call하지 않고 metadata·STATUS·FINAL JSON만 출력하는 placeholder다. 현재 실행은 파일 write가 없어 안전하지만 결과를 만들지 않는다.

| Notebook | intended input → output | implementedCalls | placeholder | safeToExecute |
|---|---|---|---:|---:|
| 00ContractAndInputAudit | contract/release → audit | root/Git metadata only | yes | yes, no-op |
| 01LoadCrawlRelease | HANDOFF/manifests → raw staging | none | yes | yes, no-op |
| 02ParseAndNormalize | APQ/SSR → normalized | none | yes | yes, no-op |
| 03OcrAndSectionRecovery | HTML/assets → OCR/sections | none | yes | yes, no-op |
| 04SplitTracks | normalized → tracks | none | yes | yes, no-op |
| 05ExtractRequirements | sections → facts | none | yes | yes, no-op |
| 06Deduplicate90Days | postings → groups/edges | none | yes | yes, no-op |
| 07LabelCareerAccess | tracks/facts → labels | none | yes | yes, no-op |
| 08LoadAndPrepareNcs | NCS raw → units/bands | none | yes | yes, no-op |
| 09MapPostingToNcs | duties/NCS → matches | none | yes | yes, no-op |
| 10BuildPostingMart | core/NCS → posting mart | none | yes | yes, no-op |
| 11BuildTimeSeriesMart | posting mart → time series | none | yes | yes, no-op |
| 12AnalyzeRq1Rq2 | time series → models | none | yes | yes, no-op |
| 13BuildArticleFigures | mart/results → figures | none | yes | yes, no-op |
| 90AuxSimilarity | canonical marts → auxiliary | none | yes | yes, no-op |

공통 parameter는 branch, HEAD, contractVersion 2.1.2, crawlReleaseId `_02`, dataVersion, asOfDate다. `_03` 기준으로는 metadata가 stale다.

## B4. Code entrypoint inventory

| 기능 | path / signature | grain·columns | exception/idempotency | test |
|---|---|---|---|---|
| contract loader | `contracts/loader.py::load_contract_yaml(bundle)` | bundle→dict | missing/invalid file 예외; pure | `test_contracts.py` |
| crawl validator | `validate_crawl_release(path, expected_contract_version=None)`; `assess_crawl_release(...)` | HANDOFF→audit | missing locator/checksum/lineage 예외; read-only | `test_contracts.py` |
| raw loader | committed batch raw loader 없음 | - | `NOT_IMPLEMENTED` | 없음 |
| SSR parser | `next_data.extract_next_data(html)`, `extract_page_props(next_data)` | HTML→Next JSON/pageProps | missing script 예외; pure | `test_linkareer_adapters.py` |
| Apollo parser | `apollo_cache.find_apollo_cache(value)`, `extract_activity(cache,id)` | cache→activity/duties/text | entity missing 예외; pure | adapter tests |
| ActivityText parser | `parse_activity_text_html(html)`, `embedded_image_urls(html)`, `build_ocr_queue_candidates(html,min=300)` | HTML→blocks/image candidates | pure/idempotent | adapter tests |
| PII masker | `apq.mask_manager(value)` | manager object→masked | manager 한정; generic PII masker 없음 | adapter tests |
| posting normalizer | `normalize_posting(raw)`, `normalize_postings(frame)` | posting row/frame→normalized row/frame | required column/parse errors | `test_parse_normalize.py` |
| postingKind classifier | 독립 classifier 없음; `normalize_posting`은 입력 kind 소비 | - | `PARTIAL_IMPLEMENTATION` | parse tests |
| eligibility | `resolve_job_types(...)`; `eligibility_flags(*,...)` | source evidence→5 flags/reason | pure | adapter/normalize tests |
| OCR router | `build_ocr_queue_candidates` | ActivityText→asset candidate | OCR 실행 엔진 없음 | adapter embedded-image test |
| section splitter | `parse_sections(body_text)` | body→section rows | unresolved boundary 보존 | parse tests |
| track splitter | `split_tracks(posting, explicit_tracks=None)` | posting→tracks | mixedUnresolved 보존 | parse tests |
| requirement extractor | `experience_months(text)`; `extract_requirements(section)` | section→atomic facts | regex scope 제한 | requirement tests |
| dedup candidate/resolver | `title_similarity`; `assign_repost_groups(postings,window_days=90,title_threshold=.9)` | posting→group/canonical flags | deterministic; candidate와 resolver 단일 함수 | dedup tests |
| career labeler | `career_class(evidence)`; `label_track(track_id,evidence)` | track evidence→E0~E3/U | pure | requirement/label tests |
| intern labeler | `intern_access_class(evidence)` | intern evidence→I0/I1/IU | pure | requirement/label tests |
| NCS input adapter | 능력단위 source loader 없음 | - | `NOT_IMPLEMENTED` | 없음 |
| NCS bands/mapping | `ncs_band(level)`; `dictionary_candidates(...)`; `rank_candidates(...)` | level/evidence→band/matches | invalid level/tool-only 예외 | `test_ncs.py` |
| posting mart | `build_posting_analysis_mart(postings,tracks,labels,matches=None,ncs_units=None,cohort_type='coreAiIt',lineage=None)` | track grain | lineage/PK validation | `test_marts.py` |
| time-series mart | `build_time_series_mart(posting_mart,low_confidence_threshold=.7)` | month×cohort×job×dedup | deterministic aggregation | `test_marts.py` |
| CSV exporter | committed exporter 없음 | - | `NOT_IMPLEMENTED` | 없음 |
| warehouse QA | `primary_key_duplicates`, `null_rate`, `orphan_count` | table→metric | safe identifier validation | warehouse tests |
| provenance guard | `require_production_provenance(payload)`; `ProvenanceContext.require_empirical()` | envelope→allow/raise | fail-closed | provenance/warehouse/analysis tests |

## B5. CRAWL_03 acceptance

| 판단 층 | 판정 | 근거 |
|---|---|---|
| adapter conformance | `PASS_WITH_ADAPTER_ALIAS` | contract 2.1.2, checksum 16/16, robots allowed, source fields 실재 |
| observed-development loadability | committed parser `PARTIAL`; dirty worktree `PASS_FOR_137_OBSERVED` | raw 29 hash·SSR parse 가능; derived 108 보조 입력 |
| full-corpus acceptance | `FAIL` | 58개월 unverified, status candidate, head_commit blank, full raw 없음, assets 0, KSA schema 미확정 |

Committed strict validator는 `sourceUrl/rawPath/rawSha256`를 요구하지만 `_03/fetch_manifest`는 `requestUrl/rawPath/contentSha256`이므로 다음 오류로 중단한다.

```text
ValueError: crawl release manifest lacks sourceUrl/rawPath/rawSha256 lineage
```

raw path도 release-root 기준이 아니라 crawl-root 기준이며 29개 gzip은 release checksum에 없다.

## B6. Observed-development loadability

### Committed HEAD 독립 read-only 재계산

| metric | count |
|---|---:|
| posting manifest rows | 137 |
| real raw HTML available/hash-valid | 29/29 |
| missing raw relative to 137 | 108 |
| invalid fetch rows for strict field contract | 33 (`requestUrl/contentSha256` aliases 필요) |
| SSR activity parseable | 29/29 |
| ActivityText recovered by committed parser | 0/29 |
| embedded image rows by committed parser | 0 |

### Dirty worktree snapshot — branch 계약 아님

미커밋 standalone ActivityText fallback과 observed batch를 사용한 기존 report는 다음을 기록한다.

| metric | observed dirty result |
|---|---:|
| input/parse success/failure | 137 / 137 / 0 |
| real SSR raw parse success | 29/29 |
| derived observed fallback | 108 |
| ActivityText recovered | 29 |
| embedded image/OCR queue | 30 |
| tracks / split success / mixed / unknown | 137 / 85 / 43 / 9 |
| sections / requirements | 84 / 35 |
| RQ1/RQ2/NCS eligible | 137 / 113 / 55 |

`p4.observed-dev.duckdb`를 안전하게 만들기 위한 최소 변경은 다음 여섯 가지다.

1. fetch alias adapter: `requestUrl→sourceUrl`, `contentSha256→rawSha256`.
2. crawl-root raw path resolver와 gzip decompression SHA 검증.
3. Apollo cache의 unambiguous standalone `ActivityText:*` fallback.
4. canonical DB와 분리된 `OBSERVED_DEVELOPMENT_ONLY` provenance/DB.
5. 137-row batch assembler와 manifest cursor.
6. parser 결과·derived fallback의 source mode를 명시하고 empirical flag를 강제로 false.

dirty worktree에 위 구현이 존재하지만 커밋·독립 검증 전에는 Notebook에서 호출하면 안 된다.

## B7. 전처리 CSV exact schema 제안

공통 규칙: UTF-8, RFC 4180, header 1행, LF, timestamp ISO-8601 Asia/Seoul, boolean `true/false`, null은 빈 필드, list/dict는 canonical JSON string. 모든 ID는 v2.1.2 SHA-256 key 형식이다.

표기: `N` non-null, `Y` nullable; `PK/FK/ENUM/RANGE/SHA/LINEAGE`는 quality rule이다.

### posting_normalized.csv — grain postingId

| column:type:null | source | derivation / quality |
|---|---|---|
| postingId:string:N | sourceName+sourcePostingId | canonical PST / PK |
| rawPostingId:string:N | raw SHA | canonical RAW / FK |
| sourcePostingId:string:N, sourceUrl:string:N | raw manifest | direct/alias; URL required |
| companyKey:string:Y, companyName:string:Y, industryName:string:Y | activity | normalize/preserve null |
| jobTitle:string:Y, bodyText:string:Y | APQ/ActivityText/OCR | normalized text |
| postedAt:timestamp:Y, deadlineAt:timestamp:Y | created/recruit dates | timezone-aware |
| postingKind:string:N, recruitmentScope:string:N | activityType/jobTypes/body | ENUM |
| postingEligibleFlag:bool:N, rq1EligibleFlag:bool:N, rq2EligibleFlag:bool:N, ncsEligibleFlag:bool:N | eligibility | independent flags |
| rq2ExclusionReason:string:Y, invalidReason:string:Y | eligibility | ENUM/preserve null |
| duplicateGroupId:string:Y, canonicalPostingId:string:N, canonicalPostedAt:timestamp:N, canonicalRecordFlag:bool:N, repostCount:int:N | dedup | independent from eligibility; count≥0 |
| rawSha256:string:N | raw bytes | 64-hex SHA |
| activityTypeId:int:Y | APQ/SSR | direct |
| jobTypesRawJson:json:N, dutiesRawJson:json:N | structured source | canonical JSON string |
| activityTextHtml:string:Y | ActivityText | exact HTML lineage; no normalization overwrite |
| externalApplyUrl:string:Y, externalAtsDomain:string:Y, externalApplyFlag:bool:N, externalDetailOnlyFlag:bool:N, jobTypeConflictFlag:bool:N | source adapter | direct/derived |
| parseVersion:string:N, contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N, normalizedAt:timestamp:N | runtime | LINEAGE; empirical requires CRAWL_ + EMPIRICAL |

### posting_tracks.csv — grain trackId

| column:type:null | source | derivation / quality |
|---|---|---|
| trackId:string:N, postingId:string:N, trackIndex:int:N | normalized+ordinal | TRK PK, posting FK, index≥0 |
| trackType:string:N, trackTitle:string:Y | duties/jobTypes/body | ENUM |
| hasEntryFlag:bool:N, hasInternFlag:bool:N, hasExperiencedFlag:bool:N | resolved types | exact flags |
| recruitmentScope:string:N, mixedResolvedFlag:bool:N, splitConfidence:float:Y | splitter | ENUM, confidence 0..1 |
| jobTypeSource:string:N, jobTypeConflictFlag:bool:N | authority priority | ENUM/review lineage |
| trackVersion:string:N, contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N | runtime | LINEAGE |

### posting_sections.csv — grain sectionId

| column:type:null | source | derivation / quality |
|---|---|---|
| sectionId:string:N, trackId:string:N, postingId:string:N, sectionOrder:int:N | track+ordinal | SEC PK/FK; order≥0 |
| sectionType:string:N | heading assignment | ENUM title/duty/required/preferred/other |
| sectionText:string:N | DOM/OCR block | non-empty evidence |
| sourceMode:string:N | html/ocr/merged | ENUM |
| boundaryResolvedFlag:bool:N, sectionConfidence:float:Y | parser | confidence 0..1 |
| evidenceSpansJson:json:N | DOM offsets | canonical JSON list; separate child export optional |
| parseVersion:string:N, contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N | runtime | LINEAGE |

### requirement_facts.csv — grain requirementId

| column:type:null | source | derivation / quality |
|---|---|---|
| requirementId:string:N, sectionId:string:N, trackId:string:N, postingId:string:N | section/evidence | REQ PK/FK |
| requirementType:string:N, obligation:string:N | parser+section | ENUM |
| valueNum:float:Y, valueUnit:string:Y, valueText:string:Y | evidence normalization | preserve source missingness |
| certificateNameRaw:string:Y, certificateClass:string:Y, degreeLevel:string:Y | evidence | controlled enums where applicable |
| evidenceText:string:N | section span | non-empty, verbatim limited to source row |
| extractorVersion:string:N, confidence:float:Y, reviewFlag:bool:N | runtime | confidence 0..1 |
| contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N | runtime | LINEAGE |

### career_access_labels.csv — grain trackId

| column:type:null | source | derivation / quality |
|---|---|---|
| trackId:string:N, postingId:string:N | tracks | PK/FK |
| careerClass:string:N, internAccessClass:string:Y | evidence rules | ENUM E0/E1/E2/E3/U; I0/I1/IU |
| nominalEntryFlag:bool:N, openEntryFlag:bool:N, restrictedEntryFlag:bool:N | career class | deterministic |
| openInternFlag:bool:N, restrictedInternFlag:bool:N, experiencedInternFlag:bool:N | intern class/evidence | portfolio/preferred-only 금지 |
| minCareerMonths:int:Y, requiredExperienceFlag:bool:N, requiredPriorExperienceFlag:bool:N, boundaryResolvedFlag:bool:N, explicitCareerFlag:bool:N | facts | months≥0 |
| labelConfidence:float:Y, labelVersion:string:N | labeler | confidence 0..1 |
| contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N | runtime | LINEAGE |

### preprocessed_posting_tracks.csv — grain trackId

| column group | exact columns / rule |
|---|---|
| identity | `trackId,postingId,rawPostingId,sourcePostingId,sourceUrl,canonicalPostingId` non-null |
| posting | `companyKey,companyName,jobTitle,postedAt,deadlineAt,postingKind,recruitmentScope` |
| source JSON | `jobTypesRawJson,dutiesRawJson,activityTextHtml`; JSON/HTML string을 그대로 보존 |
| eligibility | `postingEligibleFlag,rq1EligibleFlag,rq2EligibleFlag,ncsEligibleFlag,rq2ExclusionReason,canonicalRecordFlag` |
| track | `trackIndex,trackType,trackTitle,hasEntryFlag,hasInternFlag,hasExperiencedFlag,mixedResolvedFlag,splitConfidence,jobTypeSource,jobTypeConflictFlag` |
| label | `careerClass,internAccessClass,minCareerMonths,openEntryFlag,restrictedEntryFlag,openInternFlag,restrictedInternFlag,experiencedInternFlag` |
| evidence counts | `dutySectionCount,requiredSectionCount,preferredSectionCount,requirementCount,unresolvedBoundaryCount,ocrSectionCount` integers ≥0 |
| lineage | `rawSha256,parseVersion,trackVersion,labelVersion,contractVersion,crawlReleaseId,dataVersion,dataProvenance` non-null |

### data_quality_summary.csv — grain qualityCheckId

| column:type:null | definition / quality |
|---|---|
| qualityCheckId:string:N | deterministic PK |
| stage:string:N, tableName:string:N, checkName:string:N | check identity |
| status:string:N | PASS/WARN/FAIL/NOT_EVALUATED ENUM |
| inputRows:int:N, affectedRows:int:N | ≥0 |
| affectedRate:float:Y | 0..1 |
| thresholdJson:json:Y, observedJson:json:Y | canonical JSON |
| evidencePath:string:Y, message:string:Y | audit evidence |
| checkedAt:timestamp:N, contractVersion:string:N, crawlReleaseId:string:N, dataVersion:string:N, dataProvenance:string:N | LINEAGE |

JSON/list flattening 손실 방지: 원문 JSON string column 유지 + 선택적 child CSV (`posting_duties.csv`, `section_evidence_spans.csv`)를 동일 ID FK로 별도 발행한다. pipe join이나 Python repr를 canonical 값으로 사용하지 않는다.

## B8. Notebook cell plan

공통 cell 1은 metadata, 마지막 cell은 manifest summary다.

| notebook | cell plan: purpose → moduleCall → output/display → failureCondition |
|---|---|
| 00ContractAndInputAudit | 1 metadata; 2 contract `audit_contract_bundle`; 3 release `validate_release_gates`; 4 DB read-only inventory; 5 gate table; 6 manifest. FAIL checksum/schema/dirty input authority |
| 01LoadCrawlRelease | 1 metadata; 2 HANDOFF parse; 3 alias/path/checksum validation; 4 manifest row inventory; 5 loadable/unloadable display; 6 manifest. FAIL raw missing/hash mismatch |
| 02ParseAndNormalize | 1 metadata; 2 manifest cursor; 3 gzip/SSR/Apollo parse; 4 `adapt_linkareer_source`; 5 `normalize_postings`; 6 parse failures/QA; 7 CSV/manifest. FAIL source hash or key collision |
| 03OcrAndSectionRecovery | 1 metadata; 2 embedded-image routing; 3 asset availability; 4 OCR execution adapter; 5 `parse_sections`; 6 boundary QA; 7 export. FAIL assets absent for OCR execution; routing-only 허용 |
| 04SplitTracks | 1 metadata; 2 structured type authority; 3 `split_tracks`; 4 conflict/mixed QA; 5 export. FAIL duplicate trackId or invalid enum |
| 05ExtractRequirements | 1 metadata; 2 eligible sections; 3 `extract_requirements`; 4 atomic evidence QA; 5 export. FAIL missing evidenceText/invalid obligation |
| 06Deduplicate90Days | 1 metadata; 2 base eligible set; 3 `assign_repost_groups`; 4 canonical independence QA; 5 export. FAIL >90-day edge or multiple canonical rows |
| 07LabelCareerAccess | 1 metadata; 2 evidence aggregate; 3 `label_track`; 4 E/I boundary tests; 5 export. FAIL enum or portfolio/preferred-only violation |
| 08LoadAndPrepareNcs | 1 metadata; 2 NCS manifest/checksum; 3 source CSV load; 4 level/band QA; 5 export. FAIL duplicate unit code/level outside 1..8 |
| 09MapPostingToNcs | 1 metadata; 2 duty eligible input; 3 dictionary candidates; 4 rank/validate matches; 5 coverage QA; 6 export. FAIL missing evidence/basis/version |
| 10ExportPreprocessedCsv | 1 metadata; 2 load core outputs; 3 exact-schema projection; 4 JSON canonicalization; 5 seven CSV writes; 6 row/hash manifest. FAIL schema drift/PK duplicate/lineage missing |
| 11PreprocessedDataQa | 1 metadata; 2 PK/null/FK QA; 3 eligibility denominators; 4 source/provenance gate; 5 quality summary; 6 restart readiness display. FAIL empirical flag on partial/observed input |

## B9. 실행환경

| item | observed |
|---|---|
| Python | 3.12.3, GCC 13.3 |
| environment | `/home/sieg/projects-wsl/SBS_dataScience/.venv` shared venv; kernel `project_4_sbs_venv` |
| package manager | pip/setuptools, `pyproject.toml` |
| required | duckdb, jsonschema, matplotlib, nbformat, pandas, pyarrow, PyYAML, statsmodels; pytest optional |
| DuckDB | 1.5.4 |
| pandas | 3.0.3 |
| Polars | not installed/not used |
| OCR | `pytesseract` installed; pipeline에는 OCR engine wrapper 없음; easyocr 없음 |
| embedding | sentence-transformers/torch/sklearn installed in shared env; committed NCS mapper는 dictionary/rank 중심 |
| environment variables | committed pipeline은 필수 secret/env 없음; paths config 사용. Agent 1 dirty Notebook은 `P4_A1_*` phase/limit vars 사용 |
| API key | 이번 감사에서 사용하지 않음; Git 저장 없음 |

`tabulate`는 설치되지 않아 pandas `to_markdown`은 사용할 수 없다. CSV/Parquet/DuckDB 기능에는 영향이 없다.

## B10. Test coverage matrix

현재 committed source는 `pytest --collect-only -p no:cacheprovider`로 93 tests가 수집된다. tracked final report는 93 PASS를 기록하지만 local `runs/pytest-results.xml`은 이전 83-test run으로 stale하다. dirty observed report의 “100 passed”는 이번 감사에서 재실행하지 않았으므로 별도 미검증 기록이다.

| category | direct test evidence | coverage | gap |
|---|---|---|---|
| contract | `test_contracts.py` 8 + key contract tests | strong | actual `_03` alias/path portability fixture 부족 |
| warehouse | `test_warehouse.py` 4 | strong | observed DB는 uncommitted |
| parser | `test_linkareer_adapters.py` 11 | fixture strong | 29 real SSR regression은 committed test 아님 |
| eligibility | adapter + normalize tests | moderate | annual selection-bias QA 없음 |
| OCR routing | embedded-image test 1 | routing only | OCR execution/accuracy test 없음 |
| track split | parse normalize tests 2 | basic | real mixed track gold set 없음 |
| requirement | parse/requirements tests | basic | certificate/degree breadth 낮음 |
| dedup | `test_dedup.py` 2 | basic deterministic | body similarity/resolver review test 없음 |
| labels | requirements/labels collected 10 | strong rules | real gold agreement test 없음 |
| NCS | `test_ncs.py` collected 12 | rule strong | actual source loader/KSA test 없음 |
| mart | `test_marts.py` 4 | synthetic strong | empirical corpus 없음 |
| provenance | provenance collected 10 + warehouse/analysis guards | strong fail-closed | observed mode branch 미커밋 |
| Notebook | direct production Notebook test 0 | none | nbformat/cell call/output contract integration test 필요 |
| CSV export | 0 | none | exporter 자체가 없음 |

---

# 11. 재기동 우선순위와 완료 조건

## Agent 1

1. dirty E2E Notebook의 collector를 `crawl/src` 모듈과 CLI로 추출한다.
2. rate/concurrency/403/success kill tests를 network mock으로 추가한다.
3. 한 달·20 detail·asset 1건의 dry run을 실행하고 checkpoint resume를 검증한다.
4. `sourceUrl/rawSha256` canonical aliases와 release-contained raw/checksum을 보장한다.
5. 79개월 pagination과 full detail/asset collection 전에는 `CRAWL_READY`를 선언하지 않는다.

## Agent 2

1. active dirty observed implementation을 먼저 별도 검토·테스트·commit한다.
2. `_03` alias adapter와 standalone ActivityText fallback을 real raw 29 fixture로 고정한다.
3. production Notebook placeholder를 위 cell plan의 실제 module calls로 교체한다.
4. CSV exporter와 exact-schema/lineage tests를 구현한다.
5. full release 전에는 observed DB와 canonical DB를 절대 혼합하지 않는다.

## 현재 허용 상태

```text
AGENT1_NOTEBOOK_INFORMATION_READY
AGENT2_NOTEBOOK_INFORMATION_READY
SOURCE_ADAPTER_CONFORMANCE_ONLY
OBSERVED_DEVELOPMENT_ONLY
BLOCKED_BY_FULL_CRAWL_RELEASE
EMPIRICAL_ANALYSIS_ALLOWED=false
```

`MART_READY`, `DATA_READY`, `ANALYSIS_READY`, `CRAWL_READY`는 선언할 수 없다.
