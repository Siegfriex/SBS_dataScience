# P4 pipeline

Independent preprocessing and analysis module for the Linkareer and NCS sources.

The pipeline never writes to `../crawl`. A crawl release is accepted only through
`../crawl/releases/CRAWL_*/HANDOFF.json`. Canonical contract bundles are discovered
version-agnostically under `../shared/contracts/P4_CONTRACT_v*/`; v2.1.2 is the
current target but is not treated as supported until its full checksum-verified
bundle arrives.

`data/warehouse/p4.development.duckdb` is fixture-only. The canonical
`data/warehouse/p4.duckdb` is not bootstrapped without an executable contract.

Current development commands:

```bash
cd DSJA/project_4/pipeline
../../.venv/bin/python -m pytest
```

Generated data under `data/` and `runs/` is local-only. Reports and handoffs
include hashes and row counts; no empirical P4 result is published from test
fixtures.
