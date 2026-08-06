# P4 pipeline

Independent preprocessing and analysis module for the Linkareer and NCS sources.

The pipeline never writes to `../crawl`. A crawl release is accepted only through
`../crawl/releases/*/HANDOFF.json`, and the v2.1.0 machine-readable contract is
loaded from `../shared/contracts/P4_CONTRACT_v2.1.0`.

Current development commands:

```bash
cd DSJA/project_4/pipeline
../../.venv/bin/python -m pytest
```

Generated data under `data/` and `runs/` is local-only. Reports and handoffs
include hashes and row counts; no empirical P4 result is published from test
fixtures.

