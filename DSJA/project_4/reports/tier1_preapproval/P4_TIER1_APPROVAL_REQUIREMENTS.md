# P4 Tier 1 Approval Requirements

Decision ID: `D-T1-INDEX-CANARY`

## Question

Approve one bounded Linkareer index-only network canary?

## Current evidence

- Tier 0 canonical handoff: accepted
- A5 M1.5 audit: PASS_WITH_FINDINGS
- Tier 1 preapproval dry run: PASS
- Network calls so far: 0
- External ATS calls so far: 0

## Controller proposal (not approved)

- Proposed scope: `{"periodMonths": ["2026-03"], "queryOperations": ["CalendarScreen_ActivityCalendarEntries", "CalendarScreen_Activities"]}`
- Proposed maximum index requests: `28`
- Estimated storage: `8772876` bytes
- Detail budget: `0`
- Asset budget: `0`
- Source: `LINKAREER only`
- External ATS: `false`
- Browser automation: `false`
- Query registry SHA: `7715d7170ec4d033c6ec257aee4eebd34381b12cfc2be891a3b8d61f8655782e`
- Rate policy: `p4-linkareer-production-rate-v1` / `0f64f948b875a38434b4a05af31a0d3dee6115f2d0251b94dfe4129af79cdf92`
- Kill-switch policy: `p4-linkareer-kill-switch-v1` / `0b197b71a0c46c8a2c49f716af5d0bdc2708fad3ce130e44ede6a3002e25300a`
- Source-policy evidence SHA: `e461f58e70bca86e4e16ddf1821829972cce77a7ab55ea7eeeea9a0d8e37bb3b`; human approval remains missing
- Storage estimate SHA: `768c55a963e8731d3843f28132fe6e86596576be363f24adadaebf9ace42be07`
- Expiry suggestion: `PT2H_AFTER_APPROVAL`

## Recommendation and impact

Recommendation: approve only this bounded Tier 1 index canary after issuing a complete signed approval artifact.

- If approved: index-only transport may begin within the exact approved scope; detail and asset remain denied; full M2 remains blocked.
- If denied: no network request occurs and Tier 1 remains blocked.
- If deferred: automation remains in `AWAIT_TIER1_APPROVAL`.

The user must independently set approved scope, maximum requests, expiry, rate/retry budget, source, and source-policy approval in `USER_TIER1_INDEX_CANARY_APPROVAL`. Until then all transport remains blocked.
