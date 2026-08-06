# Agent 5 Crawl Notebook deep audit

## 1. Executive verdict

`CRAWL_NOTEBOOK_SYSTEM_REQUIRES_PATCH`

여섯 source Notebook은 모두 JSON/nbformat/AST/cell-ID/output-policy 기준을 통과하고 source/executed code parity도 통과했다. 그러나 production crawl 경로, Master 의존순서, cross-agent validator gate, 현재-run artifact 결속에 P1 결함이 있어 patch 전 production 승격은 금지한다.

## 2. Git and repository baseline

- audit branch/base: `agent/p4-notebook-audit-v1` / `b64270bd4ab839ec750a4ceceb08d57957c88782`
- Agent 1 source: `3ad43c39dd01933575529e0c81d9809dc64c4e57`
- Agent 2 source: `9a0571dbcc0183960bda153baedcd0a2c9dc8248`
- Agent 4 source: `7a9feccc7a2fc99b8b86b95bdb73699620bc7ff0`
- integration source: `b64270bd4ab839ec750a4ceceb08d57957c88782`
- live checkout: detached `71edc867a8e869b78340e4fe253ced9312894077`, dirty; `DSJA/project_4/crawl` is untracked in that checkout but each audited Notebook byte-for-byte matches its designated branch blob.
- remote fetch completed; known Agent 1-4 head values were confirmed.

## 3. Notebook integrity

| Notebook | bytes | SHA-256 | cells | module calls | validation |
|---|---:|---|---:|---:|---|
| `00RecoverSourceState.ipynb` | 8337 | `4bf405ece28246d893ea347ee1aeb27a4283f25a98926473c1fdcf6aac37f3c9` | 11 | 17 | VALID_SOURCE_NOTEBOOK |
| `01CollectLinkareerIndex.ipynb` | 7936 | `01d65fdb65d5610f437d0fbd06f5d692b5122d070fddb6be06ab41cfc1293806` | 11 | 16 | VALID_SOURCE_NOTEBOOK |
| `02CollectPostingDetail.ipynb` | 8387 | `0b1b749f5d9fe1b8f55eb71c7274a5e846e8309ab709c6c38ef43f17ca5dcb95` | 11 | 16 | VALID_SOURCE_NOTEBOOK |
| `03CollectPostingAssets.ipynb` | 8459 | `91899e17cc9c76e3e7bc05388919ebd643a763d971daa8af68817087b258daf3` | 11 | 16 | VALID_SOURCE_NOTEBOOK |
| `04BuildCrawlRelease.ipynb` | 8914 | `7d1b0b35302cdd0fea13b7b1ff682395ae16095f27d23c606928725c5af8110b` | 11 | 18 | VALID_SOURCE_NOTEBOOK |
| `P4_Notebook_First_Master.ipynb` | 10005 | `84ba8f52070c7941043be4195a146af2218d74e9c0fd6855c6122cf094da345c` | 11 | 6 | VALID_SOURCE_NOTEBOOK |

- total audited cells: 66 (6-Notebook scope); duplicate/missing IDs: 0/0; source outputs/execution counts: 0/0.
- all six executed copies preserve cell order/IDs and non-parameter source. Differences are injected parameters, execution counts, outputs, and run metadata only.
- current source SHA-256 equals the prior M1 inventory for all six.

## 4. Deep functional verdicts

| Stage | structural status | functional verdict | evidence |
|---|---|---|---|
| A1-00-RECOVER | PASS_WITH_FINDINGS | RECOVERY_PARTIAL | 137 posting, 29 raw; remaining months only summarized, not enumerated |
| A1-01-INDEX | PARTIAL | INDEX_IMPLEMENTATION_PARTIAL;INDEX_POLICY_BLOCKED | fixture networkCalls=0; 21/79 complete, 58 unverified; no success-rate kill switch |
| A1-02-DETAIL | PASS_WITH_FINDINGS | DETAIL_LOCAL_REPLAY_READY;DETAIL_LINEAGE_PARTIAL | 29/29 local SSR replay and ActivityText; standalone ActivityText fallback absent in crawl parser |
| A1-03-ASSET | NOT_EVALUATED | ASSET_LINEAGE_ONLY;ASSET_COLLECTION_NOT_EVALUATED | 59 metadata candidates, 30 OCR candidates, 0 fetched, 0 external ATS calls |
| A1-04-RELEASE | BLOCKED | RELEASE_OBSERVED_VALIDATION_READY;RELEASE_PRODUCTION_BLOCKED | CRAWL_RELEASE_READY NOT_EVALUATED; validator execution failure incorrectly eligible for PASS |
| A3-MASTER-ORCHESTRATION | PASS_WITH_FINDINGS | MASTER_EXECUTION_OBSERVED_READY;MASTER_PRODUCTION_BLOCKED | 24/24 execution, but dependency order and duplicate-manifest validation defects |

`READY` strings were not used as proof. 01 is a fixture APQ exercise, 03 has zero fetched assets, and 04 validates an observed package rather than building a production release.

## 5. Data lineage

`recover → index → detail → assets → release → master audit`

- observed package: 137 postings, 29 verified gzip SSR pages, no copied raw bodies, 0 asset rows.
- detail replay: 29/29 parsed and ActivityText recovered; sourceUrl/requestUrl and rawSha256/contentSha256 aliases are applied.
- assets: 59 Linkareer-hosted metadata candidates and 30 OCR candidates; fetched manifest remains 0 rows and `CRAWL_ASSET_LINEAGE_READY` is `NOT_EVALUATED`.
- release candidate: 21/79 months complete, 58 unverified; `CRAWL_RELEASE_READY=false`.
- observed export recalculation: tracks 137, sections 84, requirements 35, NCS candidates 128, matches 28, mapped 27, unmapped 1.

Complete artifact-level hashes, sizes, rows, columns, grain and path classes are in `NOTEBOOK_DATA_IO_LINEAGE.csv`.

## 6. Execution dependencies

- module definitions called by the six notebooks are implemented; test coverage is recorded per definition in `NOTEBOOK_MODULE_DEPENDENCY_MATRIX.csv`.
- runtime uses `/home/sieg/projects-wsl/SBS_dataScience/.venv/bin/python` / Python 3.12.3; Notebook metadata kernel is `python3`.
- installed but undeclared crawl requirements include `nbclient` and `beautifulsoup4`; `papermill` is documented but not installed. No lock file was found.
- Master registry is acyclic, but its actual execution list violates upstream order for A2-08/A2-09 versus A4 producers.

## 7. Existing execution result recalculation

- source Notebooks: 24/24; cells: 234; source outputs: 0.
- execution: 24/24; actual module-call rows: 24/24.
- artifact inventory: 388 rows, missing 0, hash mismatches 0.
- Master children contain 27 manifest files for 23 unique stage IDs and 108 termination files. Duplicate stage IDs are present, so “24 × 4” must be interpreted by unique planned stage—not raw file count.
- planned child 23 + Master 1 normalization reproduces `SUCCEEDED 23 / NOT_EVALUATED 1`; raw recursive files also contain one stale FAILED manifest and four duplicated stage IDs.
- recursive checksum audit: 42 checksum files, 226 entries passed, 0 failed.

### Controlled replay

- after static network-path review, 00~04 were executed in fresh kernels under `crawl/runs/notebooks/observed-dev/AGENT5_AUDIT_20260806_01`: 5/5 PASS.
- all 38 replay checksum entries pass; source Notebook SHA-256 values remained unchanged.
- 01 recorded `networkCalls=0`; 03 recorded `externalAtsTransportCalls=0`; 04 reproduced `EXECUTION_FAILED` for Agent 2 validation while keeping `crawlReleaseReady=false`.
- Master replay remained blocked because it executes 23 children and some write shared observed-development roots.

## 8. Structural QA versus semantic QA

- structural QA: `PASS_WITH_FINDINGS` — schema, AST, source parity, existing artifact hashes and checksums are intact.
- semantic QA: `NOT_EVALUATED` — full-corpus month/detail/assets, labeling gold, NCS gold precision/coverage and RQ denominators are not complete.
- fixture/local replay success is not live crawl success; a stage manifest PASS does not establish semantic completeness.

## 9. M1 and M2

- M1 observed-development: `PASS_WITH_FINDINGS`; review CSV bundle is reproducible as development evidence.
- M1.5 semantic QA: `NOT_STARTED`.
- M2 production crawl: `BLOCKED` by 58 months, incomplete full-corpus detail/assets, validator failure, and orchestration provenance/order defects.

## 10. Defects

- P0: 0
- P1: 6
- P2: 5
- P3: 1

The complete evidence and owner-specific fixes are in `AGENT5_NOTEBOOK_DEFECT_REGISTER.csv`.

## 11. Security and PII

- tracked secret 0; staged secret 0; Notebook-output secret 0.
- 29 raw HTML files are runtime-only under ignored `data/raw/`; raw PII Git tracked 0.
- external ATS transport calls 0. No secret values are included in this report.
- Master executed output exposes an absolute local repo path, recorded as P2 portability/policy drift.

## 12. Next recommended work

1. P4-A3-CONTROL: topologically order `crawl/control/notebook_bundle.py` and enforce one current-run manifest per planned stage.
2. P4-A1-SOURCE: fix the validator gate in `crawl/notebooks/04BuildCrawlRelease.ipynb`/renderer and add tested production-only index pagination/source-policy gating.
3. P4-A1-SOURCE + P4-A2-PIPELINE: unify the standalone `ActivityText:*` fallback and asset source-field lineage.
4. P4-A3-CONTROL: declare and lock Notebook/runtime dependencies before M2.

Final audit state: `AGENT5_NOTEBOOK_AUDIT_COMPLETE` / `USER_DECISION_REQUIRED`.
