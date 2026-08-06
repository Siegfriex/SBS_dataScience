# P4 Automation Approval Queue

## D-CANARY-T1-001

- Question: Approve a separate Tier 1 Linkareer index-only network canary?
- Current evidence: Tier 0 fixture-only canonical handoff accepted; network calls remain 0.
- Requested scope: `USER_DECISION_REQUIRED`
- Request budget: `USER_DECISION_REQUIRED`
- Detail budget: `0`
- Asset budget: `0`
- Rate-limit policy version: `USER_DECISION_REQUIRED`
- Kill-switch policy version: `USER_DECISION_REQUIRED`
- Source-policy constraints: Linkareer index only; external ATS and browser automation denied.
- Expiration: `USER_DECISION_REQUIRED`
- Acceptance prerequisites: request conflicts 0; cursor loops 0; checkpoint resume, terminal page evidence, and kill-switch tests pass; external ATS calls 0.
- Recommended option: defer until a complete signed approval artifact is supplied.
- Impact if approved: only the approved Tier 1 index request scope may run.
- Impact if denied or deferred: network calls remain 0 and no scope expands.

This queue is not an approval artifact and authorizes no transport.
