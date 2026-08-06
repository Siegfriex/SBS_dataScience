# P4 Canary Crawl Debug Report — CANARY_T0_20260807_03

## Verdict

`CANARY_BLOCKED_BY_POLICY`

- agentId: `P4-A1-CANARY-CRAWL-ORCHESTRATOR`
- branch: `agent/p4-a1-canary-crawl-v1`
- headCommitAtRun: `d82df0878cc4c69aad40bda5b052e51021539130`
- canaryRunId: `CANARY_T0_20260807_03`
- approvalId: `NONE`
- runMode: `fixture-only`
- defectFamily: `POLICY_PORTABILITY_BASELINE`
- Tier 0: `15/15 PASS`
- networkCalls: `0`
- externalAtsTransportCalls: `0`

No Linkareer, external ATS, browser, or credentialed transport was opened. The
absence or invalidity of a canary approval blocks Tier 1 before transport. Runtime
artifacts contain only fixture-derived or empty redacted tables; raw bytes are not
Git authority and no canonical production root was written.

## Next scope

Provide a new, unexpired approval matching `CANARY_APPROVAL.schema.json`, with a
small period/query/request budget and hashes bound to the current query registry
and source-policy audit. A new canaryRunId is required.
