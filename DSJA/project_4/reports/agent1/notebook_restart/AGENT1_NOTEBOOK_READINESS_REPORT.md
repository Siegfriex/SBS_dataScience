# Agent 1 Notebook readiness report

agentId = P4-A1-SOURCE
agentName = P4 Source Acquisition & Coverage Engineer

## Verdict

`AGENT1_NOTEBOOK_INFORMATION_READY`

This is a READ_ONLY_AUDIT. No network request, API key, raw mutation, release publication, or merge was performed.

## Repository

- root: `/home/sieg/projects-wsl/worktrees/p4-agent1`
- worktree: `/home/sieg/projects-wsl/worktrees/p4-agent1`
- branch: `agent/p4-crawl-release-v2`
- local/remote HEAD: `6f5b44f18f286eca6507f20cae1a885ece30b6f2` / `6f5b44f18f286eca6507f20cae1a885ece30b6f2`
- ahead/behind: `['0', '0']`
- dirty before report generation: `False`

## Release inventory

| release | status | contract | coverage | raw manifest | assets | checksums |
|---|---|---:|---|---:|---:|---|
| RECON_20260806_01 | NOT_DECLARED | None | n/a | 0 | 0 | FAIL |
| CRAWL_20260806_01 | PARTIALLY_READY | None | {'unverified': 78, 'complete': 1} | 3 | 0 | PASS |
| CRAWL_20260806_02 | PARTIALLY_READY | 2.1.2 | {'unverified': 68, 'complete': 11} | 4 | 0 | PASS |
| CRAWL_20260806_03 | CRAWL_RELEASE_CANDIDATE | 2.1.2 | {'unverified': 58, 'complete': 21} | 32 | 0 | PASS |

## Code verdict

- Python files under `crawl/**`: 0
- notebooks under `crawl/**`: 0
- executable files under `crawl/**`: 0
- APQ, pagination, httpx policy, raw/manifest writers, asset collection, release build, and validator adapter are not reproducibly implemented in the branch.

## Source-policy gate

`REVIEW_REQUIRED`: rate and concurrency are policy text without code tests; no 403 or rolling success-rate kill switch exists; recon evidence records TLS impersonation rather than transparent httpx.

## Observed data

| metric | value | note |
|---|---:|---|
| monthlyCoverageRowsAll | 85 | includes six 2019 audit rows |
| monthlyCoverageRowsTarget | 79 | 2020-01..2026-07 |
| targetMonths.complete | 21 | filesystem recalculation |
| targetMonths.partial | 0 | filesystem recalculation |
| targetMonths.insufficient | 0 | filesystem recalculation |
| targetMonths.unverified | 58 | filesystem recalculation |
| monthlyDistinctIdSumComplete | 40551 | not a global distinct count |
| globalDistinctIds | NOT_COMPUTABLE | per-ID discovery corpus is absent |
| postingManifestRows | 137 | 137 unique sourcePostingId |
| rawHtmlFiles | 29 | filesystem count |
| rawHtmlCompressedBytes | 922111 | filesystem sum |
| assetFiles | 0 | filesystem count |
| assetManifestRows | 0 | empty |
| ocrCandidateRows | 113 | ActivityText embedded image OR poster; sample-only, not a manifest |

## Actually working commands

### Agent 1 branch audit

- workingDirectory: `/home/sieg/projects-wsl/worktrees/p4-agent1`
- command: `git status --porcelain=v2 && git rev-parse HEAD && git rev-parse origin/agent/p4-crawl-release-v2`
- expectedOutput: clean status and matching HEADs
- runtime/network: <1s / 0

### CRAWL_03 checksum

- workingDirectory: `/home/sieg/projects-wsl/worktrees/p4-agent1/DSJA/project_4/crawl/releases/CRAWL_20260806_03`
- command: `sha256sum -c CHECKSUMS.sha256`
- expectedOutput: 16 OK lines
- runtime/network: <1s / 0

### Contract checksum

- workingDirectory: `/home/sieg/projects-wsl/worktrees/p4-agent1/DSJA/project_4/shared/contracts/P4_CONTRACT_v2.1.2`
- command: `sha256sum -c CHECKSUMS.sha256`
- expectedOutput: 11 OK lines
- runtime/network: <1s / 0

The requested collection/batch/staging commands are all `NOT_IMPLEMENTED` in the current Agent 1 branch.

## Masked samples

Samples are in the JSON report under `maskedSamples`; raw bodies and manager contact fields are omitted.
