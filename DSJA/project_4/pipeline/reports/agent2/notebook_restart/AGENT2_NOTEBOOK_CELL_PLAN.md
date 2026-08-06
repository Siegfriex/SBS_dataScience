# Agent 2 Notebook cell plan

agentId = P4-A2-PIPELINE
agentName = P4 Contract-Driven Pipeline & Analysis Engineer

## 00ContractAndInputAudit.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | contract bundle + CRAWL release | validated metadata | contract/release IDs | release/contract mismatch |
| 2 | code | parameters and path resolution | n/a | contract bundle + CRAWL release | validated metadata | resolved read-only inputs | release/contract mismatch |
| 3 | code | validate inputs: load_contract_bundle/audit_contract_bundle + validate crawl handoff | load_contract_bundle/audit_contract_bundle + validate crawl handoff | contract bundle + CRAWL release | validated metadata | validation summary | release/contract mismatch |
| 4 | code | execute stage: load_contract_bundle/audit_contract_bundle + validate crawl handoff | load_contract_bundle/audit_contract_bundle + validate crawl handoff | contract bundle + CRAWL release | validated metadata | row counts and exclusions | release/contract mismatch |
| 5 | code | write/check output with deterministic schema | n/a | contract bundle + CRAWL release | validated metadata | path, rows, SHA-256 | release/contract mismatch |
| 6 | markdown | interpret QA without empirical claims | n/a | contract bundle + CRAWL release | validated metadata | failure and next gate | release/contract mismatch |

## 01LoadCrawlRelease.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | accepted crawl release | raw/manifest frames | contract/release IDs | full-corpus or observed mode not explicit |
| 2 | code | parameters and path resolution | n/a | accepted crawl release | raw/manifest frames | resolved read-only inputs | full-corpus or observed mode not explicit |
| 3 | code | validate inputs: validate_release + read manifests with manifest cursor | validate_release + read manifests with manifest cursor | accepted crawl release | raw/manifest frames | validation summary | full-corpus or observed mode not explicit |
| 4 | code | execute stage: validate_release + read manifests with manifest cursor | validate_release + read manifests with manifest cursor | accepted crawl release | raw/manifest frames | row counts and exclusions | full-corpus or observed mode not explicit |
| 5 | code | write/check output with deterministic schema | n/a | accepted crawl release | raw/manifest frames | path, rows, SHA-256 | full-corpus or observed mode not explicit |
| 6 | markdown | interpret QA without empirical claims | n/a | accepted crawl release | raw/manifest frames | failure and next gate | full-corpus or observed mode not explicit |

## 02ParseAndNormalize.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | raw HTML + posting manifest | posting_normalized | contract/release IDs | raw SHA or parser failure |
| 2 | code | parameters and path resolution | n/a | raw HTML + posting manifest | posting_normalized | resolved read-only inputs | raw SHA or parser failure |
| 3 | code | validate inputs: parse_next_data/extract_activity/normalize_posting | parse_next_data/extract_activity/normalize_posting | raw HTML + posting manifest | posting_normalized | validation summary | raw SHA or parser failure |
| 4 | code | execute stage: parse_next_data/extract_activity/normalize_posting | parse_next_data/extract_activity/normalize_posting | raw HTML + posting manifest | posting_normalized | row counts and exclusions | raw SHA or parser failure |
| 5 | code | write/check output with deterministic schema | n/a | raw HTML + posting manifest | posting_normalized | path, rows, SHA-256 | raw SHA or parser failure |
| 6 | markdown | interpret QA without empirical claims | n/a | raw HTML + posting manifest | posting_normalized | failure and next gate | raw SHA or parser failure |

## 03OcrAndSectionRecovery.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | ActivityText + assets | posting_sections + OCR queue | contract/release IDs | asset missing or boundary unresolved |
| 2 | code | parameters and path resolution | n/a | ActivityText + assets | posting_sections + OCR queue | resolved read-only inputs | asset missing or boundary unresolved |
| 3 | code | validate inputs: parse_activity_text/split_sections + OCR router | parse_activity_text/split_sections + OCR router | ActivityText + assets | posting_sections + OCR queue | validation summary | asset missing or boundary unresolved |
| 4 | code | execute stage: parse_activity_text/split_sections + OCR router | parse_activity_text/split_sections + OCR router | ActivityText + assets | posting_sections + OCR queue | row counts and exclusions | asset missing or boundary unresolved |
| 5 | code | write/check output with deterministic schema | n/a | ActivityText + assets | posting_sections + OCR queue | path, rows, SHA-256 | asset missing or boundary unresolved |
| 6 | markdown | interpret QA without empirical claims | n/a | ActivityText + assets | posting_sections + OCR queue | failure and next gate | asset missing or boundary unresolved |

## 04SplitTracks.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | posting_normalized + recovered text | posting_tracks | contract/release IDs | mixed posting force-allocation |
| 2 | code | parameters and path resolution | n/a | posting_normalized + recovered text | posting_tracks | resolved read-only inputs | mixed posting force-allocation |
| 3 | code | validate inputs: split_tracks | split_tracks | posting_normalized + recovered text | posting_tracks | validation summary | mixed posting force-allocation |
| 4 | code | execute stage: split_tracks | split_tracks | posting_normalized + recovered text | posting_tracks | row counts and exclusions | mixed posting force-allocation |
| 5 | code | write/check output with deterministic schema | n/a | posting_normalized + recovered text | posting_tracks | path, rows, SHA-256 | mixed posting force-allocation |
| 6 | markdown | interpret QA without empirical claims | n/a | posting_normalized + recovered text | posting_tracks | failure and next gate | mixed posting force-allocation |

## 05ExtractRequirements.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | posting_sections | requirement_facts | contract/release IDs | evidence lineage missing |
| 2 | code | parameters and path resolution | n/a | posting_sections | requirement_facts | resolved read-only inputs | evidence lineage missing |
| 3 | code | validate inputs: extract_requirements | extract_requirements | posting_sections | requirement_facts | validation summary | evidence lineage missing |
| 4 | code | execute stage: extract_requirements | extract_requirements | posting_sections | requirement_facts | row counts and exclusions | evidence lineage missing |
| 5 | code | write/check output with deterministic schema | n/a | posting_sections | requirement_facts | path, rows, SHA-256 | evidence lineage missing |
| 6 | markdown | interpret QA without empirical claims | n/a | posting_sections | requirement_facts | failure and next gate | evidence lineage missing |

## 06Deduplicate90Days.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | posting_normalized | dedup assignments | contract/release IDs | unstable ordering/key collision |
| 2 | code | parameters and path resolution | n/a | posting_normalized | dedup assignments | resolved read-only inputs | unstable ordering/key collision |
| 3 | code | validate inputs: deduplicate_reposts | deduplicate_reposts | posting_normalized | dedup assignments | validation summary | unstable ordering/key collision |
| 4 | code | execute stage: deduplicate_reposts | deduplicate_reposts | posting_normalized | dedup assignments | row counts and exclusions | unstable ordering/key collision |
| 5 | code | write/check output with deterministic schema | n/a | posting_normalized | dedup assignments | path, rows, SHA-256 | unstable ordering/key collision |
| 6 | markdown | interpret QA without empirical claims | n/a | posting_normalized | dedup assignments | failure and next gate | unstable ordering/key collision |

## 07LabelCareerAccess.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | tracks + requirement facts | career_access_labels | contract/release IDs | unresolved evidence coerced |
| 2 | code | parameters and path resolution | n/a | tracks + requirement facts | career_access_labels | resolved read-only inputs | unresolved evidence coerced |
| 3 | code | validate inputs: classify_career/classify_intern_access | classify_career/classify_intern_access | tracks + requirement facts | career_access_labels | validation summary | unresolved evidence coerced |
| 4 | code | execute stage: classify_career/classify_intern_access | classify_career/classify_intern_access | tracks + requirement facts | career_access_labels | row counts and exclusions | unresolved evidence coerced |
| 5 | code | write/check output with deterministic schema | n/a | tracks + requirement facts | career_access_labels | path, rows, SHA-256 | unresolved evidence coerced |
| 6 | markdown | interpret QA without empirical claims | n/a | tracks + requirement facts | career_access_labels | failure and next gate | unresolved evidence coerced |

## 08LoadAndPrepareNcs.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | NCS manifest/unit rows | prepared NCS units | contract/release IDs | level outside 1..8 |
| 2 | code | parameters and path resolution | n/a | NCS manifest/unit rows | prepared NCS units | resolved read-only inputs | level outside 1..8 |
| 3 | code | validate inputs: level_to_band + NCS input adapter | level_to_band + NCS input adapter | NCS manifest/unit rows | prepared NCS units | validation summary | level outside 1..8 |
| 4 | code | execute stage: level_to_band + NCS input adapter | level_to_band + NCS input adapter | NCS manifest/unit rows | prepared NCS units | row counts and exclusions | level outside 1..8 |
| 5 | code | write/check output with deterministic schema | n/a | NCS manifest/unit rows | prepared NCS units | path, rows, SHA-256 | level outside 1..8 |
| 6 | markdown | interpret QA without empirical claims | n/a | NCS manifest/unit rows | prepared NCS units | failure and next gate | level outside 1..8 |

## 09MapPostingToNcs.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | duty sections + NCS dictionary | NCS match rows | contract/release IDs | tool-name-only match |
| 2 | code | parameters and path resolution | n/a | duty sections + NCS dictionary | NCS match rows | resolved read-only inputs | tool-name-only match |
| 3 | code | validate inputs: map_duties_to_ncs | map_duties_to_ncs | duty sections + NCS dictionary | NCS match rows | validation summary | tool-name-only match |
| 4 | code | execute stage: map_duties_to_ncs | map_duties_to_ncs | duty sections + NCS dictionary | NCS match rows | row counts and exclusions | tool-name-only match |
| 5 | code | write/check output with deterministic schema | n/a | duty sections + NCS dictionary | NCS match rows | path, rows, SHA-256 | tool-name-only match |
| 6 | markdown | interpret QA without empirical claims | n/a | duty sections + NCS dictionary | NCS match rows | failure and next gate | tool-name-only match |

## 10ExportPreprocessedCsv.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | normalized/tracks/sections/labels | six preprocessing CSVs | contract/release IDs | grain or lineage violation |
| 2 | code | parameters and path resolution | n/a | normalized/tracks/sections/labels | six preprocessing CSVs | resolved read-only inputs | grain or lineage violation |
| 3 | code | validate inputs: dataframe joins + to_csv with canonical JSON fields | dataframe joins + to_csv with canonical JSON fields | normalized/tracks/sections/labels | six preprocessing CSVs | validation summary | grain or lineage violation |
| 4 | code | execute stage: dataframe joins + to_csv with canonical JSON fields | dataframe joins + to_csv with canonical JSON fields | normalized/tracks/sections/labels | six preprocessing CSVs | row counts and exclusions | grain or lineage violation |
| 5 | code | write/check output with deterministic schema | n/a | normalized/tracks/sections/labels | six preprocessing CSVs | path, rows, SHA-256 | grain or lineage violation |
| 6 | markdown | interpret QA without empirical claims | n/a | normalized/tracks/sections/labels | six preprocessing CSVs | failure and next gate | grain or lineage violation |

## 11PreprocessedDataQa.ipynb

| cellNo | type | purpose | moduleCall | input | output | display | failureCondition |
|---:|---|---|---|---|---|---|---|
| 1 | markdown | scope, provenance, and non-empirical warning | n/a | six preprocessing CSVs | data_quality_summary.csv | contract/release IDs | duplicate key, null required field, empirical provenance failure |
| 2 | code | parameters and path resolution | n/a | six preprocessing CSVs | data_quality_summary.csv | resolved read-only inputs | duplicate key, null required field, empirical provenance failure |
| 3 | code | validate inputs: QA/provenance guards | QA/provenance guards | six preprocessing CSVs | data_quality_summary.csv | validation summary | duplicate key, null required field, empirical provenance failure |
| 4 | code | execute stage: QA/provenance guards | QA/provenance guards | six preprocessing CSVs | data_quality_summary.csv | row counts and exclusions | duplicate key, null required field, empirical provenance failure |
| 5 | code | write/check output with deterministic schema | n/a | six preprocessing CSVs | data_quality_summary.csv | path, rows, SHA-256 | duplicate key, null required field, empirical provenance failure |
| 6 | markdown | interpret QA without empirical claims | n/a | six preprocessing CSVs | data_quality_summary.csv | failure and next gate | duplicate key, null required field, empirical provenance failure |
