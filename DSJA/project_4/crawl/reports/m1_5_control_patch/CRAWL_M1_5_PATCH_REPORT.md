# P4 Crawl M1.5 control patch report

## Executive verdict

`CRAWL_M1_5_CONTROL_PATCH_READY_FOR_INDEPENDENT_AUDIT`

The crawl control/source patch is ready for independent audit. This is not a production promotion: `CRAWL_RELEASE_READY=false`, `SOURCE_POLICY_PRODUCTION_APPROVED=false`, and `M2_PRODUCTION_CRAWL=BLOCKED`.

## Git baseline

- branch: `agent/p4-crawl-m1_5-control-patch-v4`
- code HEAD before evidence publication: `a8c359cdcd39c799160730c2535f13531509b6a7`
- integration baseline: `b64270bd4ab839ec750a4ceceb08d57957c88782`
- audited Agent 1 source baseline: `3ad43c39dd01933575529e0c81d9809dc64c4e57`
- source import method: path-scoped restore; no divergent branch merge

## P1/P2 patch evidence

- Validator: exit code, status, artifact presence, runId, and input SHA must all match; negative tests `7/7 PASS`.
- Topology: registry-derived plan has `28/28 PASS` dependency edges; A4 producers precede A2-08/A2-09 and A2-09 precedes export/QA.
- Current run: `5/5` executed crawl stages have one canonical binding; stale/duplicate unit tests reject or preserve in `superseded_manifests`.
- Blob provenance: `6/6` crawl source Notebooks are tracked and their working blobs equal `HEAD` blobs.
- Source policy: `14/14 PASS`; production approval is still mandatory and no production transport was called.
- ActivityText: raw SSR replay `29/29 PASS`; ambiguous standalone auto-selection `0`.
- Lineage: 58 concrete remaining-month rows; 18 baseline raw-flag mismatches reconciled to verified raw-manifest authority with unresolved `0`; asset field/period lineage corrected.
- Runtime/idempotency: exact dependency lock published; two equal recovery runs produced identical SHA for all `8/8` content artifacts.

## Notebook integrity and blob provenance

| Notebook | bytes | source SHA-256 | cells | status |
|---|---:|---|---:|---|
| `00RecoverSourceState.ipynb` | 9373 | `c3fe68cf946e432df7610ba78452898c0fe62dfd5f9df8296d314a7990d1a257` | 11 | PASS |
| `01CollectLinkareerIndex.ipynb` | 9043 | `ea3454cca50c8e50b3d18406006f1f4fc83a705ba84134009cd3b42a2e3a95a2` | 11 | PASS |
| `02CollectPostingDetail.ipynb` | 9072 | `ca713dc03c421ba9ea900fa72062ceba6ef32ac2d7642789c59194a8e8be3de3` | 11 | PASS |
| `03CollectPostingAssets.ipynb` | 8850 | `6baf34bb0daefeb455b0da86e0eba3624a7016d11fb893ecaf46fabd8c2181f2` | 11 | PASS |
| `04BuildCrawlRelease.ipynb` | 9604 | `2b798d8f7983375660a808a496ea8fd844b615f3f02f7611c248fd39b6d0e6e0` | 11 | PASS |
| `P4_Notebook_First_Master.ipynb` | 11590 | `c25f201c9e2e9d722e7e2beb93e32ab330678550a0540fe9170bf13069309c0d` | 11 | PASS |

Total: `6/6 valid`, `66 cells`, source output/execution count `0/0`.

## Dependency graph before/after

- before: A2-08/A2-09 occurred before their A4 producers; 4 stage IDs were duplicated across 28 physical manifests and one manifest was stale `FAILED`.
- after: 28 registered edges pass; current-run consumers accept only exact stage/run/source/parameter/input/output/status/time bindings.
- Master dry-run: 23 planned children, 0 kernels started, 0 network calls. Full replay remains handoff-blocked because the clean integration baseline lacks 6 A4 and 2 A2 source Notebooks.

## Validator negative tests

`7/7 PASS`: nonzero exit, non-PASS status, missing artifact, stale runId, input SHA mismatch, malformed/full-corpus non-PASS all fail closed. Evidence: `CRAWL_VALIDATOR_NEGATIVE_TESTS.csv`.

## Source-policy and kill-switch tests

`14/14 PASS`: global interval/concurrency, 403, 429, recent success rate, unexpected content type, schema drift, empty-page streak, checkpoint corruption, external ATS rejection, and production approval guard. Evidence: `CRAWL_SOURCE_POLICY_TESTS.csv`.

## Fresh-kernel observed replay

| Stage | execution | manifest | checksum entries | network calls |
|---|---|---|---:|---:|
| A1-00-RECOVER | PASS | SUCCEEDED | 11 | 0 |
| A1-01-INDEX | PASS | SUCCEEDED | 7 | 0 |
| A1-02-DETAIL | PASS | SUCCEEDED | 7 | 0 |
| A1-03-ASSET | PASS | SUCCEEDED | 9 | 0 |
| A1-04-RELEASE | EXPECTED_BLOCKED | NOT_EVALUATED | 5 | 0 |

Replay totals: checksum failures `0`; index network calls `0`; external ATS transport calls `0`; source/executed code parity `5/5`.

## Security and portability

- tracked secret files: `0`
- tracked `.env`: `0`
- tracked raw PII files: `0`
- Notebook output secret files: `0`
- absolute local path artifact files: `0`

## Remaining blockers and owner handoff

- P4-A2-PIPELINE: adopt the ActivityText adapter contract and integrate validator plus Notebook 10/11 audited sources.
- P4-A4-NCS: integrate the six audited NCS source Notebooks.
- P4-A3-CONTROL: after those read-only owner handoffs, execute the full isolated 23-stage plan and require 23/23 exact-one manifests.
- User/source-policy owner: production network approval and transparent-client evidence remain absent.
- Data: 58 months are not pagination-audited and fetched assets remain 0; therefore crawl release and M2 stay blocked.

## Commands

- `P4_CRAWL_RAW_SOURCE_ROOT=<runtime-root> PYTHONPATH=DSJA/project_4:DSJA/project_4/crawl/src .venv/bin/python -m pytest -q DSJA/project_4/crawl/tests DSJA/project_4/crawl/control/tests` -> `58 passed`
- `.venv/bin/python DSJA/project_4/crawl/control/validate_control.py` -> `CONTROL_VALIDATION_PASS`
- `.venv/bin/python DSJA/project_4/crawl/scripts/execute_agent1_notebooks.py --run-root crawl/runs/notebooks/observed-dev/M1_5_AGENT1_20260806_01` -> 4 PASS + 1 EXPECTED_BLOCKED
- `.venv/bin/python DSJA/project_4/crawl/scripts/dry_run_master.py --output-root crawl/runs/notebooks/observed-dev/M1_5_AGENT1_20260806_01/master_dry_run` -> 28 edge PASS, 0 child kernels
