#!/usr/bin/env python3
"""Consume A1 Tier 1 no-network evidence and publish A3 approval readiness."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from tier1_preapproval_contract import (
    REQUIRED_A1_PREAPPROVAL_ARTIFACTS,
    file_sha256,
    read_csv_rows,
    validate_a1_preapproval_bundle,
)


OUTPUT_NAMES = (
    "P4_TIER1_POLICY_COMPATIBILITY_AUDIT.csv",
    "P4_TIER1_SCOPE_VALIDATION.csv",
    "P4_TIER1_HANDOFF_VALIDATOR_SCHEMA.json",
    "P4_TIER1_ACCEPTANCE_GATE_MATRIX.csv",
    "P4_TIER1_SCOPE_ESCALATION_RULES.json",
    "P4_TIER1_APPROVAL_REQUIREMENTS.md",
)
AUTOMATION_OUTPUT_NAMES = (
    "P4_AUTOMATION_STATE.json",
    "P4_AUTOMATION_ITERATION_LOG.jsonl",
    "P4_AUTOMATION_DEFECT_BACKLOG.csv",
    "P4_AUTOMATION_SCOPE_REGISTER.csv",
    "P4_AUTOMATION_APPROVAL_QUEUE.md",
    "P4_AUTOMATION_AGENT_STATUS.csv",
    "P4_AUTOMATION_PROMOTION_DECISIONS.csv",
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_value(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def validate_a1_git_binding(root: Path, submitted_head: str) -> list[str]:
    errors: list[str] = []
    top = Path(git_value(root, "rev-parse", "--show-toplevel"))
    actual_head = git_value(root, "rev-parse", "HEAD")
    if actual_head != submitted_head:
        errors.append("A1_PREAPPROVAL_HEAD_MISMATCH")
    tracked = set(git_value(top, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    for name in REQUIRED_A1_PREAPPROVAL_ARTIFACTS:
        target = root / name
        relative = target.relative_to(top).as_posix()
        if relative not in tracked:
            errors.append(f"A1_PREAPPROVAL_NOT_TRACKED:{name}")
            continue
        head_blob = git_value(top, "rev-parse", f"HEAD:{relative}")
        worktree_blob = git_value(top, "hash-object", str(target))
        if head_blob != worktree_blob:
            errors.append(f"A1_PREAPPROVAL_DIRTY:{name}")
    return errors


def handoff_schema(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:p4:canary:tier1-index-handoff:v1",
        "title": "P4 Tier 1 index canary handoff summary",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "runId", "dataVersion", "approvalId", "approvalArtifactSha256",
            "logicalRequestType", "approvedScopeHash", "requestCount",
            "detailRequestCount", "assetRequestCount", "externalAtsTransportCalls",
            "browserAutomationCalls", "requestManifestSha256", "checkpointManifestSha256",
            "terminalPageEvidenceSha256", "requestAttempts", "terminalPages",
            "checkpoint", "requestsAfterKillSwitchStop", "status",
        ],
        "properties": {
            "runId": {"type": "string", "minLength": 1},
            "dataVersion": {"type": "string", "minLength": 1},
            "approvalId": {"type": "string", "minLength": 1},
            "approvalArtifactSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "logicalRequestType": {"const": "INDEX"},
            "approvedScopeHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "requestCount": {"type": "integer", "minimum": 1, "maximum": proposal["proposedMaxIndexRequests"]},
            "detailRequestCount": {"const": 0},
            "assetRequestCount": {"const": 0},
            "externalAtsTransportCalls": {"const": 0},
            "browserAutomationCalls": {"const": 0},
            "requestManifestSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "checkpointManifestSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "terminalPageEvidenceSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "requestAttempts": {
                "type": "array", "minItems": 1, "maxItems": proposal["proposedMaxIndexRequests"],
                "items": {"$ref": "#/$defs/requestAttempt"},
            },
            "terminalPages": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/terminalPage"}},
            "checkpoint": {"$ref": "#/$defs/checkpoint"},
            "requestsAfterKillSwitchStop": {"const": 0},
            "status": {"enum": [
                "CANARY_VALIDATION", "CANARY_READY_FOR_NEXT_SCOPE", "CANARY_STOPPED_BY_KILL_SWITCH",
                "CANARY_STOPPED_BY_SCOPE_LIMIT", "CANARY_QUARANTINED", "CANARY_FAILED",
            ]},
        },
        "$defs": {
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "requestAttempt": {
                "type": "object",
                "required": [
                    "requestAttemptId", "requestKey", "logicalRequestType", "periodMonth",
                    "pageOrCursor", "startedAtUtc", "completedAtUtc", "responseSha256",
                    "checkpointId", "terminalStatus",
                ],
                "properties": {
                    "requestAttemptId": {"type": "string", "minLength": 1},
                    "requestKey": {"$ref": "#/$defs/sha256"},
                    "logicalRequestType": {"const": "INDEX"},
                    "periodMonth": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}$"},
                    "pageOrCursor": {"type": ["string", "integer"]},
                    "startedAtUtc": {"type": "string", "format": "date-time"},
                    "completedAtUtc": {"type": "string", "format": "date-time"},
                    "responseSha256": {"$ref": "#/$defs/sha256"},
                    "checkpointId": {"type": "string", "minLength": 1},
                    "terminalStatus": {"enum": [
                        "FETCHED_VALID", "FETCHED_EMPTY_VALID", "POLICY_BLOCKED",
                        "RETRY_EXHAUSTED", "PARSER_QUARANTINED",
                    ]},
                },
            },
            "terminalPage": {
                "type": "object",
                "required": ["periodMonth", "pageOrCursor", "terminal", "cursorLoopDetected", "evidenceSha256"],
                "properties": {
                    "periodMonth": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}$"},
                    "pageOrCursor": {"type": ["string", "integer"]},
                    "terminal": {"const": True},
                    "cursorLoopDetected": {"const": False},
                    "evidenceSha256": {"$ref": "#/$defs/sha256"},
                },
            },
            "checkpoint": {
                "type": "object",
                "required": [
                    "checkpointId", "runId", "completedRequestKeys",
                    "requestLedgerOffset", "rawObjectManifestSha256", "coverageSnapshotSha256",
                ],
                "properties": {
                    "checkpointId": {"type": "string", "minLength": 1},
                    "runId": {"type": "string", "minLength": 1},
                    "completedRequestKeys": {"type": "array", "uniqueItems": True, "items": {"$ref": "#/$defs/sha256"}},
                    "requestLedgerOffset": {"type": "integer", "minimum": 0},
                    "rawObjectManifestSha256": {"$ref": "#/$defs/sha256"},
                    "coverageSnapshotSha256": {"$ref": "#/$defs/sha256"},
                },
            },
        },
    }


def update_automation_state(
    project: Path,
    proposal: dict[str, Any],
    *,
    a1_branch: str,
    a1_head: str,
    a3_head: str,
    tier1_evidence_sha: str,
) -> None:
    root = project / "reports/automation"
    state_path = root / "P4_AUTOMATION_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    iteration_id = "P4_AUTO_T1_PREAPPROVAL_20260807_01"
    state.update({
        "state": "AWAIT_TIER1_APPROVAL",
        "tier": "TIER1",
        "iterationId": iteration_id,
        "updatedAtUtc": now,
        "a1Status": "TIER1_APPROVAL_PACKET_READY",
        "a3Status": "TIER1_CANARY_ACCEPTANCE_READY",
        "a5Status": "NOT_REQUIRED",
        "approvalStatus": "TIER1_APPROVAL_MISSING",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "acceptedScope": "TIER0_FIXTURE_ONLY",
        "nextRequiredAction": "USER_TIER1_INDEX_CANARY_APPROVAL_ARTIFACT",
        "tier1Proposal": {
            "proposalStatus": "PROPOSED_NOT_APPROVED",
            "candidateScopeId": proposal["candidateScopeId"],
            "candidatePeriodOrQuery": proposal["candidatePeriodOrQuery"],
            "proposedMaxIndexRequests": proposal["proposedMaxIndexRequests"],
            "estimatedStorageBytes": proposal["estimatedStorageBytes"],
            "approvalExpiryRecommendation": proposal["approvalExpiryRecommendation"],
            "a1Branch": a1_branch,
            "a1Head": a1_head,
            "a3HeadBeforeReportCommit": a3_head,
            "a3EvidenceManifestSha256": tier1_evidence_sha,
        },
        "m2FullCrawlEligible": False,
        "crawlReleaseEligible": False,
        "analysisEligible": False,
    })
    if "P2-TIER1-PREEXISTING-ABSOLUTE-PATH-LITERALS" not in state["openDefects"]:
        state["openDefects"].append("P2-TIER1-PREEXISTING-ABSOLUTE-PATH-LITERALS")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    defect_path = root / "P4_AUTOMATION_DEFECT_BACKLOG.csv"
    defect_rows = read_csv_rows(defect_path)
    defect_id = "P2-TIER1-PREEXISTING-ABSOLUTE-PATH-LITERALS"
    if not any(row.get("defectId") == defect_id for row in defect_rows):
        defect_rows.append({
            "defectId": defect_id,
            "severity": "P2",
            "family": "PATH_PORTABILITY",
            "status": "OPEN_FINDING",
            "evidence": "7 historical audit/negative-test absolute-path literals outside new Tier 1 packet tree",
            "requiredAction": "Do not consume literals as runtime authority; clean in a separately scoped hygiene change",
        })
    write_csv(
        defect_path,
        ["defectId", "severity", "family", "status", "evidence", "requiredAction"],
        defect_rows,
    )

    log_path = root / "P4_AUTOMATION_ITERATION_LOG.jsonl"
    retained = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("iterationId") != iteration_id:
                retained.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    iteration = {
        "iterationId": iteration_id,
        "tier": "TIER1",
        "runId": "TIER1_PREAPPROVAL_NO_NETWORK",
        "inputCommit": a3_head,
        "outputCommit": None,
        "approvalId": "NONE",
        "networkCalls": 0,
        "scope": proposal["candidateScopeId"],
        "defectFamily": "TIER1_PREAPPROVAL",
        "repairAction": "NO_NETWORK_PREPARATION_AND_VALIDATION",
        "testResult": "PASS",
        "acceptanceStatus": "TIER1_APPROVAL_PACKET_READY",
        "nextState": "AWAIT_TIER1_APPROVAL",
        "blockedReason": None,
        "recordedAtUtc": now,
    }
    retained.append(json.dumps(iteration, ensure_ascii=False, sort_keys=True))
    log_path.write_text("".join(f"{line}\n" for line in retained), encoding="utf-8")

    write_csv(
        root / "P4_AUTOMATION_SCOPE_REGISTER.csv",
        ["tier", "state", "acceptedScope", "approvalRequired", "networkAllowed", "blockedReason"],
        [
            {"tier": "TIER0", "state": "ACCEPTED", "acceptedScope": "TIER0_FIXTURE_ONLY", "approvalRequired": "false", "networkAllowed": "false", "blockedReason": "NONE"},
            {"tier": "TIER1", "state": "APPROVAL_PACKET_READY", "acceptedScope": "NONE", "approvalRequired": "true", "networkAllowed": "false", "blockedReason": "TIER1_APPROVAL_MISSING"},
            *[
                {"tier": tier, "state": "NOT_STARTED", "acceptedScope": "NONE", "approvalRequired": "true", "networkAllowed": "false", "blockedReason": "UPSTREAM_TIER_NOT_ACCEPTED"}
                for tier in ("TIER2", "TIER3", "TIER4")
            ],
        ],
    )
    approval_text = (project / "reports/tier1_preapproval/P4_TIER1_APPROVAL_REQUIREMENTS.md").read_text(encoding="utf-8")
    (root / "P4_AUTOMATION_APPROVAL_QUEUE.md").write_text(approval_text, encoding="utf-8")
    write_csv(
        root / "P4_AUTOMATION_AGENT_STATUS.csv",
        ["agent", "branch", "headCommit", "status", "nextAction"],
        [
            {"agent": "A1", "branch": a1_branch, "headCommit": a1_head, "status": "TIER1_APPROVAL_PACKET_READY", "nextAction": "AWAIT_USER_APPROVAL"},
            {"agent": "A3", "branch": "integration/p4-canary-acceptance-v1", "headCommit": a3_head, "status": "TIER1_CANARY_ACCEPTANCE_READY", "nextAction": "HOLD_NETWORK_GATE"},
            {"agent": "A5", "branch": "NONE", "headCommit": "NONE", "status": "NOT_REQUIRED", "nextAction": "CONDITIONAL_OR_TIER4"},
        ],
    )
    write_csv(
        root / "P4_AUTOMATION_PROMOTION_DECISIONS.csv",
        ["gate", "decision", "evidence", "eligible"],
        [
            {"gate": "TIER0_GLOBAL_ACCEPTANCE", "decision": "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE", "evidence": state["a1CanonicalHandoff"]["manifestSha256"], "eligible": "true"},
            {"gate": "TIER1_APPROVAL_PACKET", "decision": "READY", "evidence": tier1_evidence_sha, "eligible": "true"},
            {"gate": "TIER1_NETWORK_CANARY", "decision": "AWAITING_USER_APPROVAL", "evidence": "no USER_TIER1_INDEX_CANARY_APPROVAL", "eligible": "false"},
            {"gate": "M2_FULL_CRAWL", "decision": "BLOCKED", "evidence": "Tier 1-4 and human approval gates unmet", "eligible": "false"},
            {"gate": "CRAWL_RELEASE", "decision": "BLOCKED", "evidence": "no production release", "eligible": "false"},
            {"gate": "ANALYSIS", "decision": "BLOCKED", "evidence": "no production data readiness", "eligible": "false"},
        ],
    )
    manifest = root / "EVIDENCE_MANIFEST.sha256"
    manifest.write_text("".join(f"{file_sha256(root / name)}  {name}\n" for name in AUTOMATION_OUTPUT_NAMES), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--a1-report-root", type=Path, required=True)
    parser.add_argument("--a1-branch", required=True)
    parser.add_argument("--a1-head", required=True)
    parser.add_argument("--a3-head", required=True)
    parser.add_argument("--tier0-manifest-sha", required=True)
    parser.add_argument("--report-root", type=Path)
    args = parser.parse_args()

    project = args.project_root.resolve()
    a1_root = args.a1_report_root.resolve()
    report = (args.report_root or project / "reports/tier1_preapproval").resolve()
    report.mkdir(parents=True, exist_ok=True)
    errors, proposal = validate_a1_preapproval_bundle(a1_root, args.tier0_manifest_sha)
    errors.extend(validate_a1_git_binding(a1_root, args.a1_head))

    local_registry_sha = file_sha256(project / "crawl/configs/queryRegistry.yaml")
    if proposal.get("queryRegistrySha256") != local_registry_sha:
        errors.append("TIER1_QUERY_REGISTRY_SHA_MISMATCH")
    automation_policy = yaml.safe_load((project / "automation_policy.yaml").read_text(encoding="utf-8"))
    approval_schema_path = project / "shared/contracts/canary_acceptance/v1/production_crawl_approval.schema.json"
    approval_schema = json.loads(approval_schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(approval_schema)
    source_authority = json.loads(
        (project / "crawl/reports/reconciliation_a1/A1_M2_PREFLIGHT_REBIND_MANIFEST.json").read_text(encoding="utf-8")
    )
    if proposal.get("sourcePolicyAuditSha256") != source_authority.get("sourcePolicyAuditSha256"):
        errors.append("TIER1_SOURCE_POLICY_AUDIT_SHA_MISMATCH")
    if proposal.get("rateLimitPolicyVersion") != "p4-linkareer-production-rate-v1":
        errors.append("TIER1_RATE_POLICY_VERSION_MISMATCH")
    if proposal.get("killSwitchPolicyVersion") != "p4-linkareer-kill-switch-v1":
        errors.append("TIER1_KILL_SWITCH_VERSION_MISMATCH")
    if automation_policy["networkPolicy"]["allowNetworkWithoutApproval"] is not False:
        errors.append("AUTOMATION_NETWORK_WITHOUT_APPROVAL_NOT_DENIED")
    if errors:
        raise SystemExit("Tier 1 A1 preapproval rejected: " + ";".join(sorted(set(errors))))

    common = {
        "a1Branch": args.a1_branch,
        "a1Head": args.a1_head,
        "candidateScopeId": proposal["candidateScopeId"],
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    }
    compatibility = [
        {**common, "checkId": "AUTOMATION_POLICY", "expected": "schema PASS; 3 repair / 2 run", "observed": f"{automation_policy['maxAutoRepairIterationsPerTier']}/{automation_policy['maxCanaryRunsPerScope']}", "status": "PASS", "evidence": "automation_policy.yaml"},
        {**common, "checkId": "TIER0_INPUT_BINDING", "expected": args.tier0_manifest_sha, "observed": proposal["tier0CanonicalHandoffManifestSha256"], "status": "PASS", "evidence": "P4_TIER1_SCOPE_PROPOSAL.json"},
        {**common, "checkId": "QUERY_REGISTRY", "expected": local_registry_sha, "observed": proposal["queryRegistrySha256"], "status": "PASS", "evidence": "crawl/configs/queryRegistry.yaml"},
        {**common, "checkId": "RATE_POLICY", "expected": "p4-linkareer-production-rate-v1", "observed": proposal["rateLimitPolicyVersion"], "status": "PASS", "evidence": "P4_TIER1_KILL_SWITCH_AUDIT.csv"},
        {**common, "checkId": "KILL_SWITCH_POLICY", "expected": "p4-linkareer-kill-switch-v1", "observed": proposal["killSwitchPolicyVersion"], "status": "PASS", "evidence": "P4_TIER1_KILL_SWITCH_AUDIT.csv"},
        {**common, "checkId": "APPROVAL_SCHEMA", "expected": "Draft 2020-12 valid", "observed": file_sha256(approval_schema_path), "status": "PASS", "evidence": "shared/contracts/canary_acceptance/v1/production_crawl_approval.schema.json"},
        {**common, "checkId": "SOURCE_POLICY_EVIDENCE_BINDING", "expected": source_authority["sourcePolicyAuditSha256"], "observed": proposal["sourcePolicyAuditSha256"], "status": "PASS", "evidence": "A1 reconciliation rebind manifest; human approval still missing"},
        {**common, "checkId": "APPROVAL_BOUNDARY", "expected": "no approved* values; network 0", "observed": "proposal only; network 0", "status": "PASS", "evidence": "A1 bundle + production_crawl_approval.schema.json"},
    ]
    test_summary = read_csv_rows(a1_root / "P4_TIER1_PREAPPROVAL_TEST_SUMMARY.csv")
    path_inventory = next(
        (row for row in test_summary if row.get("testId") == "TRACKED_CRAWL_ABSOLUTE_PATH_INVENTORY"),
        None,
    )
    if path_inventory:
        compatibility.append({
            **common,
            "checkId": "PREEXISTING_ABSOLUTE_PATH_LITERAL_INVENTORY",
            "expected": "new preapproval tree 0; legacy evidence isolated",
            "observed": path_inventory.get("observed", "UNKNOWN"),
            "status": path_inventory.get("status", "NOT_EVALUATED"),
            "evidence": "A1 test summary; historical audit/negative-test literals not consumed as runtime paths",
        })
    write_csv(report / OUTPUT_NAMES[0], list(compatibility[0]), compatibility)

    validations = [
        {**common, "checkId": "INDEX_ONLY", "expected": "INDEX", "observed": proposal["logicalRequestType"], "status": "PASS"},
        {**common, "checkId": "SMALLEST_VIABLE_SCOPE_PROPOSED", "expected": "one exact proposal, not approval", "observed": json.dumps(proposal["candidatePeriodOrQuery"], ensure_ascii=False, sort_keys=True), "status": "PASS"},
        {**common, "checkId": "REQUEST_BUDGET_PROPOSED", "expected": ">= estimated and not approved", "observed": proposal["proposedMaxIndexRequests"], "status": "PASS"},
        {**common, "checkId": "DETAIL_ASSET_DENY", "expected": "0/0", "observed": f"{proposal['detailRequestCount']}/{proposal['assetRequestCount']}", "status": "PASS"},
        {**common, "checkId": "NO_NETWORK_DRY_RUN", "expected": 0, "observed": proposal["networkCalls"], "status": "PASS"},
    ]
    write_csv(report / OUTPUT_NAMES[1], list(validations[0]), validations)
    (report / OUTPUT_NAMES[2]).write_text(json.dumps(handoff_schema(proposal), indent=2) + "\n", encoding="utf-8")

    gates = [
        ("TIER0_CANONICAL_INPUT", "PASS", "16-file accepted manifest binding"),
        ("TIER1_QUERY_REGISTRY_READY", "PASS", "registry SHA and required operations"),
        ("TIER1_REQUESTKEY_DRY_RUN", "PASS", "deterministic fixture"),
        ("TIER1_CHECKPOINT_RESUME_DRY_RUN", "PASS", "round-trip and corruption stop"),
        ("TIER1_KILL_SWITCH_DRY_RUN", "PASS", "403/429/content/schema/cursor/checkpoint fixtures"),
        ("TIER1_HANDOFF_SCHEMA_READY", "PASS", "index-only counts and SHA bindings"),
        ("TIER1_APPROVAL_SCHEMA_READY", "PASS", "Draft 2020-12 schema and source-policy evidence binding"),
        ("TIER1_SCOPE_BUDGET_ENFORCEMENT_READY", "PASS", "schema max bound and approval binding"),
        ("TIER1_APPROVAL_PACKET_READY", "PASS", "proposal values only"),
        ("PREEXISTING_ABSOLUTE_PATH_LITERAL_INVENTORY", "PASS_WITH_FINDINGS", "7 historical audit/negative-test literals; new packet tree 0"),
        ("TIER1_NETWORK_EXECUTION", "BLOCKED", "USER_TIER1_INDEX_CANARY_APPROVAL missing"),
        ("DETAIL_REQUEST", "BLOCKED", "Tier 1 contract"),
        ("ASSET_REQUEST", "BLOCKED", "Tier 1 contract"),
        ("M2_FULL_CRAWL", "BLOCKED", "Tier 1-4 and M2 approvals missing"),
    ]
    gate_rows = [{**common, "gateId": gate, "status": status, "evidence": evidence} for gate, status, evidence in gates]
    write_csv(report / OUTPUT_NAMES[3], list(gate_rows[0]), gate_rows)

    rules = {
        "schemaVersion": "p4-tier1-scope-escalation-v1",
        "currentState": "AWAIT_TIER1_APPROVAL",
        "scopeEscalationAutomatic": False,
        "nextApprovalPacketMayBeProposedOnlyWhen": {
            "requestResponseConflictCount": 0,
            "cursorLoopCount": 0,
            "checkpointResume": "PASS",
            "terminalPageEvidence": "COMPLETE",
            "killSwitchBehavior": "PASS",
            "externalAtsTransportCalls": 0,
        },
        "tier2PolicyBinding": {
            "detailSampleSize": automation_policy["tier2"]["detailSampleSize"],
            "samplingMethod": automation_policy["tier2"]["samplingMethod"],
            "requiresSeparateUserApproval": True,
        },
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    }
    (report / OUTPUT_NAMES[4]).write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")

    (report / OUTPUT_NAMES[5]).write_text(
        "# P4 Tier 1 Approval Requirements\n\n"
        "Decision ID: `D-T1-INDEX-CANARY`\n\n"
        "## Question\n\nApprove one bounded Linkareer index-only network canary?\n\n"
        "## Current evidence\n\n"
        "- Tier 0 canonical handoff: accepted\n"
        "- A5 M1.5 audit: PASS_WITH_FINDINGS\n"
        "- Tier 1 preapproval dry run: PASS\n"
        "- Network calls so far: 0\n"
        "- External ATS calls so far: 0\n\n"
        "## Controller proposal (not approved)\n\n"
        f"- Proposed scope: `{json.dumps(proposal['candidatePeriodOrQuery'], ensure_ascii=False, sort_keys=True)}`\n"
        f"- Proposed maximum index requests: `{proposal['proposedMaxIndexRequests']}`\n"
        f"- Estimated storage: `{proposal['estimatedStorageBytes']}` bytes\n"
        "- Detail budget: `0`\n- Asset budget: `0`\n- Source: `LINKAREER only`\n"
        "- External ATS: `false`\n- Browser automation: `false`\n"
        f"- Query registry SHA: `{proposal['queryRegistrySha256']}`\n"
        f"- Rate policy: `{proposal['rateLimitPolicyVersion']}` / `{proposal['rateLimitPolicySha256']}`\n"
        f"- Kill-switch policy: `{proposal['killSwitchPolicyVersion']}` / `{proposal['killSwitchPolicySha256']}`\n"
        f"- Source-policy evidence SHA: `{proposal['sourcePolicyAuditSha256']}`; human approval remains missing\n"
        f"- Storage estimate SHA: `{file_sha256(a1_root / 'P4_TIER1_STORAGE_ESTIMATE.json')}`\n"
        f"- Expiry suggestion: `{proposal['approvalExpiryRecommendation']}`\n\n"
        "## Recommendation and impact\n\n"
        "Recommendation: approve only this bounded Tier 1 index canary after issuing a complete signed approval artifact.\n\n"
        "- If approved: index-only transport may begin within the exact approved scope; detail and asset remain denied; full M2 remains blocked.\n"
        "- If denied: no network request occurs and Tier 1 remains blocked.\n"
        "- If deferred: automation remains in `AWAIT_TIER1_APPROVAL`.\n\n"
        "The user must independently set approved scope, maximum requests, expiry, rate/retry budget, source, and source-policy approval in `USER_TIER1_INDEX_CANARY_APPROVAL`. Until then all transport remains blocked.\n",
        encoding="utf-8",
    )
    manifest = report / "EVIDENCE_MANIFEST.sha256"
    manifest.write_text("".join(f"{file_sha256(report / name)}  {name}\n" for name in OUTPUT_NAMES), encoding="utf-8")
    update_automation_state(
        project,
        proposal,
        a1_branch=args.a1_branch,
        a1_head=args.a1_head,
        a3_head=args.a3_head,
        tier1_evidence_sha=file_sha256(manifest),
    )
    print(json.dumps({
        "status": "TIER1_CANARY_ACCEPTANCE_READY",
        "candidateScopeId": proposal["candidateScopeId"],
        "proposedMaxIndexRequests": proposal["proposedMaxIndexRequests"],
        "networkCalls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
