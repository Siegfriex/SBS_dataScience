# P4 Combined Tier 1 / Detail 10 / Linkareer Asset Approval Packet

Decision ID: `D-T1T2-DETAIL-ASSET-CANARY`

## Question

Approve one bounded Linkareer index canary, a deterministic sample of 10 discovered postings, and only their Linkareer-hosted asset candidates?

## Current evidence

- Tier 0 canonical handoff: accepted
- A5 M1.5 audit: PASS_WITH_FINDINGS
- Combined preapproval validation: PASS_WITH_FINDINGS
- Network, detail, asset, external ATS and credentialed API calls so far: 0
- Actual 10 posting IDs: not selected; selection waits for the Tier 1 discovery manifest

## Controller proposal (not approved)

- Index scope: `{"periodMonths": ["2026-03"], "queryOperations": ["CalendarScreen_ActivityCalendarEntries", "CalendarScreen_Activities"]}`
- Maximum index requests: `28`
- Detail requests: `10`
- Detail sampling: deterministic random without replacement
- Terminal failure replacement: `false`
- Expected Linkareer-hosted candidates in evidence: `59` across `137` evidence postings
- Proposed maximum asset requests: `30`
- Asset cap method: DETAIL_SAMPLE_SIZE_X_OBSERVED_MAX_CANDIDATES_PER_POSTING
- Source: `LINKAREER only`
- External ATS: `false`
- Browser automation: `false`
- Raw retention: immutable content-addressed external storage; Git raw bytes forbidden
- OCR: queue, MIME, SHA and text-volume measurement only; extraction/mapping forbidden
- Query/rate/kill/source-policy SHA: inherited exactly from the accepted Tier 1 proposal
- Expiry suggestion: `PT2H_AFTER_APPROVAL`

## User-owned values still required

The approval artifact must set the exact approved scope, index/detail/asset budgets, expiry, rate limit, retry budget, source-policy human approval record, and storage-plan SHA. This packet sets none of those values.

Under the current automation policy, this is one combined decision packet, not one reusable transport authorization: Tier 2 and Tier 3 still require newly bound approval artifacts and new run IDs after their upstream acceptance gates.

## Impact

- If approved: only the exact bounded index, detail-10, and Linkareer-hosted asset measurement may run.
- If denied: all network calls remain zero.
- If deferred: automation remains in `AWAIT_TIER1_APPROVAL`.

This canary measures source recovery and asset availability only. It does not establish production coverage, OCR quality, NCS mapping quality, Human Gold, RQ findings, or article claims.
