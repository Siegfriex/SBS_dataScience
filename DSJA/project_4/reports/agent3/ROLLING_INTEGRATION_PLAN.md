# P4 Rolling Integration Plan

- agentId = `P4-A3-CONTROL`
- agentName = `P4 SSOT Contract, Repository Hygiene & Control Plane Lead`
- audit date = `2026-08-06`
- canonical contract = `P4_CONTRACT_v2.1.2`
- integration base = `agent/p4-integration-cleanup-v2@3b4e8669f08b719b4f083d2a5e304a76b674610a`
- plan status = `READY_FOR_CONTROLLED_BUILD`

No cherry-pick or merge was executed by this audit. The plan separates code and
foundation commits from evidence-only crawl releases.

## Audited source heads

| Agent | Branch | Remote HEAD | Disposition |
|---|---|---|---|
| Agent 1 | `agent/p4-crawl-release-v2` | `379fc1fc138fc8e84da2dd431a02ed5fcd866bed` | adapter evidence selectable; corpus rejected |
| Agent 2 | `agent/p4-pipeline-v2` | `71edc867a8e869b78340e4fe253ced9312894077` | foundation selectable |
| Agent 3 | `agent/p4-integration-cleanup-v2` | `3b4e8669f08b719b4f083d2a5e304a76b674610a` | integration base |
| Agent 4 | `agent/p4-ncs-mapping-v2` | `0b93d50893f76e51e24ca8328670c5aae59a2327` | base-source foundation selectable |

## Proposed commit order

1. Start from Agent 3 commit `3b4e8669f08b719b4f083d2a5e304a76b674610a`.
2. Cherry-pick Agent 2 commits in order:
   `9ca7a43dfd55aea2528ed72e2a3535ef7f10624e`,
   `649d87946d5a04974983adf55676c0becb050b2a`,
   `636653dc911e6cb5ff888f0c0a0a64976dd8e765`, and
   `71edc867a8e869b78340e4fe253ced9312894077`.
3. Cherry-pick Agent 4 commits in order:
   `c9aca9ff08346dc413c5f3ad245575a2eb2ccfb0`,
   `0e289923c16a21df54fc5038d831a25258cea92c`,
   `cd0feeb9e118bbb461711b219cb2dfd5a4bd726f`, and
   `0b93d50893f76e51e24ca8328670c5aae59a2327`.
4. Review Agent 1 metadata commits separately:
   `729734cbc45340a31cccdbc6698b1e580de228c7` for raw-data ignore policy and
   `45dbfb2a9ae9f0da510dce2d9afaa34f69cbb6b1` for APQ range semantics.
   Commit `f0a46da28818280f14dc9d0c1786b5b54da33be5` is evidence-only because KSA
   live records remain unverified.
5. Do not promote or load `379fc1fc138fc8e84da2dd431a02ed5fcd866bed`
   (`CRAWL_20260806_03`) as a production corpus. It may be retained as an
   immutable evidence candidate only.

Commits `98dd7e8`, `608c1a1`, `a92eb91`, `f94e8aa`, `8fc16f9`, `fcd0ea7`, and
`5815375` are excluded because their contract or handoff content is already
patch-equivalent on the Agent 3 base.

## Expected conflicts and controls

| Paths | Expected risk | Control |
|---|---|---|
| `pipeline/README.md`, Agent 2 reports and handoffs | medium; commits 636653d and 71edc867 both refresh generated reports | preserve Agent 2 commit order and regenerate reports after tests |
| `pipeline/notebooks/**` | medium; generated binary JSON notebooks | semantic notebook validation and output-count check, no manual merge |
| `shared/contracts/P4_CONTRACT_v2.1.2/**` | high if Agent 4 vendor commits are included | skip duplicate vendor commits; retain Agent 3 hashes |
| `shared/handoffs/AGENT3_*` | high if Agent 1/4 vendor commits are included | skip duplicate vendor commits; retain Agent 3 handoffs |
| `ncs_mapping/**` | low; additive on current base | verify no local `.env` is staged and rerun NCS tests |
| `crawl/**` | medium; active Agent 2 checkout has legacy untracked copies | integrate only in the clean cleanup worktree; never overwrite untracked evidence |
| `crawl/releases/CRAWL_20260806_03/**` | policy risk | classify `EVIDENCE_ONLY`; prohibit warehouse load |

## Build gates after each stage

- Contract checksum parity and DuckDB bootstrap must remain PASS.
- Agent 2 test suite must pass with canonical and observed-development
  provenance guards enabled.
- Agent 4 tests must pass with no gold labels and no KSA dependency.
- Secret scan must report no tracked, staged, notebook-output, log, fixture, or
  history exposure.
- `p4.duckdb` must remain an empty canonical contract database.
- No `p4.observed-dev.duckdb` or empirical mart may be created from the current
  crawl candidate.
- Quarantine stays copy-only until the full crawl release, rolling build PASS,
  restore test, key rotation, and canonical replacements are all confirmed.

## Promotion boundary

This plan can produce a rolling integration build for contract, pipeline, and
NCS foundations. It cannot produce `CRAWL_RELEASE_READY`,
`DATA_READY_RQ1_RQ2A`, `DATA_READY_RQ2B`, or `ANALYSIS_READY` from the current
evidence.
