# Agent 4 M1 NCS lexical baseline report

## Status

```text
NCS_MAPPING_DEV_READY
```

Final Notebook execution source Git HEAD: `afac9fd9e1854715759c7d893440cbe89e04c150`.

This status is limited to observed development. It is not a production code-set freeze, gold validation, final precision/coverage result, RQ2-B result, or `DATA_READY_RQ2B` declaration.

## Fixed execution policy

```text
runMode = observed-dev
contractVersion = 2.1.2
crawlReleaseId = CRAWL_20260806_03
dataProvenance = OBSERVED_DEVELOPMENT_ONLY
empiricalAnalysisAllowed = false
promotionAllowed = false
mappingMode = LEXICAL_BASELINE
codeSetStatus = REVIEW_REQUIRED
goldValidatedFlag = false
denseScore = NULL
KSA = optional enrichment (D-023 provisional)
```

`dense_rerank` was not called. The existing identity stub remains explicitly outside the M1 execution path.

## Implemented

- Strict observed-duty handoff validator: sender/recipient, contract/release, observed-only flags, required row schema, unique `sectionId`, SHA-256 syntax, declared row count, and canonical rows SHA.
- Dependency-free token plus Korean character n-gram TF-IDF lexical index over included NCS units.
- Same-subcategory enforcement: a returned unit code must begin with its selected 8-digit `ncsSubCode`; alias hits restrict retrieval to the alias-declared subcategory.
- Batch top-5 materialization, bare-tool-only exclusion, explicit unmapped reason, and development-only confidence category.
- Six canonical Parquet plus UTF-8-SIG inspection CSV exports and semantic round-trip equality checks.
- Agent 2 handoff with relative paths, file SHA-256 values, observed-only policy, and prohibited-claim list.
- Six executable source notebooks with deterministic cell IDs, title/spec Markdown first and a first-code-cell 13-variable common parameter contract, no stored outputs, stage-specific `src/p4_ncs` calls, input audits, and termination checks.
- Four termination artifacts for each stage, matching the Agent 3 manifest and metrics schemas. `stage_quality.csv` uses `gateId,ruleId,severity,status,observedValue,threshold,evidencePath`.

## Recomputed observed results

| Item | Rows |
|---|---:|
| NCS units | 13,442 |
| Core candidate codes | 120 |
| Included development codes | 69 |
| Excluded development codes | 51 |
| Lexical unit documents | 691 |
| Alias rows | 10 |
| Observed duty input | 28 |
| Candidate rows | 128 |
| Match/unmapped rows | 28 |
| Explicit unmapped rows | 1 |
| Gold rows | 0 |

The current Agent 2 handoff supplies `rowsSha256`; the recomputed digest matched. These counts are pipeline-development observations only and are not mapping performance metrics.

## Outputs

Canonical and inspection exports:

```text
ncs_mapping/data/exports/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/
  ncs_units.parquet/csv
  core_ai_it_codes.parquet/csv
  ncs_alias_dictionary.parquet/csv
  posting_ncs_candidates.parquet/csv
  posting_ncs_matches.parquet/csv
  ncs_mapping_summary.parquet/csv
```

Handoff:

```text
shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json
```

Per-stage termination artifacts:

```text
ncs_mapping/data/runs/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/<stageId>/
  stage_manifest.json
  stage_metrics.json
  stage_quality.csv
  CHECKSUMS.sha256
```

## Validation evidence

- `python3 -m pytest -q`: 34 passed (22 pre-existing plus 12 M1 tests).
- Six notebooks executed in separate fresh kernels: 00~04 `SUCCEEDED`, 05 `NOT_EVALUATED` as required for zero gold rows.
- `nbformat.validate`, per-cell `ast.parse`, source outputs=0, and parameter-cell-first: passed.
- All six `stage_manifest.json` and `stage_metrics.json` files validated against the current Agent 3 schemas.
- Each stage directory contains exactly the four termination artifacts.
- CSV-to-Parquet semantic equality: passed for all six exports.
- Top-5 cap, unmapped preservation, same-subcategory unit prefix, bare-tool exclusion, null dense score, and observed provenance: passed.
- Absolute-path and secret-pattern scan over exported data, stage artifacts, and handoff: no hits.
- Ignored local `ncs_mapping/.env` was preserved and is not staged.

## Remaining restrictions

- The `core-ai-it-v0.1` 69/51 decision remains `REVIEW_REQUIRED`, not production-frozen.
- Development confidence labels are operational triage categories, not calibrated probabilities.
- No final precision, final coverage, or low-confidence quality-gate result is claimed.
- Gold annotation/evaluation and any RQ2-B use remain blocked.

Final executed copies and their four-artifact stage bundles are stored under:

```text
ncs_mapping/runs/notebooks/observed-dev/AGENT4_20260806_01/
```
