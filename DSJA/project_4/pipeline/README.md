# P4 pipeline

Independent preprocessing and analysis module for the Linkareer and NCS sources.

The pipeline never writes to `../crawl`. A crawl release is accepted only through
`../crawl/releases/CRAWL_*/HANDOFF.json`. Canonical contract bundles are discovered
version-agnostically under `../shared/contracts/P4_CONTRACT_v*/`. Contract v2.1.2
is checksum-verified, supported, and linked to the pipeline.

`data/warehouse/p4.development.duckdb` is fixture-only. The canonical
`data/warehouse/p4.duckdb` is bootstrapped from the v2.1.2 DDL. Its empty-data
analysis gate is `NOT_EVALUATED`, not `PASS`.

The legacy fixture database that previously occupied the canonical filename is
quarantined as `data/warehouse/p4.synthetic.duckdb`; its immutable inventory is
recorded in `reports/agent2/SYNTHETIC_DB_QUARANTINE.json`. Never restore it over
the canonical database. Canonical mart writes fail closed unless the caller
supplies `contractVersion=2.1.2`, an immutable `CRAWL_` release ID, a non-empty
`dataVersion`, and `dataProvenance=EMPIRICAL`.

`CRAWL_20260806_02` is accepted only for source-adapter conformance. It is not an
empirical corpus because 68 of 79 target months have unverified pagination and
per-record immutable detail HTML lineage is absent. Empirical marts, analyses,
and figures remain blocked until a full crawl release passes the strict validator.

`notebooks/*.ipynb` are production notebooks and intentionally contain no
executed outputs while the canonical inputs are blocked. Executed structural
checks live separately under `notebooks/fixture/` and carry an explicit
`SYNTHETIC_FIXTURE` provenance marker.

Current development commands:

```bash
cd DSJA/project_4/pipeline
../../.venv/bin/python -m pytest
../../.venv/bin/python scripts/validate_full_release.py \
  --handoff ../crawl/releases/CRAWL_<FULL_RELEASE_ID>/HANDOFF.json
```

Generated data under `data/` and `runs/` is local-only. Reports and handoffs
include hashes and row counts; no empirical P4 result is published from test
fixtures.

The pre-full-crawl duty input contract for Agent 4 is published at
`../shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT.json`. It contains schema and
synthetic fixture rows only; empirical RQ2-B mapping remains blocked.
