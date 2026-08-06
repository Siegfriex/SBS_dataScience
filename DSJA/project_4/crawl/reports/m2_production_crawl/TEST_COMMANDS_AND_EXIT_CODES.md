# P4 M2 preflight test commands and exit codes

| Check | Command | Exit | Result | Evidence |
|---|---|---:|---|---|
| M2 policy/month/checkpoint unit tests | `PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests/test_m2_preflight.py -q --junitxml=<temporary-junit>` | 0 | 14/14 PASS | `P4_M2_PREFLIGHT_TESTS.csv`, 14 rows, SHA `b4536e6ac7e35a67a2e4bbe14c4821e744f91e29e0ce43332b887ffdb3f64e13` |
| Full crawl/control regression | `P4_CRAWL_RAW_SOURCE_ROOT=<ignored-runtime-root> PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests crawl/control/tests -q -rs --junitxml=<temporary-full-junit>` | 0 | 52/52 PASS | `P4_M2_FULL_REGRESSION_TESTS.csv`, 52 rows, SHA `843cea3c37b6bba3586e9fc13dc844f8b696440fc79c7073b0847e5cdfd0119c` |
| Network-zero preflight build | `PYTHONPATH=crawl/src:. .venv/bin/python crawl/scripts/build_m2_preflight.py --raw-source-root <ignored-runtime-root> --junit <temporary-junit> --full-junit <temporary-full-junit> --authority-prompt <Prompt-A>` | 0 | 79 month rows; transport 0 | `M2_PREFLIGHT_MANIFEST.json`, SHA recorded in `EVIDENCE_MANIFEST.sha256` |

Git commit at generation: `c72f4e74dfbac23f56d97b12ebc5469f87895d4b`. Production Linkareer and external ATS transports were not invoked.
