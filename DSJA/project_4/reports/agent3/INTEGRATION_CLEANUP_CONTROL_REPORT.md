# P4 Integration Cleanup Control Report

- agentId = `P4-A3-CONTROL`
- agentName = `P4 SSOT Contract, Repository Hygiene & Control Plane Lead`
- audit date = `2026-08-06`
- status = `PARTIALLY_READY`
- canonical contract = `P4_CONTRACT_v2.1.2`

## Executive verdict

The contract control plane, contract consumer, pipeline foundation, and isolated
repository hygiene are ready. The current empirical corpus and both RQ data
paths are not ready. Contract v2.1.2 remains sufficient; the KSA policy and
source-policy evidence changes are documentation decisions, not schema changes.

Latest audited remote heads are:

| Agent | Branch | HEAD | Current disposition |
|---|---|---|---|
| Agent 1 | `agent/p4-crawl-release-v2` | `379fc1fc138fc8e84da2dd431a02ed5fcd866bed` | crawl candidate, empirical load rejected |
| Agent 2 | `agent/p4-pipeline-v2` | `71edc867a8e869b78340e4fe253ced9312894077` | pipeline/provenance foundation PASS |
| Agent 3 | `agent/p4-integration-cleanup-v2` | `3b4e8669f08b719b4f083d2a5e304a76b674610a` | clean integration base |
| Agent 4 | `agent/p4-ncs-mapping-v2` | `0b93d50893f76e51e24ca8328670c5aae59a2327` | base source ready; mapping foundation partial |

## Secret and API-key disposition

The scoped scan found no key material in tracked files, staged files, reachable
P4 Git history, notebook outputs, logs, fixtures, or manifests on Agent 1 or
Agent 4. Agent 4 has one ignored local `.env`; it is untracked, unstaged, absent
from reachable history, mode 0600, and was not modified by Agent 3.

- `REMOTE_SECRET_EXPOSURE = NONE`
- `LOCAL_ROTATION_REQUIRED = TRUE`

The old local key must be revoked or rotated. Authentication bypass, parameter
brute force, and reuse of the old key remain prohibited. No key value is
recorded in this report.

## Provisional KSA decision

`DATA_READY_RQ2B` should be decided by mapping precision, mapping coverage, and
the low-confidence gate, not by KSA existence alone. KSA is optional enrichment
and becomes a blocker only if the base mapping cannot meet those gates. This is
`PROVISIONAL_DECISION` pending user approval. It changes no table, field, DDL,
or metric contract, so v2.1.3 is not required.

Agent 4 has normalized the official 13,442-row NCS unit source and preserved an
empty gold template. The 120-code core AI/IT candidate contains 69 included
codes and remains `REVIEW_REQUIRED`. No live 15157547 KSA response, response
checksum, or observed-duty mapping exists. Its current 22-test suite passes.
Consequently:

- `NCS_BASE_SOURCE_READY = PASS`
- `NCS_BASE_MAPPING_FOUNDATION = PARTIAL`
- KSA dependency assessment = `KSA_REQUIREMENT_NOT_EVALUATED`
- `DATA_READY_RQ2B = FAIL`

## Source-policy evidence

Agent 1's transparent `httpx` reproduction, explicit research user agent, and
non-impersonated APQ/SSR request evidence close the former client-transparency
gap. The documented operating policy is at most one request per second,
concurrency at most two, stop on HTTP 403, and no external-ATS traversal.

The audited Agent 1 HEAD does not contain collector implementation evidence for
the concurrency cap or 403 kill switch. Source policy therefore remains
`REVIEW_REQUIRED`; canonical documentation is refreshed without changing the
v2.1.2 schema.

## Agent 2 observed-development audit

Agent 2 correctly isolated the previous synthetic warehouse:

- `p4.synthetic.duckdb`: 10,760,192 bytes; before/after SHA-256 and row counts
  match the quarantine manifest.
- canonical `p4.duckdb`: 2,895,872 bytes, 26 empty tables and six views;
  `qa.vAnalysisReadyGate` returns `NOT_EVALUATED`.
- production loaders fail closed without `contractVersion`, `crawlReleaseId`,
  `dataVersion`, and `dataProvenance=EMPIRICAL`.
- the provenance-related audit subset passed 15 tests; Agent 2 reports 93 tests
  passing at HEAD.

No `p4.observed-dev.duckdb` exists. The current Agent 2-to-Agent 4 duty handoff
is `SCHEMA_AND_FIXTURE_ONLY`, has one structural fixture row, and prohibits
empirical use. There is no
`AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json`. Canonical DB contamination is
zero, but observed-development parsing and mapping have not started.

## Crawl release audit

`CRAWL_20260806_03` is an immutable candidate, not a full production corpus.
Its 16 checksums pass, but 58 of 79 target months remain unverified, full-corpus
per-record raw HTML lineage is absent, and `asset_manifest.jsonl` is empty. The
Agent 2 full-release validator still rejects the manifest because required
source URL, raw path, and raw SHA-256 lineage are missing.

- source adapter = `SOURCE_ADAPTER_CONFORMANCE_ACCEPTED`
- empirical corpus = `EMPIRICAL_CORPUS_REJECTED`
- `CRAWL_RELEASE_READY = FAIL`

## Quarantine

Quarantine remains copy-only at
`/home/sieg/projects-wsl/P4_QUARANTINE_20260806`. All 38 manifest entries retain
matching before/after hashes and byte sizes, and all originals remain present.
Physical deletion remains prohibited until a full crawl release, rolling
integration build PASS, restore test, key rotation, and canonical replacements
are all confirmed.

## Gate dashboard

| Gate | Status | Basis |
|---|---|---|
| `CONTRACT_LINKED` | PASS | Agent 2 consumes canonical v2.1.2 and exact key tests pass |
| `PIPELINE_FOUNDATION` | PASS | provenance guards, empty canonical DB, reported 93 tests |
| `CRAWL_RELEASE_READY` | FAIL | 58/79 months unverified and record-level raw lineage missing |
| `NCS_BASE_SOURCE_READY` | PASS | official 13,442-row unit source normalized |
| `DATA_READY_RQ1_RQ2A` | FAIL | no accepted empirical parse, labels, dedup, or posting mart |
| `DATA_READY_RQ2B` | FAIL | no observed duties, gold labels, precision, or coverage gate |
| `ANALYSIS_READY` | FAIL | upstream empirical gates fail |

## Integration disposition

The rolling integration candidate may include Agent 2 foundation/provenance,
Agent 4 NCS base foundation, and Agent 3 contract/hygiene. Agent 1 raw-ignore
policy and APQ range-semantics commits are selective review candidates. The
current Agent 1 release must remain `EVIDENCE_ONLY` and must not be loaded as a
production corpus. Exact SHAs and conflict controls are in
`ROLLING_INTEGRATION_PLAN.md` and `.json`.

## Remaining defects

- P0: 58/79 target months are unverified; no full crawl release.
- P0: full-corpus record-level raw HTML lineage is absent.
- P0: the prior local API key still requires revoke/rotation.
- P1: source-policy concurrency and HTTP-403 kill-switch implementation evidence
  is missing.
- P1: no observed-development duty input, gold mapping, precision, or coverage
  result exists.
- P1: ActivityText embedded-image assets are not preserved in the release.
- P2: KSA source remains unverified, but is non-blocking enrichment unless base
  mapping fails the approved gates.
- P2: core AI/IT code set remains `REVIEW_REQUIRED`.

Final verdict: `PARTIALLY_READY`. A controlled rolling build is plan-ready; an
empirical integration or analysis release is not.
