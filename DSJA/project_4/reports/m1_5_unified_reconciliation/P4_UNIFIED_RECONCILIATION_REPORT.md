# P4 Unified M1.5 Reconciliation Report

## Executive verdict

`M1_5_RECONCILIATION_READY_FOR_A5_AUDIT`

This is an implementation-orchestrator result, not an independent A5 verdict. It does not authorize M2 crawl, a production release, an analysis mart, Gold promotion, article numbers, or any network transport.

## Authority chain

- Branch: `integration/p4-m1_5-unified-reconciliation-v2`
- Base: `5508fce02ba5396b5d5a55870f1f879c1f32e8e0`
- Evidence code head: `cb4f119fe447d151ecd70b6af534bda1a163d2ab`
- Latest A1 publication/code/baseline: `14ebe6beba530318dcedfd3471c7ba8565ee11f2` / `92207e8fe7cc445c7426218da06b0b064f9df941` / `2d3f48025352359acf5787efeb79c0111fdea9f7`
- A2 source candidate: `879b2c2e2cf3ba3f3cdc8f0847e607f045e2b839`
- A4 source candidate: `3396eb66f6f9af80d0458ab8c5431b1c5ce6414c`
- Run/data version: `M1_5_RECONCILIATION_20260807_03` / `reconciliation-20260807.3`

## Reconciliation result

- A1 latest handoff: ACCEPTED; 88/88 classified, Notebook authority 6/6, raw mount 29/29, raw binding 11 matched + 18 quarantined.
- A1 previous compatibility failures: 8/8 classified and superseded; current crawl tests 86 passed.
- A2 canonical export: 137 rows, invalid postingKind 0, dates/month/company 29 authoritative and 108 explicitly unresolved, period mismatch 0.
- Source lineage: source blocks 84, semantic chunks 277, requirements 41 with sourceBlock FK 41/41.
- A4: six-stage authority accepted; 27 structural level/band rows plus one UNMAPPED. Mapping quality remains NOT_EVALUATED and HUMAN_GOLD remains 0.
- Replay: planned 23, executed 23, exact-one manifests 23, stale 0, foreign 0.
- Strict validator: SUCCEEDED with 17 checks and 0 failures.
- Network: production Linkareer 0, external ATS 0, credentialed API 0.

## Test evidence

- `pytest crawl/tests crawl/control/tests -q`: 86 passed, exit 0.
- `pytest pipeline/tests -q`: 120 passed, exit 0.
- `pytest ncs_mapping/tests -q`: 87 passed, exit 0.
- strict validator: SUCCEEDED, exit 0.

## Non-promotions

`M1_5_RECONCILIATION_READY_FOR_M2_PREFLIGHT`, `M2_CRAWL_READY_FOR_USER_APPROVAL`, `CRAWL_RELEASE_READY`, `NCS_MAPPING_GOLD_READY`, and `ANALYSIS_READY` remain blocked.
