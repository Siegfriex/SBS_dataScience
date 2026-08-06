# AGENT1 M1 Source Report

- Agent: `P4-A1-SOURCE`
- Branch: `agent/p4-crawl-release-v2`
- Contract: `2.1.2`
- Source release: `CRAWL_20260806_03`
- Observed package: `OBSERVED_INPUT_20260806_01`
- Run mode: `observed-dev`
- Data provenance: `OBSERVED_DEVELOPMENT_ONLY`
- Empirical analysis allowed: `false`
- Promotion allowed: `false`

## Result

```text
CRAWL_OBSERVED_INPUT_READY     = PASS
COLLECTOR_MODULARIZATION_READY = PASS
LIVE_PRODUCTION_CRAWL_EXECUTED = NO
CRAWL_RELEASE_READY            = NO
PUSH_STATUS                    = PUSH_BLOCKED_BY_UNRELATED_AHEAD_COMMIT
```

M1 Agent 1 work is ready for the Agent 2 observed parser handoff. This is not
a full-corpus release and cannot be promoted to an empirical-analysis input.

## Observed input package

Path: `crawl/observed_inputs/OBSERVED_INPUT_20260806_01/`

| Measure | Recomputed value |
|---|---:|
| posting manifest rows | 137 |
| distinct source posting IDs | 137 |
| detail fetch references | 32 |
| verified real raw SSR HTML | 29 |
| excluded masked-fixture references | 3 |
| asset manifest rows | 0 |
| NCS ability-unit rows | 13,442 |

Every included raw row was verified by decompressing the existing ignored
gzip file and comparing both uncompressed SHA-256 and byte count with the
source fetch manifest. Raw HTML was not copied. `raw_detail_manifest.jsonl`
contains only crawl-root-relative paths, SHA-256, bytes, URL, status, fetch
time, collector version, and source posting ID.

The three excluded fetch rows point to masked fixtures through paths outside
`data/raw/linkareer/detail/`; they are not counted as real raw HTML. The NCS
source manifest retains the 13,442-row ability-unit source and the explicitly
unavailable KSA source record.

Package checksum-file SHA-256:

```text
83d9beab338bebd6e9165d24ff246116e18b003345ed987ca33b64049379fdc9
```

Rebuilding with identical parameters produced the same checksum.

## Collector modularization

The former 19-cell implementation was split into:

```text
crawl/src/p4_crawl/
├─ config.py
├─ policy.py
├─ query_registry.py
├─ apq.py
├─ coverage.py
├─ detail.py
├─ assets.py
├─ storage.py
├─ manifests.py
├─ frontier.py
├─ release.py
├─ stage.py
└─ cli.py
```

The APQ operation hashes are loaded from
`crawl/configs/queryRegistry.yaml`; no Notebook contains an APQ hash. The CLI
has `recover`, `build-observed-input`, `release-readiness`, `index`, `detail`,
and `assets` commands. Live commands require both `runMode=production` and an
explicit `--execute-live` switch. They were not executed in M1.

Source policy is enforced before transport:

- global request start interval at least one second;
- concurrency limited to two;
- HTTP 403 trips a shared kill switch and queued work is cancelled;
- non-Linkareer/external ATS URLs are rejected before transport;
- only accepted response bodies enter content-addressed raw storage;
- manifest append is idempotent;
- log secret redaction helper is present.

## Thin notebooks

The deterministic renderer created these four-cell, output-free orchestration
notebooks:

```text
crawl/notebooks/00RecoverSourceState.ipynb
crawl/notebooks/01CollectLinkareerIndex.ipynb
crawl/notebooks/02CollectPostingDetail.ipynb
crawl/notebooks/03CollectPostingAssets.ipynb
crawl/notebooks/04BuildCrawlRelease.ipynb
```

The first code cell is tagged `parameters` and declares the common run
parameters. Collector implementations remain in `src/p4_crawl`. Each stage
writes `stage_manifest.json`, `stage_metrics.json`, `stage_quality.csv`, and
`CHECKSUMS.sha256` through the common stage helper.

The old 19-cell Notebook was absent from the current worktree at execution
time. A 62,814-byte, 19-cell, output-free copy at `/tmp` was audited as the
extraction reference only; it was neither copied nor treated as canonical.
The zero-byte `P4 Notebook-First.ipynb` was not reused as an executor.

## Validation

```text
pytest                                  10 passed
Python source AST                       23 files PASS
nbformat.validate                       5/5 PASS
Notebook code-cell AST                  5/5 PASS
Notebook source outputs                 0 across 5 notebooks
first cell parameter tag                5/5 PASS
observed package checksum verification  PASS
same-parameter package determinism      PASS
posting CSV/Parquet row and PK parity   137/137 PASS
tracked raw PII files                   0
new-source secret-pattern scan          0 findings
observed-package absolute paths         0 findings
git diff --check                        PASS
```

Tests cover the fake-clock interval, maximum concurrency, HTTP 403 kill and
queued cancellation, external ATS zero-call behavior, manifest idempotency,
frontier interruption recovery, query registry loading, asset host policy,
and the real observed-package counts/checksum.

## Git disposition and remaining blockers

An unrelated pre-existing commit, `d4669fe`, appeared on the branch during
implementation and changes files under `DSJA/project_4/reports/agent1/`.
Those files were preserved and never staged by this work. Agent 1 M1 changes
are eligible only for a narrow local `crawl/**` commit. Push is intentionally
blocked because pushing would also publish the unrelated ahead commit.

M2 remains blocked by 58 unverified months, incomplete full-corpus detail and
asset lineage, and the missing Agent 2 production validator pass.
