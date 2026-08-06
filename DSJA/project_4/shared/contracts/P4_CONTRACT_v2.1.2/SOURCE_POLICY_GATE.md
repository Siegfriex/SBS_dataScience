# P4 Source Policy Gate

- Agent ID: `P4-A3-CONTROL`
- Agent name: `P4 SSOT Contract & Control Plane Lead`
- Status: `canonical`
- Contract version: `2.1.2`
- Physical implementation: `qa.sourcePolicyAudit` and `qa.vSourcePolicyGate`

## Decision rule

Collection is eligible for a policy PASS only when all conditions hold:

1. `robotsStatus` is not `restricted`.
2. `termsStatus` is one of `reviewedConditional`, `permissionGranted`, or
   `permitted`.
3. `transparentClientVerified=true` for the routes and request shape actually
   used by the collector.
4. `collectionBlocked=false`.
5. `clientAccessMode` is not `impersonatedOnly`.

No evidence row produces `NOT_EVALUATED`, never PASS. A restricted robots or
terms decision, or an explicit collection block, produces `BLOCKED`.
`transparentClientVerified=false` or success only under browser impersonation
produces `REVIEW_REQUIRED`.

## Current Linkareer evidence

Agent 1 recon observed that `/calendar`, `/activity/*`, and `/list/*` were not
disallowed by the robots snapshot. The terms review is conditional rather than
unconditional permission. APQ and SSR requests were reproduced with
`curl_cffi(impersonate=chrome)`, so the contract does not promote source policy
to PASS until a declared transparent-client test succeeds for the production
request form.

External ATS destinations are recorded as Linkareer source metadata only. The
collector must not follow or scrape those external sites under this contract.

## Required evidence fields

`qa.sourcePolicyAudit` records source, policy version, robots status, terms
status, access mode, transparent-client verification, collection block,
verification timestamp, reviewer status, and notes. Release and analysis gates
must read the view rather than infer permission from robots alone.
