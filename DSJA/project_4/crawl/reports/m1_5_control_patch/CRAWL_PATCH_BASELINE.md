# P4 Crawl M1.5 control patch baseline

- Captured: 2026-08-06 (Asia/Seoul)
- Project root: `DSJA/project_4`
- Owned root: `DSJA/project_4/crawl`
- Patch branch: `agent/p4-crawl-m1_5-control-patch-v4`
- Integration baseline: `b64270bd4ab839ec750a4ceceb08d57957c88782`
- Audited Agent 1 source: `3ad43c39dd01933575529e0c81d9809dc64c4e57`
- Agent 2 source candidate (read-only): `9a0571dbcc0183960bda153baedcd0a2c9dc8248`
- Agent 4 source candidate (read-only): `7a9feccc7a2fc99b8b86b95bdb73699620bc7ff0`
- Baseline construction: clean integration worktree plus a path-scoped restore of Agent 1 crawl source, fixtures, observed input, and `CRAWL_20260806_03`. No branch merge was performed.
- Production network: forbidden for this patch and replay.

## Design evidence

The live `crawl/main_docs` directory is an input reference and is not copied into this branch. Its relevant Markdown checksums at baseline were:

| Document | SHA-256 |
|---|---|
| `P4_final_design_v4.0.md` | `409866c166ce3874ce587ad3b1230bc530c036e9682be01bf3466aa1fd37a05a` |
| `P4_Notebook_First_기능명세_데이터활용_기획서_v1.0.md` | `2585ce96dc24bff4a0cc9d61db108abaf221498f70760e56582af30e417f0f30` |
| `P4_local_development_handoff.md` | `8e8d5362b2949288ad88eb26d2aeb9c0c211b66fe8579fdb7b4da77e7c17682b` |
| `P4_prompt_crawl_orchestrator.md` | `d96d637d8076fb01e8daeb43a39e70132a9ea58603914408f0ecf2845292c2ec` |

The canonical `P4_CONTRACT_v2.1.2` source-policy gate remains fail-closed: missing evidence is `NOT_EVALUATED`, restricted evidence is `BLOCKED`, and transparent-client production evidence is still absent.

## Reconstructed data and execution state

- Source Notebooks: 6/6 valid, 66 cells, 0 source outputs, 0 execution counts.
- Observed postings: 137 rows / 137 unique IDs.
- Verified raw SSR manifest: 29 rows; baseline `hasDetailRawHtml=true`: 11 rows, hence 18 known flag mismatches.
- Target coverage: 21/79 complete and 58/79 pagination-unverified according to the immutable release handoff.
- Baseline asset manifest: 0 fetched rows.
- Existing tracked Master run: 28 physical stage manifests, 24 unique stage IDs, 4 duplicated IDs, 1 stale `FAILED` manifest.
- Existing Master order places A2-08/A2-09 before required A4 producers.
- Existing Agent 2 validator adapter can convert an execution exception into an eligible `PASS` Notebook gate.
- Runtime is inherited from the repository-level `.venv`; crawl-specific runtime dependencies were not locked.

## Promotion boundary

This baseline does not establish `CRAWL_RELEASE_READY`, `M2_PRODUCTION_CRAWL_READY`, `DATA_READY_RQ1_RQ2A`, `DATA_READY_RQ2B`, or `ANALYSIS_READY`.
