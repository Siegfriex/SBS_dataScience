# P4 A1 Crawl Authority Reconciliation

## Executive verdict

`A1_RECONCILIATION_READY_FOR_A3_INTEGRATION`

This packet reconciles source and Notebook authority, proves portable external raw
resolution, and rebinds the offline M2 preflight. It does **not** approve or run a
production crawl and does not declare a crawl release or analysis ready.

## Identity

- branch: `agent/p4-a1-reconcile-crawl-authority-v1`
- baseCommit: `5508fce02ba5396b5d5a55870f1f879c1f32e8e0`
- headCommitAtGeneration: `92207e8fe7cc445c7426218da06b0b064f9df941`
- integrationCommit: `aec8dfcb4cb6d57efc5a351874c2c32ba69abc0a`
- crawlAuthorityCommit: `2d3f48025352359acf5787efeb79c0111fdea9f7`
- dataVersion: `observed-dev-reconciliation-20260807.1`
- runId: `A1_RECON_20260807_01`
- rawStorageRootId: `P4_RAW_OBSERVED_20260806_01`

## Reconciliation evidence

- Cloud crawl differences: **88/88 classified**, conflict 0, unexpected 0.
- Source Notebooks: **6/6 exact authority match**; source outputs 0; source execution counts 0.
- Fresh executed code parity: **6/6**. A1 00-03 passed; A1-04 and Master remained fail-closed rather than promoting an incomplete release.
- External raw mount: **29/29** objects matched compressed/content SHA and byte counts.
- Raw/posting binding: **11 MATCHED**, **18 QUARANTINED**, 0 silently corrected.
- DAG: 28 edges, cycles 0, ordering violations 0.
- M2 preflight: `PREFLIGHT_ONLY`; 79 month rows rebound; approval absent; production network 0; external ATS 0.
- Required tests: **19/19 PASS**.

## Promotion boundary

`M2_CRAWL_READY_FOR_USER_APPROVAL`, `CRAWL_RELEASE_READY`, `M2_PRODUCTION_CRAWL`,
all data-ready states, and `ANALYSIS_READY` remain unclaimed. The 18 observed posting
flag mismatches are explicit quarantine evidence, not production correction.

## A3 consumption

A3 should consume the reconciliation commits and the selected Notebook blobs, retain
generated evidence as evidence only, map `P4_RAW_OBSERVED_20260806_01` outside Git, and preserve
the quarantine denominator. No `pipeline/**`, `ncs_mapping/**`, or canonical shared contract
source was modified by this branch.
