# P4 Tier 1/2/3 sequential canary preapproval packet

Status: `PREAPPROVAL_ONLY_NO_NETWORK_AUTHORITY`

## Bound Tier 1 proposal

- Source commit: `c17c7f5bc8c3eb1a9c1d12efb1eeb801f074f61c`
- Scope: `2026-03`, index-only APQ
- Proposed maximum index requests: `28`
- Tier 1 approval: `MISSING`

## Tier 2 detail proposal

- Status: `NOT_EVALUATED_AWAITING_TIER1_DISCOVERY`
- Sample size: `10`
- Frame: unique posting IDs from the accepted Tier 1 discovery manifest
- Seed: `SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)`
- Sampling: deterministic random without replacement
- Terminal failure replacement: forbidden
- Posting IDs selected now: `0`
- Proposed maximum detail requests: `10`

Tier 2 needs a new user approval after Tier 1 acceptance. This packet does not
select, invent or authorize any posting ID.

## Tier 3 Linkareer-hosted asset proposal

- Evidence: `59` checked-in metadata candidates across `137` postings
- Asset-bearing postings: `29`
- Per-posting mean: `0.430657`
- Conditional mean among bearing postings: `2.034483`
- Observed maximum per posting: `3`
- Proposed maximum asset requests: `10 × 3 = 30`
- Hosts: `api.linkareer.com`
- External ATS candidates/calls: `0/0`
- Fetched asset byte evidence: `0`; asset storage remains `NOT_EVALUATED`
- OCR: candidate queue metadata only; extraction and mapping calls `0`

Tier 3 needs another new user approval after Tier 2 acceptance. External hosts,
browser automation, OCR extraction, mapping and promotion remain forbidden.

## Storage evidence

- Tier 1 index estimate: `8772876` bytes
- Tier 2 detail upper estimate: `1692840` bytes, using observed max `169284` × 10
- Known pre-asset estimate: `10465716` bytes
- Asset and total reservation: `NOT_EVALUATED`

## Approval boundary

This document contains proposals only. It does not supply any approved scope,
budget, expiration, rate, retry, source-policy record or network authority.
