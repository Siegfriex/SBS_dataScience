# Test commands and exit codes

Audited code commit: `f1fa16e5d4de097c39a35f89e23ffe29f781c3d8`

| Check | Command | Exit | Result | Evidence |
|---|---|---:|---|---|
| Full unit/schema/negative suite | `P4_CRAWL_RAW_SOURCE_ROOT=<local-runtime-root> PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests crawl/control/tests -q -rs` | 0 | 64 passed, 0 skipped | runtime command log; `f1fa16e5d4de097c39a35f89e23ffe29f781c3d8` |
| Validator and binding negatives | `pytest crawl/tests/test_validator.py crawl/control/tests/test_current_run_manifest.py -q --junitxml=.../validator-and-binding-negative.xml` | 0 | 18 passed | `crawl/runs/notebooks/observed-dev/POST_IMPL_AUDIT_20260806_01/test-results/validator-and-binding-negative.xml` SHA `8567d0b99bc985048aa80fa27afe42019bdc3c9d51e74aba9c0f5861cbcf9a30` |
| Source policy and kill switches | `pytest crawl/tests/test_policy.py crawl/tests/test_index_orchestrator.py crawl/tests/test_query_registry.py crawl/tests/test_assets.py -q --junitxml=.../source-policy.xml` | 0 | 18 passed | `crawl/runs/notebooks/observed-dev/POST_IMPL_AUDIT_20260806_01/test-results/source-policy.xml` SHA `d15e2cf01f5c11c5da4359c2218c61abca06853061cc3ac84fa43e793604a648` |
| Fresh 00-04 replay | `execute_agent1_notebooks.py --run-root crawl/runs/notebooks/observed-dev/POST_IMPL_AUDIT_20260806_01 --data-version observed-dev-20260806.2` | 0 | 4 PASS, 1 EXPECTED_BLOCKED | `crawl/runs/notebooks/observed-dev/POST_IMPL_AUDIT_20260806_01/NOTEBOOK_EXECUTION_RESULTS.csv` |
| Isolated Master replay | `execute_master_notebook.py --run-root crawl/runs/notebooks/observed-dev/POST_IMPL_MASTER_AUDIT_20260806_01 --data-version observed-dev-20260806.2` | 1 | EXPECTED_BLOCKED: integration baseline lacks required A2/A4 source Notebooks | `crawl/runs/notebooks/observed-dev/POST_IMPL_MASTER_AUDIT_20260806_01/NOTEBOOK_EXECUTION_RESULTS.csv` |
| Git whitespace validation | `git diff --check b64270bd4ab839ec750a4ceceb08d57957c88782...f1fa16e5d4de097c39a35f89e23ffe29f781c3d8` | 0 | PASS | Git object range |

The earlier unmounted-runtime invocation produced 63 passes and one explicit skip. It was not hidden; the final full suite was rerun with the local raw runtime root and produced 64 passes with zero skips.
