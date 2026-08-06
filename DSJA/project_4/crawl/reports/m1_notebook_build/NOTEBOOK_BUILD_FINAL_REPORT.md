# P4 Notebook-First final build report

- Notebook source: `24/24`
- Executed Notebook: `24/24`
- Source output count: `0`
- Output artifacts inventoried: `388`
- Run mode: `observed-dev`
- Empirical analysis allowed: `false`
- Promotion allowed: `false`

| Agent | Notebook | 파일 존재 | Cells | 실제 module call | source outputs | 실행 결과 |
|---|---|---:|---:|---:|---:|---:|
| P4-A1-SOURCE | `crawl/notebooks/00RecoverSourceState.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A1-SOURCE | `crawl/notebooks/01CollectLinkareerIndex.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A1-SOURCE | `crawl/notebooks/02CollectPostingDetail.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A1-SOURCE | `crawl/notebooks/03CollectPostingAssets.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A1-SOURCE | `crawl/notebooks/04BuildCrawlRelease.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/00ContractAndInputAudit.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/01LoadCrawlRelease.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/02ParseAndNormalize.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/03OcrAndSectionRecovery.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/04SplitTracks.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/05ExtractRequirements.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/06Deduplicate90Days.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/07LabelCareerAccess.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/08LoadAndPrepareNcs.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/09MapPostingToNcs.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/10ExportPreprocessedCsv.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A2-PIPELINE | `pipeline/notebooks/11PreprocessedDataQa.ipynb` | TRUE | 11 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/00NcsSourceAudit.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/01BuildCoreAiItCodeSet.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/02BuildNcsRetrievalIndex.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/03MapObservedDuties.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/04ExportNcsMappingCsv.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A4-NCS | `ncs_mapping/notebooks/05EvaluateNcsMapping.ipynb` | TRUE | 6 | TRUE | 0 | PASS |
| P4-A3-CONTROL | `crawl/notebooks/P4_Notebook_First_Master.ipynb` | TRUE | 11 | TRUE | 0 | PASS |

## State decision

- `OBSERVED_DEV_CSV_READY = READY`
- `NOTEBOOK_SOURCE_READY = READY`
- `NOTEBOOK_EXECUTION_READY_OBSERVED_DEV = READY`
- `NOTEBOOK_BUNDLE_READY = READY`

The bundle does not declare production crawl, RQ data, or analysis readiness.
