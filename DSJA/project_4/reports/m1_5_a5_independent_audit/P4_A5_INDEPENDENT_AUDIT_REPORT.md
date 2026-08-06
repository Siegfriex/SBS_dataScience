# P4 M1.5 A5 Independent Audit

## Executive verdict

`PASS_WITH_FINDINGS`

A5 independently recalculated the `_06` reconciliation evidence from branch `audit/p4-m1_5-a5-unified-v1` at integration base `f30f1a386895ac4f165ed390ee038a833c2a8012`. No production Linkareer, external ATS, or credentialed API call was made.

This verdict introduces no new P1. It does not promote M2, a crawl release, NCS quality, or analysis readiness. A3 may review the M2-preflight gate, but A5 does not declare it ready.

## Scope and independence

- Audited integration run: `M1_5_RECONCILIATION_20260807_06`
- Data version: `reconciliation-20260807.6`
- A5 worktree was separate from the implementation worktree.
- Implementation source was not edited.
- The original `_06` native A1/A2 runtime was mounted read-only only to rehash 17 native manifests.
- Audit scripts and evidence were written only below `reports/m1_5_a5_independent_audit/`.

## 1. A4 deterministic runner

All six A4 stages were executed again in independent processes using the current audit worktree.

- Source Notebook SHA: 6/6 matched the `_06` ledger; Git blob IDs were recalculated.
- A4 module-tree SHA: 6/6 matched `6a2b0eed448675fbf898dd5a852744481adc04a86f3b0526fafb1af65daeb6e6`.
- Canonical result SHA: 6/6 matched the `_06` ledger.
- A4-05 independently returned `NOT_EVALUATED` with Gold rows 0.

The runner executes current Python modules, but it does not execute the six source Notebook bytes. The Notebooks are SHA-bound only. A portable search over 32 contract, SSOT, registry, gate, and Notebook-spec authority files found zero explicit clauses authorizing this runner as equivalent to fresh-kernel Notebook execution. Therefore substitution equivalence remains `NOT_EVALUATED`, recorded as `A5-P2-001`.

Evidence: `P4_A5_A4_RUNNER_AUDIT.csv`, SHA-256 `e882804854c89989fa1f0055c00832eb0f7dd8f20534322ae6ddea3d60e04b2a`; `P4_A5_CONTRACT_REGISTRY_SEARCH_AUDIT.csv`, SHA-256 `e17e8f31d04d798a241f556d331efab79869e39a718994bb4b5f5ac568ae8df3`.

## 2. A1-04 to A2-00 access isolation

A2-00 was executed in a new fresh kernel with a Python audit hook installed before pipeline imports.

- `OBSERVED_INPUT_20260806_01/HANDOFF.json` was actually opened 4 times.
- Its SHA matched the stage manifest: `f58810b38bde7c7e1c69bf1f7000b3931cadf9d4d544f64b9c9c0d27a63bce8e`.
- The validator also opened the package members referenced by the HANDOFF, including checksums, posting manifests, known gaps, raw-detail manifest, and NCS source manifest.
- Access to `crawl/runs/**`, `crawl/releases/**`, and the tracked A1-04 reconciliation stage output was 0.
- The A2-00 stage completed `SUCCEEDED`.

This proves the current implementation consumes the HANDOFF-rooted observed package and does not implicitly read an A1-04 release artifact. It does not resolve the registry semantics: A2-00 still has A1-04 as a generic dependency. The same 32-file portable authority search found zero explicit clauses permitting A2-00 execution when A1-04 is `NOT_EVALUATED`. `A5-P2-002` remains open.

Evidence: `P4_A5_A1_A2_ACCESS_AUDIT.csv`, SHA-256 `e9a25dd0010e901fd033e7d5e1d1d2f2cea8eeb9428fc016a7c28195d1136d39`; portable access log SHA-256 `c6fb19b3f99d7e2afa5bf30d393b2724d45811c333b4823c8fc1fc85e7d08e34`; contract/registry search SHA-256 `e17e8f31d04d798a241f556d331efab79869e39a718994bb4b5f5ac568ae8df3`.

## 3. Raw authority

- Mounted: 29/29 objects matched compressed SHA, content SHA, and byte-count policy.
- Unmounted: 29/29 returned `RAW_ROOT_UNMOUNTED`, downstream consumption false.
- Wrong SHA: the tampered row returned `COMPRESSED_SHA_MISMATCH` and `QUARANTINED`.
- Missing object: the row returned `RAW_OBJECT_MISSING` and `QUARANTINED`.
- Raw-to-posting binding: 11 `MATCHED`, 18 `QUARANTINED`, silent correction 0.

Evidence: `P4_A5_RAW_MOUNT_AUDIT.csv`, SHA-256 `76819d4905d16f32c161ab39606ee993312200bf86bf440bf15322834a9b67ac`.

## 4. DAG, timestamps, and SHA bindings

An A5-local dependency map was used instead of importing the integration validator.

- Exact DAG dependencies: 23/23.
- Producer order and producer-complete before consumer-start: 23/23.
- Non-reversed runtime timestamps: 23/23.
- Current source Notebook and module-tree SHA: 23/23.
- Ledger-to-global-manifest input/output/command/timestamp binding: 23/23.
- A1/A2 native manifests independently rehashed from the read-only `_06` runtime: 17/17.
- A4 outputs independently reproduced: 6/6.

Evidence: `P4_A5_DAG_SHA_AUDIT.csv`, SHA-256 `0a398d571cf5840447d354c23a0c5881941afce74216b6624dd56f9c7f119b31`.

## 5. Canonical unresolved policy

The observed semantic batch was regenerated independently from the observed package and mounted raw authority.

- Rows: 137.
- `canonicalPostedAt`: 29 present, 108 explicit unresolved.
- `periodMonth`: 29 present, 108 explicit unresolved; mismatch 0.
- `companyKey`: 29 present, 108 explicit unresolved.
- Silent date/company null without reason: 0.
- Invalid `postingKind`: 0.
- Non-null `highDemandScore`: 0.
- Regenerated semantic SHA: `1b5c70f15a2e1e04d11a55b07964e9ac75ee013caf8683f6c4bebaae0859878b`.

Evidence: `P4_A5_CANONICAL_POLICY_AUDIT.csv`, SHA-256 `9e6e29b094bc8057a7e8e115c5c858db9cd380469a94778dcd170cba03cbf768`.

## 6. Tests

| Suite | Result |
|---|---:|
| A2-00 fresh-kernel access audit | PASS |
| A5 independent recalculation | 52 checks, 0 failed |
| Crawl | 86 passed |
| Pipeline | 120 passed |
| NCS mapping | 87 passed |
| Integration | 17 passed |

All commands exited 0. Full pytest stdout and exit codes are retained as `PYTEST_CRAWL.log`, `PYTEST_PIPELINE.log`, `PYTEST_NCS.log`, and `PYTEST_INTEGRATION.log`; their SHA values are bound in `P4_A5_TEST_SUMMARY.csv`. Network counters remained zero.

## Gate conclusion

```text
M1_5_RECONCILIATION_DAG_VALID              = PASS
M1_5_RUNTIME_TIMESTAMP_VALID                = PASS
M1_5_RECONCILIATION_READY_FOR_A5_AUDIT      = PASS_WITH_FINDINGS
M1_5_RECONCILIATION_READY_FOR_M2_PREFLIGHT  = NOT_EVALUATED_BY_A5
M2_CRAWL_READY_FOR_USER_APPROVAL            = BLOCKED
CRAWL_RELEASE_READY                         = BLOCKED
ANALYSIS_READY                              = BLOCKED
```

The A5 audit is sufficient for A3 to review the M2-preflight gate because it found no new P1. Existing P1-UNIFIED-001 through P1-UNIFIED-005 remain open and continue to block the corresponding production, NCS-quality, M3, and analysis promotions.
