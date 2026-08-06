# P4 Tier 1 index-canary approval packet

Decision ID: `D-T1-INDEX-CANARY`

## Question

승인된 작은 Linkareer index-only canary를 실제 network로 실행할까요?

## Current evidence

- Tier 0 canonical handoff: accepted checksum manifest `6162d3aea6ff3646d4d9cb7ff09d09acf91bbde81a815896096bca82b6f63c42`
- A1 source commit: `13205c11e7de3dfc7b005b0fde16197281eb857f`
- Tier 1 preapproval dry run: `10/11 PASS`
- Historical tracked crawl absolute-path inventory: `7` `PASS_WITH_FINDINGS`
  (pre-existing audit reports and negative-test literals; new preapproval tree findings: `0`)
- Network calls so far: `0`
- External ATS calls so far: `0`

## Proposed scope — not approved

- proposalStatus: `PROPOSED_NOT_APPROVED`
- candidateScopeId: `T1-INDEX-2026-03-APQ-V1`
- period: `2026-03`
- query operations: `CalendarScreen_ActivityCalendarEntries`, `CalendarScreen_Activities`
- proposed maximum index requests: `28`
- fixture-derived pagination depth: `27`
- estimated response storage: `8772876` bytes
- detail budget: `0`
- asset budget: `0`
- source: `LINKAREER` only
- external ATS: `false`
- browser automation: `false`
- query registry SHA-256: `7715d7170ec4d033c6ec257aee4eebd34381b12cfc2be891a3b8d61f8655782e`
- rate policy: `p4-linkareer-production-rate-v1` / `0f64f948b875a38434b4a05af31a0d3dee6115f2d0251b94dfe4129af79cdf92`
- kill-switch policy: `p4-linkareer-kill-switch-v1` / `0b197b71a0c46c8a2c49f716af5d0bdc2708fad3ce130e44ede6a3002e25300a`
- approval expiry recommendation: `PT2H_AFTER_APPROVAL`

These values are controller proposals only. They are not `approved*` fields and
do not open transport. The user-issued approval artifact must independently set
the exact scope, maximum request count, expiry, rate/retry budget, source and
source-policy human record.

## Recommendation

Approve one bounded Tier 1 index-only canary only after reviewing this proposal.

## Impact

- If approved: bounded index transport may begin; detail and asset requests remain forbidden.
- If denied: network remains at zero with no production-data impact.
- If deferred: automation remains `AWAIT_TIER1_APPROVAL`.

Full M2, production release, analysis, detail and asset promotion remain blocked.
