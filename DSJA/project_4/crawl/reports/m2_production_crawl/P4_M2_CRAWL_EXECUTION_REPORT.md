# P4 M2 production crawl preflight report

## Executive verdict

`M2_CRAWL_READY_FOR_USER_APPROVAL`

This is a network-zero approval handoff, not a production crawl or release. Production transport remains physically blocked because the signed approval artifact is absent and transparent-client evidence is still review-required.

## Git and authority

- branch: `agent/p4-crawl-m2-production-v1`
- preflight code HEAD: `c72f4e74dfbac23f56d97b12ebc5469f87895d4b`
- integration baseline: `aec8dfcb4cb6d57efc5a351874c2c32ba69abc0a`
- contract: `2.1.2` (latest tracked approved contract)
- authority prompt SHA-256: `bac3b50a9f8aa7930a26c095cb5dbb1362c6e009a90a4eb47d58204ed90bff39`

## Production preflight

- Month plan: `79` rows (`2020-01` to `2026-07`), SHA-256 `f7c2f57ff0bb0d2c2d7371e50ff4ee449ff3adca8afdbcd08816c16ee31c06da`.
- Baseline: `21/79` pagination-complete; `58` require approved collection.
- Query registry: `PASS`, two verified APQ operations, status filter omitted, OR/union semantics documented.
- Kill-switch/checkpoint tests: `14/14 PASS`, JUnit SHA-256 `86e4829acfefb54dbc13009b3fd52865d05393a2a45fb47c93dab56b5a98f9d7`.
- Full crawl/control regression: `52/52 PASS`, JUnit SHA-256 `1a0f023a0f680455bb6dede74c6246156037b4c046db3844454abfc4b05285c0`.
- Capacity estimate with 2x headroom: `31470697848` bytes; this is a planning estimate, not quota reservation.
- Production Linkareer network calls: `0`.
- External ATS transport calls: `0`.
- Tracked secrets/raw bytes: `0/0`.

## Execution boundary

Index, detail, asset, immutable release, and Agent2 validator stages are `NOT_STARTED` or `BLOCKED`. A signed artifact alone is insufficient: transparent-client source-policy evidence must also close before transport is enabled. `CRAWL_RELEASE_READY` remains blocked.

## User action

Review `P4_M2_CRAWL_USER_DECISION_PACKET.md`. If approved, add a schema-valid `crawl/control/PRODUCTION_APPROVAL.json`; then rerun this preflight before any network transport.
