# P4 Canary Acceptance Contract v1

This contract governs portable evidence accepted by the A3 global canary integration gate.

- It authorizes no network transport. A non-zero network ledger requires a separate, unexpired `production_crawl_approval.json` whose SHA is bound by `approval_binding.json`.
- Raw bytes remain in an external mounted root. Git accepts only redacted manifests, relative locators, hashes, counts, policy identifiers, and coverage.
- Missing mounts, wrong hashes, request-response conflicts, terminal request reissues, broken checkpoints, and post-kill-switch requests fail closed.
- Canary data is debugging evidence only. It cannot enter canonical/observed databases, marts, Gold/reference labels, or article artifacts.
- `CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE` does not imply any M2, crawl-release, production-data, NCS-quality, or analysis gate.

The deterministic request key is SHA-256 over the concatenation of logical request type, canonical JSON of `normalizedRedactedParameters`, and the applicable month/posting/asset identifiers. The canonical JSON is UTF-8, key-sorted, compact JSON. Its SHA must equal `requestParamsRedactedSha256`.
