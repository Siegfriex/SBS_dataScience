# P4 Integration Cleanup Control Report

- agentId = `P4-A3-CONTROL`
- agentName = `P4 SSOT Contract, Repository Hygiene & Control Plane Lead`
- status = `PARTIALLY_READY`
- contractVersion = `2.1.2`
- audit date = `2026-08-06`

## Executive verdict

The canonical contract and its Agent 2 consumer are aligned on the isolated
`agent/p4-integration-cleanup-v2` branch. The documentation repository remains
clean at `878386ac233403e75fcdab65574c65a09b5e69fa` and tag
`contract-v2.1.2`. The cleanup branch contains Agent 2 commits through
`a92eb91` as isolated cherry-picks and passes all contract, DDL, and test gates.

The project is not empirically ready. Agent 1's `CRAWL_20260806_02` is a valid
partial release with 14/14 checksums passing, but only 11 of 79 target months
have complete pagination verification. Per-record raw detail lineage is also
missing. The release handoff has an empty `head_commit`, and the reported
`AGENT1_TO_AGENT3_ISSUES.json` is absent from commit `825ba03`.

No Agent 1 or Agent 2 protected worktree file was moved or deleted. The legacy
quarantine is copy-only, so the dirty Agent 2 worktree remains dirty by design.

## Repository and worktree state

- docs repo: clean, `main`, HEAD `878386ac`, tag `contract-v2.1.2`
- Agent 1: clean and pushed, HEAD `825ba03`
- Agent 2 branch: HEAD `a92eb91`; 32 tracked notebook/builder changes remain
  uncommitted in its active worktree
- cleanup branch baseline after controlled cherry-picks: `d3e3deb`
- monorepo-wide porcelain entries: 12,216; outside-P4 entries were not touched
- P4 porcelain entries in the active Agent 2 worktree: 110

## Dirty inventory

The inventory contains 289 physical files at the Agent 2 source snapshot:

| Classification | Count |
|---|---:|
| AGENT2_COMMITTED | 123 |
| CONTRACT_SNAPSHOT | 13 |
| HANDOFF_CURRENT | 4 |
| DUPLICATE_IDENTICAL | 31 |
| OBSOLETE_SUPERSEDED | 7 |
| EVIDENCE_UNREGISTERED | 1 |
| SKELETON_REUSABLE | 32 |
| RUNTIME_IGNORED | 77 |
| SECRET_LOCAL | 1 |

Git-state counts at the inventory snapshot were 106 tracked-clean files, 32
tracked-modified files, 74 untracked files, and 77 ignored files. The unique
legacy evidence is the 1,374-byte `configs/sources.yaml`; Agent 1 must decide
whether any non-superseded content should be republished under its ownership.

## Quarantine

- final path: `/home/sieg/projects-wsl/P4_QUARANTINE_20260806`
- copied files: 38
- duplicate-identical: 31
- obsolete-superseded: 7
- source disposition: `SOURCE_RETAINED`
- manifest SHA-256:
  `319e3850f56220e9c2735657dc7c1110d2f1ea4c8e12b2102bb2f78c8832be8b`
- checksum file SHA-256:
  `9c60d69d6154071a405ba75dfbf2b79712d24ff78970c91f3d3fbf15f8027c32`
- restore instructions SHA-256:
  `62edbd8f0205b1138b85c568d5fa66cff68339619e7a7683a8026eeed1305957`

All before/after SHA-256 values and byte sizes match. Two earlier Agent 3-only
quarantine drafts were retained under `*_SUPERSEDED_DRAFT*`; they contain no
source deletion. No automatic action was taken on skeletons, runtime files,
the local secret, or unique evidence.

## Contract consumer

The v2.1.2 contract directly defines SHA-256, UTF-8, the `|` separator, 20 hex
characters, prefixes, input order, and formulas. Therefore the original loader
failure was `CONTRACT_CONSUMER_DRIFT`; a v2.1.3 contract is not required.

Agent 2 resolved this in commits `98dd7e8`, `608c1a1`, and `a92eb91`; controlled
integration equivalents are `f0445d8`, `9a6ddfe`, and `d3e3deb`. Exact key
tests pass, including:

- `postingId(linkareer,123) = PST_8a245070a5ece697d6cf`
- `rawPostingId(linkareer,123,a*64) = RAW_1ffe6e05045f37a6271f`
- `trackId(PST_demo,0) = TRK_7bcc98532a391ab10796`

## Agent 1 release audit

- release: `CRAWL_20260806_02`
- branch/HEAD: `agent/p4-crawl-release-v2` / `825ba03`
- contractVersion: `2.1.2`
- checksums: 14/14 PASS
- coverage rows: 85
- complete: 11; unverified: 68; partial out-of-range: 1; insufficient
  pre-launch: 5
- target-month pagination: 11/79 complete
- detail sample: 126/126 successful
- source adapter: `SOURCE_ADAPTER_CONFORMANCE_ACCEPTED`
- empirical corpus: `EMPIRICAL_CORPUS_REJECTED`

The new transparent-http evidence makes the current evidence paragraph in
`SOURCE_POLICY_GATE.md` stale, but the gate rule and schema remain valid. The
evidence row/document should be refreshed without changing contract v2.1.2.

## Git hygiene and runtime

The scoped `.gitignore` protects `.env`, Python/test caches, notebook runtime
state, raw/interim/warehouse/runs, and DuckDB files. `.env.example` is explicitly
trackable and contains placeholders only. Gold and mart outputs are not blanket
ignored; their release policy remains contract-owned.

The local `.env`, two DuckDB files, two synthetic mart parquet files, pytest
cache, Python caches, and pytest XML were preserved. Production notebook output
count is 0; fixture notebook output count is 45; notebook absolute `/home/sieg`
paths are 0. Secret-pattern scan of Agent 3 additions returned no findings.

## Validation evidence

- contract release checksum: PASS
- DuckDB version: 1.5.4
- DDL statements: 39
- schemas/tables/views: 5/26/6
- cross-schema physical FK: absent by contract design
- DDL first and second bootstrap: PASS, identical inventory
- all six QA views execute
- empty database gate: `NOT_EVALUATED`, not data-quality PASS
- Agent 2 tests: 83 passed
- Agent 3-owned diff check: PASS
- full historical branch diff check: inherited EOF blank-line warnings remain
- production notebook outputs: 0
- absolute user paths in notebooks: 0

## Integration plan

1. Use `agent/p4-integration-cleanup-v2` as the contract-consumer integration
   base; it includes Agent 2 through `a92eb91` plus the v2.1.2 snapshot.
2. Integrate Agent 1 source commits `047b453`, `bec745b`, `8864092`, `3330705`,
   and `825ba03` in order.
3. Skip Agent 1 commits `f94e8aa` and `8fc16f9` because they are patch-equivalent
   contract/handoff vendors already present in the cleanup branch.
4. Do not include the 32 uncommitted Agent 2 notebook/builder edits until Agent 2
   publishes a clean logical commit and tests it.
5. Keep empirical analysis disabled until monthly coverage and raw-detail lineage
   gates are explicitly satisfied or the analysis scope is reduced by decision.

## Remaining blockers

- P0: 68/79 target months lack pagination verification; empirical corpus rejected.
- P0: detail release lacks per-record raw HTML lineage; derived-only capture is
  insufficient for reproducible parse/OCR.
- P0: embedded ActivityText image routing affects 89.7% of the measured sample;
  poster-file-only OCR routing is invalid.
- P1: `CRAWL_20260806_02/HANDOFF.json.head_commit` is empty.
- P1: reported `AGENT1_TO_AGENT3_ISSUES.json` is absent from Agent 1 HEAD.
- P1: source-policy evidence prose predates the transparent httpx verification.
- P1: NCS KSA source requires a human API key and remains unverified.
- P2: Agent 2 active worktree has 32 uncommitted notebook/builder changes.
- P2: inherited Agent 2 baseline files contain EOF blank-line warnings; Agent 3
  did not rewrite another owner's paths.
- P2: recruit start/close range combination semantics remain unresolved.

Final verdict: `PARTIALLY_READY`. The contract control plane and isolated
integration branch are technically sound; the empirical release and the active
Agent worktree hygiene are not yet release-ready.
