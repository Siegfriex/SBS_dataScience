#!/usr/bin/env python3
"""Publish A3's no-network approval packet for the bounded measurement canary."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from tier1t2_preapproval_contract import (
    REQUIRED_A1_TIER1T2_ARTIFACTS,
    combined_approval_schema,
    file_sha256,
    validate_a1_bundle,
    validate_schema,
)


OUTPUT_NAMES = (
    "P4_TIER1T2_POLICY_COMPATIBILITY_AUDIT.csv",
    "P4_TIER1T2_SCOPE_BUDGET_VALIDATION.csv",
    "P4_TIER1T2_COMBINED_APPROVAL.schema.json",
    "P4_TIER1T2_MEASUREMENT_CONTRACT.json",
    "P4_TIER1T2_ACCEPTANCE_GATE_MATRIX.csv",
    "P4_TIER1T2_USER_DECISION_PACKET.md",
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def git_value(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def validate_git_binding(root: Path, submitted_head: str) -> list[str]:
    errors: list[str] = []
    top = Path(git_value(root, "rev-parse", "--show-toplevel"))
    if git_value(top, "rev-parse", "HEAD") != submitted_head:
        errors.append("TIER1T2_A1_HEAD_MISMATCH")
    tracked = set(git_value(top, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    for name in REQUIRED_A1_TIER1T2_ARTIFACTS:
        target = root / name
        relative = target.relative_to(top).as_posix()
        if relative not in tracked:
            errors.append(f"TIER1T2_A1_NOT_TRACKED:{name}")
        elif git_value(top, "rev-parse", f"HEAD:{relative}") != git_value(top, "hash-object", str(target)):
            errors.append(f"TIER1T2_A1_DIRTY:{name}")
    return errors


def measurement_contract() -> dict[str, Any]:
    return {
        "schemaVersion": "p4-tier1t2-measurement-contract-v1",
        "purpose": "SOURCE_RECOVERY_AND_LINKAREER_HOSTED_ASSET_AVAILABILITY_MEASUREMENT",
        "detailRowFields": [
            "postingId", "terminalStatus", "ssrRawByteCount", "ssrDecodedCharacterCount",
            "apolloTextCharacterCount", "activityTextCharacterCount", "mergedSourceTextCharacterCount",
            "sourceBlockCount", "sectionCount", "semanticChunkCount", "requirementFactCount",
            "koreanCharacterRatio", "emptyTextFlag", "parserQuarantineFlag",
        ],
        "detailAggregateFields": [
            "detailRequestedCount", "detailFetchedValidCount", "detailTerminalCoverage", "totalSsrBytes",
            "totalSsrCharacters", "totalApolloCharacters", "totalActivityTextCharacters",
            "totalMergedTextCharacters", "meanTextCharacters", "medianTextCharacters",
            "zeroTextPostingCount", "sourceModeDistribution",
        ],
        "assetRowFields": [
            "postingId", "assetCandidateId", "sourceField", "host", "mime", "contentLength",
            "assetSha256", "terminalStatus", "duplicateContent", "ocrCandidateFlag",
        ],
        "assetAggregateFields": [
            "selectedPostingCount", "assetCandidateCount", "linkareerHostedAssetCount",
            "fetchedValidAssetCount", "duplicateContentCount", "unsupportedMimeCount",
            "notFoundAssetCount", "policyBlockedAssetCount", "uniqueAssetShaCount", "totalAssetBytes",
            "mimeDistribution", "postingWithAtLeastOneAssetCount",
        ],
        "detailTerminalStatus": [
            "FETCHED_VALID", "FETCHED_EMPTY_VALID", "NOT_FOUND", "EXPIRED", "POLICY_BLOCKED",
            "RETRY_EXHAUSTED", "PARSER_QUARANTINED",
        ],
        "assetTerminalStatus": [
            "FETCHED_VALID", "DUPLICATE_CONTENT", "UNSUPPORTED_MIME", "NOT_FOUND",
            "POLICY_BLOCKED", "RETRY_EXHAUSTED",
        ],
        "fallback": {
            "exactSourceIdOrApolloReferenceAllowed": True,
            "ambiguousStandaloneAutoSelectionAllowed": False,
            "terminalStatusOverwriteAllowed": False,
        },
        "assetPolicy": {
            "linkareerHostedOnly": True,
            "externalAtsTransportAllowed": False,
            "redirectToUnapprovedHostAllowed": False,
        },
        "ocr": {
            "mode": "QUEUE_MIME_SHA_TEXT_VOLUME_ONLY",
            "textExtractionAllowed": False,
            "ncsMappingAllowed": False,
        },
        "promotion": {
            "productionReleaseAllowed": False,
            "analysisPromotionAllowed": False,
            "goldPromotionAllowed": False,
        },
    }


def update_automation_state(project: Path, proposal: dict[str, Any], a1_branch: str, a1_head: str, a3_head: str) -> None:
    root = project / "reports/automation"
    path = root / "P4_AUTOMATION_STATE.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.update({
        "state": "AWAIT_TIER1_APPROVAL",
        "tier": "TIER1",
        "iterationId": "P4_AUTO_T1T2_PREAPPROVAL_20260807_01",
        "updatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "a1Status": "TIER1T2_COMBINED_APPROVAL_PACKET_READY",
        "a3Status": "TIER1T2_CANARY_ACCEPTANCE_READY",
        "a5Status": "NOT_REQUIRED",
        "approvalStatus": "TIER1T2_APPROVAL_MISSING",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "acceptedScope": "TIER0_FIXTURE_ONLY",
        "nextRequiredAction": "USER_TIER1T2_DETAIL_ASSET_CANARY_APPROVAL_ARTIFACT",
        "tier1t2Proposal": {
            "proposalStatus": "PROPOSED_NOT_APPROVED",
            "candidateScopeId": proposal["tier1"]["candidateScopeId"],
            "candidatePeriodOrQuery": {
                "periodMonths": proposal["tier1"]["periodMonths"],
                "queryOperations": proposal["tier1"]["queryOperations"],
            },
            "proposedMaxIndexRequests": proposal["tier1"]["proposedMaxIndexRequests"],
            "detailSampleSize": proposal["tier2"]["sampleSize"],
            "proposedMaxAssetRequests": proposal["tier3"]["proposedMaxAssetRequests"],
            "approvalExpiryRecommendation": "PT2H_AFTER_APPROVAL",
            "a1Branch": a1_branch,
            "a1Head": a1_head,
            "a3HeadBeforeReportCommit": a3_head,
        },
        "m2FullCrawlEligible": False,
        "crawlReleaseEligible": False,
        "analysisEligible": False,
        "automationPolicySha256": file_sha256(project / "automation_policy.yaml"),
    })
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    iteration_id = "P4_AUTO_T1T2_PREAPPROVAL_20260807_01"
    log_path = root / "P4_AUTOMATION_ITERATION_LOG.jsonl"
    retained = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("iterationId") != iteration_id:
            retained.append(line)
    retained.append(json.dumps({
        "iterationId": iteration_id,
        "tier": "TIER1",
        "runId": "TIER1T2_PREAPPROVAL_NO_NETWORK",
        "inputCommit": a3_head,
        "outputCommit": None,
        "approvalId": "NONE",
        "networkCalls": 0,
        "scope": proposal["tier1"]["candidateScopeId"],
        "defectFamily": "TIER1T2_PREAPPROVAL",
        "repairAction": "NO_NETWORK_COMBINED_SCOPE_BUDGET_AND_MEASUREMENT_CONTRACT",
        "testResult": "PASS_WITH_FINDINGS",
        "acceptanceStatus": "TIER1T2_COMBINED_APPROVAL_PACKET_READY",
        "nextState": "AWAIT_TIER1_APPROVAL",
        "blockedReason": None,
        "recordedAtUtc": state["updatedAtUtc"],
    }, ensure_ascii=False, sort_keys=True))
    log_path.write_text("\n".join(retained) + "\n", encoding="utf-8")

    scope_path = root / "P4_AUTOMATION_SCOPE_REGISTER.csv"
    scope_rows = read_csv(scope_path)
    for row in scope_rows:
        if row["tier"] == "TIER1":
            row.update({"state": "COMBINED_APPROVAL_PACKET_READY", "blockedReason": "TIER1T2_APPROVAL_MISSING"})
        elif row["tier"] == "TIER2":
            row.update({"state": "PREAPPROVAL_CONTRACT_READY", "blockedReason": "TIER1_ACCEPTANCE_AND_NEW_TIER2_APPROVAL_REQUIRED"})
        elif row["tier"] == "TIER3":
            row.update({"state": "PREAPPROVAL_BUDGET_PROPOSED", "blockedReason": "TIER2_ACCEPTANCE_AND_NEW_TIER3_APPROVAL_REQUIRED"})
    write_csv(scope_path, list(scope_rows[0]), scope_rows)

    agent_path = root / "P4_AUTOMATION_AGENT_STATUS.csv"
    agent_rows = read_csv(agent_path)
    for row in agent_rows:
        if row["agent"] == "A1":
            row.update({"branch": a1_branch, "headCommit": a1_head, "status": "TIER1T2_COMBINED_APPROVAL_PACKET_READY", "nextAction": "AWAIT_USER_APPROVAL"})
        elif row["agent"] == "A3":
            row.update({"headCommit": a3_head, "status": "TIER1T2_CANARY_ACCEPTANCE_READY", "nextAction": "HOLD_NETWORK_GATE"})
    write_csv(agent_path, list(agent_rows[0]), agent_rows)

    promotion_path = root / "P4_AUTOMATION_PROMOTION_DECISIONS.csv"
    promotion_rows = read_csv(promotion_path)
    replacement = {
        "gate": "TIER1T2_APPROVAL_PACKET",
        "decision": "READY_WITH_SEQUENTIAL_GATES",
        "evidence": "reports/tier1t2_preapproval/EVIDENCE_MANIFEST.sha256",
        "eligible": "true",
    }
    promotion_rows = [row for row in promotion_rows if row["gate"] != replacement["gate"]]
    promotion_rows.append(replacement)
    write_csv(promotion_path, list(promotion_rows[0]), promotion_rows)

    queue = project / "reports/tier1t2_preapproval/P4_TIER1T2_USER_DECISION_PACKET.md"
    (root / "P4_AUTOMATION_APPROVAL_QUEUE.md").write_text(queue.read_text(encoding="utf-8"), encoding="utf-8")

    evidence_names = (
        "P4_AUTOMATION_STATE.json", "P4_AUTOMATION_ITERATION_LOG.jsonl",
        "P4_AUTOMATION_DEFECT_BACKLOG.csv", "P4_AUTOMATION_SCOPE_REGISTER.csv",
        "P4_AUTOMATION_APPROVAL_QUEUE.md", "P4_AUTOMATION_AGENT_STATUS.csv",
        "P4_AUTOMATION_PROMOTION_DECISIONS.csv",
    )
    (root / "EVIDENCE_MANIFEST.sha256").write_text(
        "".join(f"{file_sha256(root / name)}  {name}\n" for name in evidence_names),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--a1-root", type=Path, required=True)
    parser.add_argument("--a1-tier1-root", type=Path, required=True)
    parser.add_argument("--a1-branch", required=True)
    parser.add_argument("--a1-head", required=True)
    parser.add_argument("--a1-tier1-head", required=True)
    parser.add_argument("--a3-head", required=True)
    parser.add_argument("--report-root", type=Path)
    args = parser.parse_args()

    project = args.project_root.resolve()
    report = (args.report_root or project / "reports/tier1t2_preapproval").resolve()
    report.mkdir(parents=True, exist_ok=True)
    errors, payloads = validate_a1_bundle(args.a1_root.resolve(), args.a1_tier1_head)
    errors.extend(validate_git_binding(args.a1_root.resolve(), args.a1_head))
    if errors:
        raise SystemExit("Tier 1/Tier 2 proposal rejected: " + ";".join(sorted(set(errors))))

    proposal = payloads["P4_TIER1T2_SCOPE_PROPOSAL.json"]
    sample = payloads["P4_TIER2_DETAIL_SAMPLE_CONTRACT.json"]
    asset = payloads["P4_TIER3_ASSET_REQUEST_ESTIMATE.json"]
    tier1_proposal_path = args.a1_tier1_root.resolve() / "P4_TIER1_SCOPE_PROPOSAL.json"
    tier1_proposal = json.loads(tier1_proposal_path.read_text(encoding="utf-8"))
    if file_sha256(tier1_proposal_path) != proposal["tier1ScopeProposalSha256"]:
        raise SystemExit("Tier 1/Tier 2 proposal rejected: TIER1_SCOPE_SHA_MISMATCH")
    for field in (
        "queryRegistrySha256", "sourcePolicyAuditSha256", "rateLimitPolicyVersion",
        "rateLimitPolicySha256", "killSwitchPolicyVersion", "killSwitchPolicySha256",
    ):
        proposal[field] = tier1_proposal[field]
    policy = yaml.safe_load((project / "automation_policy.yaml").read_text(encoding="utf-8"))
    required_seed = ["canaryRunId", "tier1DiscoveryManifestSha256", "approvedScopeHash"]
    if policy["tier2"]["samplingSeedMaterial"] != required_seed:
        raise SystemExit("Tier 1/Tier 2 proposal rejected: AUTOMATION_SAMPLE_SEED_POLICY_MISMATCH")
    if policy["tier2"]["detailSampleSize"] != 10:
        raise SystemExit("Tier 1/Tier 2 proposal rejected: AUTOMATION_DETAIL_SAMPLE_SIZE_MISMATCH")

    common = {
        "a1Branch": args.a1_branch,
        "a1Head": args.a1_head,
        "a3HeadBeforeReportCommit": args.a3_head,
        "candidateScopeId": proposal["tier1"]["candidateScopeId"],
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    }
    compatibility = [
        {**common, "checkId": "A1_GIT_TRACKED_BUNDLE", "expected": "7/7 exact HEAD bytes", "observed": "7/7", "status": "PASS", "evidence": "A1 evidence manifest + Git blob binding"},
        {**common, "checkId": "TIER1_SCOPE_BINDING", "expected": "existing Tier 1 proposal", "observed": f"periods={proposal['tier1']['periodMonths']}; operations={proposal['tier1']['queryOperations']}; max={proposal['tier1']['proposedMaxIndexRequests']}", "status": "PASS", "evidence": "P4_TIER1T2_SCOPE_PROPOSAL.json"},
        {**common, "checkId": "DETAIL_SAMPLE_CONTRACT", "expected": "10 deterministic without replacement; no terminal replacement", "observed": sample["contractStatus"], "status": "PASS", "evidence": "P4_TIER2_DETAIL_SAMPLE_CONTRACT.json"},
        {**common, "checkId": "ASSET_BUDGET_EVIDENCE", "expected": "checked-in metadata; Linkareer host only", "observed": f"observed={asset['linkareerHostedCandidateRows']}; max={asset['proposedMaxAssetRequests']}", "status": "PASS_WITH_FINDINGS", "evidence": asset["upperBoundMethod"]},
        {**common, "checkId": "SEQUENTIAL_APPROVAL_POLICY", "expected": "new approval artifact at each tier", "observed": "one combined decision packet; later tier activation remains gated", "status": "PASS_WITH_FINDINGS", "evidence": "automation_policy.yaml scopeEscalation.requiresNewApprovalArtifact=true"},
        {**common, "checkId": "TRANSPORT_BOUNDARY", "expected": "network/detail/asset calls 0", "observed": "0/0/0", "status": "PASS", "evidence": "proposal-only bundle"},
        {**common, "checkId": "SOURCE_POLICY_HUMAN_APPROVAL", "expected": "user-issued record", "observed": "missing", "status": "BLOCKED", "evidence": "combined approval schema requires SHA"},
    ]
    write_csv(report / OUTPUT_NAMES[0], list(compatibility[0]), compatibility)

    validations = [
        {**common, "checkId": "INDEX_SCOPE", "expected": "one proposed period/query scope", "observed": json.dumps({"periodMonths": proposal["tier1"]["periodMonths"], "queryOperations": proposal["tier1"]["queryOperations"]}, sort_keys=True), "status": "PASS"},
        {**common, "checkId": "INDEX_MAX", "expected": "proposal only", "observed": proposal["tier1"]["proposedMaxIndexRequests"], "status": "PASS"},
        {**common, "checkId": "DETAIL_MAX", "expected": 10, "observed": proposal["tier2"]["sampleSize"], "status": "PASS"},
        {**common, "checkId": "DETAIL_SELECTION", "expected": "await Tier 1 discovery", "observed": sample["contractStatus"], "status": "NOT_EVALUATED"},
        {**common, "checkId": "ASSET_MAX", "expected": "evidence-based proposed cap", "observed": proposal["tier3"]["proposedMaxAssetRequests"], "status": "PASS_WITH_FINDINGS"},
        {**common, "checkId": "EXTERNAL_ATS_BROWSER", "expected": "0/0", "observed": "0/0", "status": "PASS"},
    ]
    write_csv(report / OUTPUT_NAMES[1], list(validations[0]), validations)

    schema = combined_approval_schema(proposal)
    validate_schema(schema)
    (report / OUTPUT_NAMES[2]).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report / OUTPUT_NAMES[3]).write_text(json.dumps(measurement_contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    gates = [
        ("TIER0_CANONICAL_HANDOFF", "PASS", "accepted fixture-only authority"),
        ("TIER1T2_PREAPPROVAL_BUNDLE", "PASS", "A1 8-file proposal evidence"),
        ("TIER1_INDEX_SCOPE_PROPOSED", "PASS", "exact proposal; not approval"),
        ("TIER2_DETAIL_SAMPLE_CONTRACT", "PASS", "sample size 10 and deterministic seed contract"),
        ("TIER2_DETAIL_SAMPLE_SELECTED", "NOT_EVALUATED", "Tier 1 discovery manifest does not exist"),
        ("TIER3_LINKAREER_ASSET_BUDGET_PROPOSED", "PASS_WITH_FINDINGS", "fixture-derived upper bound; live candidates unknown"),
        ("COMBINED_USER_APPROVAL_SCHEMA", "PASS", "user-set scope, budgets, expiry, rate, retry and source-policy record required"),
        ("TIER1T2_NETWORK_EXECUTION", "BLOCKED", "USER_TIER1T2_DETAIL_ASSET_CANARY_APPROVAL missing"),
        ("EXTERNAL_ATS_TRANSPORT", "BLOCKED", "hard deny"),
        ("OCR_TEXT_EXTRACTION_OR_MAPPING", "BLOCKED", "queue/MIME/SHA/text-volume measurement only"),
        ("M2_FULL_CRAWL", "BLOCKED", "canary and user gates remain"),
        ("PRODUCTION_RELEASE", "BLOCKED", "canary cannot promote"),
        ("ANALYSIS", "BLOCKED", "canary cannot promote"),
    ]
    gate_rows = [{**common, "gateId": gate, "status": status, "evidence": evidence} for gate, status, evidence in gates]
    write_csv(report / OUTPUT_NAMES[4], list(gate_rows[0]), gate_rows)

    (report / OUTPUT_NAMES[5]).write_text(
        "# P4 Combined Tier 1 / Detail 10 / Linkareer Asset Approval Packet\n\n"
        "Decision ID: `D-T1T2-DETAIL-ASSET-CANARY`\n\n"
        "## Question\n\nApprove one bounded Linkareer index canary, a deterministic sample of 10 discovered postings, and only their Linkareer-hosted asset candidates?\n\n"
        "## Current evidence\n\n"
        "- Tier 0 canonical handoff: accepted\n"
        "- A5 M1.5 audit: PASS_WITH_FINDINGS\n"
        "- Combined preapproval validation: PASS_WITH_FINDINGS\n"
        "- Network, detail, asset, external ATS and credentialed API calls so far: 0\n"
        "- Actual 10 posting IDs: not selected; selection waits for the Tier 1 discovery manifest\n\n"
        "## Controller proposal (not approved)\n\n"
        f"- Index scope: `{json.dumps({'periodMonths': proposal['tier1']['periodMonths'], 'queryOperations': proposal['tier1']['queryOperations']}, ensure_ascii=False, sort_keys=True)}`\n"
        f"- Maximum index requests: `{proposal['tier1']['proposedMaxIndexRequests']}`\n"
        "- Detail requests: `10`\n"
        "- Detail sampling: deterministic random without replacement\n"
        "- Terminal failure replacement: `false`\n"
        f"- Expected Linkareer-hosted candidates in evidence: `{asset['linkareerHostedCandidateRows']}` across `{asset['evidencePostingRows']}` evidence postings\n"
        f"- Proposed maximum asset requests: `{proposal['tier3']['proposedMaxAssetRequests']}`\n"
        f"- Asset cap method: {asset['upperBoundMethod']}\n"
        "- Source: `LINKAREER only`\n"
        "- External ATS: `false`\n"
        "- Browser automation: `false`\n"
        "- Raw retention: immutable content-addressed external storage; Git raw bytes forbidden\n"
        "- OCR: queue, MIME, SHA and text-volume measurement only; extraction/mapping forbidden\n"
        "- Query/rate/kill/source-policy SHA: inherited exactly from the accepted Tier 1 proposal\n"
        "- Expiry suggestion: `PT2H_AFTER_APPROVAL`\n\n"
        "## User-owned values still required\n\n"
        "The approval artifact must set the exact approved scope, index/detail/asset budgets, expiry, rate limit, retry budget, source-policy human approval record, and storage-plan SHA. This packet sets none of those values.\n\n"
        "Under the current automation policy, this is one combined decision packet, not one reusable transport authorization: Tier 2 and Tier 3 still require newly bound approval artifacts and new run IDs after their upstream acceptance gates.\n\n"
        "## Impact\n\n"
        "- If approved: only the exact bounded index, detail-10, and Linkareer-hosted asset measurement may run.\n"
        "- If denied: all network calls remain zero.\n"
        "- If deferred: automation remains in `AWAIT_TIER1_APPROVAL`.\n\n"
        "This canary measures source recovery and asset availability only. It does not establish production coverage, OCR quality, NCS mapping quality, Human Gold, RQ findings, or article claims.\n",
        encoding="utf-8",
    )
    manifest = report / "EVIDENCE_MANIFEST.sha256"
    manifest.write_text("".join(f"{file_sha256(report / name)}  {name}\n" for name in OUTPUT_NAMES), encoding="utf-8")
    update_automation_state(project, proposal, args.a1_branch, args.a1_head, args.a3_head)
    print(json.dumps({
        "status": "TIER1T2_CANARY_ACCEPTANCE_READY",
        "candidateScopeId": proposal["tier1"]["candidateScopeId"],
        "proposedMaxIndexRequests": proposal["tier1"]["proposedMaxIndexRequests"],
        "detailSampleSize": proposal["tier2"]["sampleSize"],
        "proposedMaxAssetRequests": proposal["tier3"]["proposedMaxAssetRequests"],
        "networkCalls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
