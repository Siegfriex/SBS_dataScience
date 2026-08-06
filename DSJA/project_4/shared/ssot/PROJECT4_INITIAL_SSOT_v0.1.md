# PROJECT4_INITIAL_SSOT_v0.1

- verdict: `PROJECT4_INITIAL_SSOT_READY`
- user state: `USER_DECISION_REQUIRED`
- audit mode: `READ_ONLY_FORENSIC_RECONSTRUCTION`
- generated: `2026-08-06T00:00:00+09:00`

## 1. 프로젝트·연구문제

P4는 Linkareer 채용공고와 NCS를 결합해 RQ1 시계열 공고구조, RQ2-A 진입장벽·요구조건, RQ2-B 인턴 업무의 NCS 수준·직무구조를 분석한다. RQ3~RQ5는 유사성, 독립 기술통계, 대표 사례의 보조분석이다. 허용 추론은 기술통계·패턴·상관·기간/집단 차이·조건부 연관성이다. AI 원인의 채용감소나 인턴 대체 같은 인과표현은 금지한다.

## 2. 오케스트레이터 식별자

`agentId=P4-ORCHESTRATOR`, `agentName=P4 Project-Wide Multi-Agent Orchestrator`, `role=MULTI_AGENT_CONTROL_AND_SSOT_OWNER`.

## 3. Repository topology

| Agent | Branch | Local HEAD | Remote HEAD | Ahead/Behind | Dirty | 판정 |
|---|---|---|---|---:|---|---|
| P4-A1-SOURCE | `agent/p4-crawl-release-v2` | `00b2e6b832b0` | `3ad43c39dd01` | 2/10 | tracked 0, untracked 0, ignored 43 | PARTIAL |
| P4-A2-PIPELINE | `agent/p4-pipeline-v2` | `9a0571dbcc01` | `9a0571dbcc01` | 0/0 | tracked NOT_EVALUATED, untracked NOT_EVALUATED, ignored NOT_EVALUATED | PASS_WITH_FINDINGS |
| P4-A3-CONTROL | `agent/p4-integration-cleanup-v2` | `b64270bd4ab8` | `b64270bd4ab8` | 0/0 | tracked 0, untracked 0, ignored 64 | PASS_WITH_FINDINGS |
| P4-A4-NCS | `agent/p4-ncs-mapping-v2` | `7a9feccc7a2f` | `7a9feccc7a2f` | 0/0 | tracked 0, untracked 0, ignored 5 | PASS_WITH_FINDINGS |

별도 docs repo는 `c65253f806dc95fa87c6c7dcc7d583a00de45e09`에서 local/remote parity와 clean 상태다. canonical contract snapshot은 docs repo와 byte-identical이다. Agent 3 base에는 `integration/` 디렉터리가 없고 control evidence는 `shared/`, `crawl/control/`, `reports/agent3/`에 분산돼 있다.

## 4. Source

- Linkareer release candidate `CRAWL_20260806_03`: 79개월 중 21개월 pagination 검증, 58개월 미검증, posting 137, real raw SSR 29, asset 0, full corpus false.
- source policy: robots allowed, terms reviewedConditional, transparent client verified. production human approval과 canonical audit row는 아직 없다.
- NCS source: 13,442 unique units. hierarchy code는 있으나 hierarchy name 53,768 cells는 null이다.
- core AI·IT review candidate: 120 = included 69 + excluded 51. alias 10개는 draft seed다.

## 5. 계약

`contractVersion=2.1.2`, 5 schemas, 26 base tables, 6 QA views, 11/11 checksum PASS. 식별자는 SHA-256 deterministic policy를 사용하고 빈 데이터 gate는 `NOT_EVALUATED`다.

Canonical fields: `postingEligibleFlag`, `rq1EligibleFlag`, `rq2EligibleFlag`, `ncsEligibleFlag`. `highDemandScore`는 항상 NULL이고 `validPostingFlag`는 canonical에서 사용하지 않는다.

## 6. 데이터 layer와 authority

Raw는 immutable bytes+SHA manifest, processing authority는 DuckDB/Parquet, CSV는 human-inspection export다. 현재 lineage는 raw 29 → manifest 137 → normalized/track 137 → sections 84 → requirements 35 → labels 137 → NCS candidates 128 → matches 28 → preprocessed 137이다. mart와 analysis는 시작하지 않았다.

동일 `OBSERVED_DEV_20260806_01`의 crawl/pipeline copy가 108개 lineage 행에서 다르고 observed DB는 pipeline copy와 일치한다. snapshot freeze 전에는 어느 것도 유일 SSOT로 승격하지 않는다.

## 7. Notebook system

Canonical observed source는 24개(A1 5 + A2 12 + A4 6 + A3 master 1), 234 cells/136 code cells, parameters 24/24, project module call 24/24, source output/execution 0이다. Fresh-kernel evidence는 24/24 PASS, canonical stage artifact 4종은 24/24, inventoried artifact SHA는 388/388 일치한다.

독립 판정은 source `PASS`, execution `PASS_WITH_FINDINGS`, bundle `PASS_WITH_FINDINGS`다. A4-05는 의미상 `NOT_EVALUATED`; quality 87 rows 중 PASS 80, NOT_EVALUATED 4, REVIEW_REQUIRED 3이다. 76 runtime paths가 네 remote branch에 없고 extra manifest 4개가 있어 snapshot authority가 필요하다. 전체 filesystem notebook universe는 93개이며 zero-byte는 0이다.

## 8. 현재 데이터·구조 QA

- output checksums 20/20, CSV↔Parquet schema-aware semantic pairs 8/8, PK 8 grains violation 0, FK 11 relationships orphan 0.
- canonical `p4.duckdb` 26 base tables row count 0; observed contamination 0. analysis gate는 `NOT_EVALUATED`.
- bundle text-field PII/secret/absolute-path checks는 PASS. Agent4 worktree의 ignored mode-600 `.env`는 tracked되지 않았으나 production 전 custody 결정을 요구한다.
- posting/tracks 137, raw SSR 29, sections 84, requirements 35, NCS candidates 128, final matches 28(27 mapped, 1 unmapped).

## 9. 의미 QA

`canonicalPostedAt`, `periodMonth`, `companyKey`, `requiredDegreeLevel`, positive `requiredToolCount`, `ncsLevelWeightedMedian`, `ncsBandPrimary`는 모두 0/137이다. careerClass는 137/137 존재하지만 전부 `U`; intern 35개는 전부 `IU`; boundary resolved는 0/137이다. requirement facts는 28/137 tracks에 35개뿐이며 `requirementType` 35/35가 canonical enum 밖이다. `postingKind`도 137/137 canonical enum 밖이다.

## 10. 상태 게이트

| Gate | 상태 | 근거/차단 |
|---|---|---|
| OBSERVED_DEV_CSV_READY | PASS_WITH_FINDINGS | crawl/data/exports/observed-dev/OBSERVED_DEV_20260806_01; 20/20 checksum, 8/8 semantic pairs, but duplicate bundle ID diverges from pipeline copy; authority freeze and canonical enum remediation |
| NOTEBOOK_SOURCE_READY | PASS | 24/24 source; 234 cells; 136 code; output/execution 0; module calls 24/24;  |
| NOTEBOOK_EXECUTION_READY_OBSERVED_DEV | PASS_WITH_FINDINGS | 24/24 execution; 136/136 code cells; 0 error; A4-05 meaningfully NOT_EVALUATED; NCS gold is absent |
| NOTEBOOK_BUNDLE_READY | PASS_WITH_FINDINGS | 388/388 artifact SHA; 24/24 canonical 4-artifact stage sets; 76 runtime-only paths and four duplicate manifests need snapshot authority |
| SOURCE_POLICY_READY | PARTIAL | robots allowed, reviewedConditional terms, transparent client verified; no production approval record in canonical DB; human production collection approval |
| CRAWL_RELEASE_READY | BLOCKED | CRAWL_20260806_03 is CRAWL_RELEASE_CANDIDATE; 21/79 months, raw 29/137, assets 0, head_commit blank; 58 months, full detail/raw/asset lineage, validator and source-policy closure |
| DATA_READY_RQ1_RQ2A | BLOCKED | canonicalPostedAt and periodMonth 0/137; career resolved 0/137; valid requirementType 0/35; semantic QA and production preprocessing |
| DATA_READY_RQ2B | BLOCKED | NCS mapped 27; level/band 0/137; gold 0; evaluator NOT_EVALUATED; scope decision, gold n=300 and quality gates |
| ANALYSIS_READY | BLOCKED | canonical analysis gate NOT_EVALUATED; empiricalAnalysisAllowed=false throughout observed bundle; all production data gates |

## 11. 결함

- P0: 0건 확인. tracked secret 또는 canonical data contamination은 발견되지 않았다.
- P1: 7건. snapshot divergence, crawl/date/enum/career/source-policy/NCS gold blockers.
- P2: 8건. raw/asset/Git worktree/runtime authority/NCS naming/secret custody/integration findings.
- P3: 3건. release commit metadata, query-registry 문서 drift, CSV dtype guidance.

세부 내용은 `PROJECT4_DEFECT_REGISTER.csv`가 authority다.

## 12. 의사결정·로드맵

즉시 결정은 D-ORCH-001 snapshot authority, D-ORCH-002 Agent3 integration base, D-ORCH-003 M1.5-first 순서다. M2 전에는 D-ORCH-004 source-policy/기간/2019, D-ORCH-005 asset/OCR/API-key custody가 필요하다. M3 전에는 D-ORCH-006 core 69/51 범위와 D-ORCH-007 KSA optional/gold n=300/30% 이중코딩/검수자를 확정한다.

`M1 snapshot freeze → M1.5 semantic QA → M2 full crawl → production preprocessing → M3 gold → analysis → article`.

## 통제 문장

Notebook이 실행됐다는 것은 분석데이터가 준비됐다는 뜻이 아니다.

구조적 QA 통과는 의미적 변수 완성도를 보장하지 않는다.

Observed-development 결과는 기사 결과가 아니다.

CSV는 canonical source가 아니다.

NCS candidate 생성은 NCS mapping 품질게이트 통과가 아니다.
