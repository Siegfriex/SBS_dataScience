# P4 M1.5 v4.0 Independent Audit

Status: `PASS_WITH_FINDINGS`

Candidate HEAD audited: `2b8a8ce` (base `9acf5b3` plus credential-state and API-evidence updates).

The audit ran in the separate `agent/p4-a5-m1_5-audit-v4` worktree. It made no network, production crawl, LLM, analysis, or article calls.

## Recalculation

- Evidence manifest: PASS for every listed artifact.
- Six stage checksum manifests: PASS.
- Control validator: PASS — 12 schemas, 6 endpoints, 6 stages, 26 gates, 11 dependency edges.
- Integration/control tests: 32/32 PASS.
- Pipeline tests: 116/116 PASS.
- NCS tests: 84/84 PASS.
- Crawl portable tests: 15/16 PASS. The sole failure requires the 29 ignored local raw SSR files; the independent Git worktree contains 0 raw files.
- Observed evidence: 137 postings, 29 authoritative timestamps, 18 raw declaration/existence mismatches, 84 source blocks, 277 chunks, 30 OCR candidate rows, 0 asset bytes.
- NCS candidate manifest: 13,442 units, 14,930 nodes, 14,906 edges, bridge 0, crosswalk 0, `promotionAllowed=false`.
- `highDemandScore` non-null: 0. Canonical DB table contamination: 0.
- New bundle tracked secret, email and absolute-path findings: 0.
- production Linkareer calls, live API probes, article-number generation: 0.

## Findings

1. `PASS_WITH_FINDINGS`: raw SSR bytes are intentionally ignored local authority. The tracked bundle is checksum-verifiable, but an independent Git-only worktree cannot reproduce the 29-raw semantic replay without separately transferring the raw authority.
2. `PASS_WITH_FINDINGS`: the original evidence manifest was generated at implementation HEAD `a2fe4fe`; the later credential-state and offline API evidence commits were outside that manifest. The final publisher must regenerate the manifest against the final candidate.
3. `NOT_EVALUATED`: live NCS/Work24 contracts, OCR extraction, human/LLM reference construction, dense model, temporal calibration, and production RQ2-B marts lack evidence. This is correctly fail-closed.

## Verdict boundary

The implementation is suitable for handoff to independent audit/replay, subject to the raw portability finding. No production, data-ready, analysis-ready, or release-ready promotion is supported.
