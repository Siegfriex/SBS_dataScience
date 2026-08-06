# Agent 2 final report

agentId = P4-A2-PIPELINE

agentName = P4 Contract-Driven Pipeline & Analysis Engineer

## Status

- `CONTRACT_LINKED`
- `BLOCKED_BY_FULL_CRAWL_RELEASE`
- `PIPELINE_FOUNDATION_READY`
- empiricalAnalysisAllowed: `false`

## Contract and warehouse

- Contract: `2.1.2`
- Contract SHA-256: `f92380cdfc16967f1e363800cd9a575e44532f18a86b2f28f8c3e2404ed675e9`
- DDL SHA-256: `956986874eae5686a20a52721dc303f1913c7391b2ee27da6d582a762f73ad58`
- Checksums: 11 PASS, 0 failures
- Canonical DDL: 39 statements; two executions identical
- Objects: 5 schemas, 26 tables, 6 QA views
- Empty `vAnalysisReadyGate`: `NOT_EVALUATED`
- Synthetic DB quarantine SHA-256: `4e08b5645747cfd21742480c32d87e50dcf5187ba5a1fa30f0e5bbca3883e03e`
- Canonical mart provenance guard: `contractVersion + crawlReleaseId + dataVersion + EMPIRICAL`

## Partial crawl conformance

- Release: `CRAWL_20260806_02` (`PARTIALLY_READY`)
- Acceptance: `SOURCE_ADAPTER_CONFORMANCE_ACCEPTED`
- Empirical corpus: `EMPIRICAL_CORPUS_REJECTED`
- Target coverage: 11 complete, 68 unverified
- Complete-month distinct postings: 11,825
- Detail sample: 126 success, 0 failure
- Per-record raw HTML lineage: absent
- NCS ability-unit records: 13,442

Sample rates are conformance diagnostics, not empirical findings: ActivityText 100.0%, external apply 99.2%, external detail only 19.0%, RQ1 100.0%, RQ2 81.0%, NCS 21.4%, conflict 0.8%, embedded-image OCR candidate 89.7%.

## Agent 4 duty input

- Status: `SCHEMA_AND_FIXTURE_ONLY`
- Schema: `agent2-duty-input-v1`
- Structural fixture rows: 1
- Empirical use allowed: `false`

## Verification

- Tests: 93 passed, 0 failed, 0 errors
- Production notebooks: 15, outputs 0
- Fixture notebooks: 15, all code cells executed
- Empirical marts, analysis, figures: not generated
