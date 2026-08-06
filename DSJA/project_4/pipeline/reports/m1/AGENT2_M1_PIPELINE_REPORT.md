# Agent 2 M1 observed-development pipeline report

Status: `PREPROCESSED_EXPORT_BUILT`

- Run mode: `observed-dev`
- Provenance: `OBSERVED_DEVELOPMENT_ONLY`
- Empirical analysis allowed: `false`
- Promotion allowed: `false`
- Observed warehouse: `pipeline/data/warehouse/p4.observed-dev.duckdb`
- Final review CSV: `pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01/preprocessed_posting_tracks.csv`
- QA: `17/17 PASS`
- Agent 3 termination schemas: `PASS`
- NCS candidates: `0` (`AWAITING_AGENT4_HANDOFF`)
- Recomputed posting rows: `137`
- Recomputed usable raw SSR rows: `29`
- Recomputed sections / requirements / duty handoff: `84` / `35` / `28`

The output bundle remains under `pipeline/data/exports` on the Agent 2 branch. Moving it to
`crawl/data/exports` is an integration action gated by the Agent 1 input package and Agent 3
contract/checksum audit.

This report does not declare any empirical, production-crawl, RQ, or analysis readiness state.
