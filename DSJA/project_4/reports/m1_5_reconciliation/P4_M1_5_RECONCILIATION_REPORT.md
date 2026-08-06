# P4 M1.5 Global Integration Reconciliation → M2 Gate

## Executive verdict

`BLOCKED_BY_EVIDENCE`

The maximum allowed state `M1_5_RECONCILIATION_READY_FOR_A5_AUDIT` is **not** declared. A1 and A2 are `REJECTED`; A4 is `EVIDENCE_INSUFFICIENT`. The 23-stage isolated replay and strict validator were correctly not invoked because every required handoff was not accepted.

## Authority

- agentId: `P4-A3-GLOBAL-INTEGRATION-RECONCILIATION-ORCHESTRATOR`
- branch: `integration/p4-m1_5-reconcile-for-m2-v1`
- audited base/head: `5508fce02ba5396b5d5a55870f1f879c1f32e8e0` / `e903d3a1d5f919cf7a117d8e351750ab9dc840f2`
- runId/dataVersion: `M1_5_RECONCILIATION_20260807_01` / `reconciliation-20260807.1`
- contractVersion: `2.1.2`
- production Linkareer calls: `0`
- external ATS calls: `0`
- report SHA-256: see `EVIDENCE_MANIFEST.json` (self-hash is not embedded)
- verified test commands: pipeline `116/116`, NCS `84/84`, integration `12/12`, A1 source branch `64/64`; consumed crawl candidate `70 passed, 8 failed`

## Agent handoff acceptance

| Agent | Ref | Verdict | Principal blocker |
|---|---|---|---|
| A1 | `agent/p4-crawl-m1_5-control-patch-v4@2d3f48025352359acf5787efeb79c0111fdea9f7` | REJECTED | source branch 64/64 passes, but consumed candidate has 8 control compatibility failures |
| A2 | `agent/p4-a2-semantic-m1_5-v4@879b2c2e2cf3ba3f3cdc8f0847e607f045e2b839` | REJECTED | canonical enum invalid 137/137; time/month/company 0/137; recovery is not wired to export |
| A4 | `agent/p4-a4-ncs-reference-v4@3396eb66f6f9af80d0458ab8c5431b1c5ce6414c` | EVIDENCE_INSUFFICIENT | no base-5508 v4 authority; mapping→level/band→mart output 0 |

No Agent branch was merged. The A1 commit sequence was cherry-picked as a compatibility candidate, then rejected after the integration test failed. Accepted Agent commits: none.

## Notebook authority

- physical source Notebooks: `27`
- registered observed bundle: `24` (`23` execution stages plus A3 Master)
- reconciliation execution stages: `23`
- analysis/article/support excluded: `3`
- latest A1 source SHA and Git blob exact match in integration: `6/6`
- source outputs/execution counts in candidate: `0/0`

## Raw authority

An explicit local mount independently resolves `29/29` objects and the original A1 suite passes `64/64`; those bytes are not Git authority. Git-only resolution is `0/29`, which means **unavailable**, not absent. Unmounted execution was independently verified fail-closed. Eighteen posting-flag drift rows remain quarantined. The integrated candidate additionally fails 8 compatibility tests.

## Canonical and NCS reconciliation

- canonical `postingKind` invalid: `137/137`
- canonical `canonicalPostedAt`, `periodMonth`, `companyKey` non-null: `0/137`
- separate deterministic recovery: valid enum `137/137`, date/month `29/137`; export consumption `0`
- `highDemandScore` non-null: `0`
- NCS official units: `13,442`; graph nodes/edges: `14,930/14,906`
- mapped codes joining official units: `27/27`; canonical mart level/band rows: `0`
- HUMAN_GOLD / dual coding / adjudication: `0/0/0`

## Replay and strict validator

`plannedStages=23`, `executedStages=0`, `exactOneManifests=0`. This is a fail-closed precondition outcome, not an empty-data PASS. `validatorInvoked=false`; there is no current-run validator SHA.

## Gate decision

`M1_5_RECONCILIATION_READY_FOR_A5_AUDIT`, `M1_5_RECONCILIATION_READY_FOR_M2_PREFLIGHT`, `M2_CRAWL_READY_FOR_USER_APPROVAL`, `CRAWL_RELEASE_READY`, and `ANALYSIS_READY` remain `BLOCKED`.

## Next admissible actions

1. A1 resolves the eight consumed-candidate control compatibility failures without removing the stronger base tests.
2. A2 publishes canonical export with deterministic recovery provenance and zero invalid enums.
3. A4 publishes v4 authority and mapping-to-mart handoff schema.
4. A3 re-runs this acceptance gate; only then may the isolated 23-stage replay and strict validator run.
5. A5 audits the resulting package in a separate worktree.

Notebook execution does not mean analysis data is ready. Structural QA does not prove semantic completeness. Observed-development output is not an article result. CSV is inspection/export only. NCS candidates are not a mapping quality gate.
