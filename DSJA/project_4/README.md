# SBS P4 project workspace

This workspace separates source collection from processing:

- `crawl/`: Agent 1 owned, read-only to the pipeline implementation.
- `pipeline/`: Agent 2 preprocessing, DuckDB, marts, analysis, and notebooks.
- `shared/contracts/`: Agent 3 machine-readable contracts.
- `shared/handoffs/`: cross-agent requests and validation issues.

The pipeline currently has no v2.1.0 contract bundle and no immutable Agent 1
crawl release. Synthetic fixtures are limited to software verification and must
not be interpreted as Linkareer or NCS observations.

