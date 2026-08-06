# P4 M2 crawl user decision packet

Status: `USER_DECISION_REQUIRED`

## D-M2-001 — Production Linkareer crawl approval

- Question: Approve the 2020-01 through 2026-07 Linkareer-only production crawl after the source-policy evidence condition is satisfied?
- Current evidence: 79-row plan ready; baseline `21/79` complete and `58` require collection; kill-switch tests `14/14` PASS; network calls `0`.
- Options: A approve after transparent-client evidence / B conditional limited-month approval / C defer.
- Recommendation: A only after `M2-P1-002` is closed; until then keep transport disabled.
- Impact: A opens the frozen plan; B must specify an exact month subset and cannot publish a full release; C preserves preflight only.
- May defer: yes.

## Required signed artifact

Create `crawl/control/PRODUCTION_APPROVAL.json` conforming to `crawl/control/PRODUCTION_APPROVAL.schema.json` with these fixed values:

```json
{
  "productionApprovalId": "<user-issued-id>",
  "approvedBy": "<user-identity>",
  "approvedAt": "<UTC timestamp>",
  "approvedPeriod": "2020-01~2026-07",
  "approvedSource": "Linkareer",
  "externalAtsTransportAllowed": false,
  "linkareerHostedAssetAllowed": true,
  "rateLimitPolicyVersion": "p4-linkareer-production-rate-v1",
  "killSwitchPolicyVersion": "p4-linkareer-kill-switch-v1"
}
```

Approval does not itself declare `CRAWL_RELEASE_READY`; 79-month, detail, asset, checksum, and strict Agent2 validator gates still must pass.
