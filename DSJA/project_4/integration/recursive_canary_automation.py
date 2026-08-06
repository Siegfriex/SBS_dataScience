#!/usr/bin/env python3
"""Fail-closed bootstrap for the P4 recursive canary automation controller.

The controller deliberately performs no network transport.  A complete,
machine-readable automation policy is required before an iteration can start.
When the policy is absent or incomplete, it publishes a Git-safe evidence
packet and exits non-zero without inventing retry budgets or canary scopes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


AGENT_ID = "P4-RECURSIVE-CANARY-M2-ORCHESTRATOR"
REQUIRED_POLICY_FIELDS = (
    "schemaVersion",
    "maxAutoRepairIterationsPerTier",
    "maxCanaryRunsPerScope",
    "allowedBranchPrefixes",
    "allowedWriteRoots",
    "requiredA1HandoffArtifacts",
    "requiredA3AcceptanceArtifacts",
    "requiredA5AuditArtifacts",
    "canaryTierDefinitions",
    "approvalSchemaVersion",
    "sourcePolicySchemaVersion",
    "networkPolicy",
    "scopeEscalation",
    "budgetExhaustionPolicy",
)
REQUIRED_TIERS = ("TIER0", "TIER1", "TIER2", "TIER3", "TIER4")
OUTPUT_NAMES = (
    "P4_AUTOMATION_STATE.json",
    "P4_AUTOMATION_ITERATION_LOG.jsonl",
    "P4_AUTOMATION_DEFECT_BACKLOG.csv",
    "P4_AUTOMATION_SCOPE_REGISTER.csv",
    "P4_AUTOMATION_APPROVAL_QUEUE.md",
    "P4_AUTOMATION_AGENT_STATUS.csv",
    "P4_AUTOMATION_PROMOTION_DECISIONS.csv",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_automation_policy(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, ["AUTOMATION_POLICY_FILE_MISSING"]
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return None, ["AUTOMATION_POLICY_PARSE_ERROR"]
    if not isinstance(payload, dict):
        return None, ["AUTOMATION_POLICY_NOT_OBJECT"]

    errors: list[str] = []
    for field in REQUIRED_POLICY_FIELDS:
        if field not in payload:
            errors.append(f"AUTOMATION_POLICY_FIELD_MISSING:{field}")

    for field in ("maxAutoRepairIterationsPerTier", "maxCanaryRunsPerScope"):
        value = payload.get(field)
        if field in payload and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            errors.append(f"AUTOMATION_POLICY_POSITIVE_INTEGER_REQUIRED:{field}")

    for field in (
        "allowedBranchPrefixes",
        "allowedWriteRoots",
        "requiredA1HandoffArtifacts",
        "requiredA3AcceptanceArtifacts",
        "requiredA5AuditArtifacts",
    ):
        value = payload.get(field)
        if field in payload and (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            errors.append(f"AUTOMATION_POLICY_NONEMPTY_STRING_LIST_REQUIRED:{field}")

    tiers = payload.get("canaryTierDefinitions")
    if "canaryTierDefinitions" in payload:
        if not isinstance(tiers, dict):
            errors.append("AUTOMATION_POLICY_TIER_DEFINITIONS_NOT_OBJECT")
        else:
            for tier in REQUIRED_TIERS:
                if tier not in tiers or not isinstance(tiers[tier], dict) or not tiers[tier]:
                    errors.append(f"AUTOMATION_POLICY_TIER_DEFINITION_MISSING:{tier}")

    for field in ("approvalSchemaVersion", "sourcePolicySchemaVersion"):
        value = payload.get(field)
        if field in payload and (not isinstance(value, str) or not value.strip()):
            errors.append(f"AUTOMATION_POLICY_VERSION_REQUIRED:{field}")
    if payload.get("schemaVersion") != "p4-canary-automation-v1":
        errors.append("AUTOMATION_POLICY_SCHEMA_VERSION_INVALID")

    required_false = {
        "networkPolicy": (
            "allowNetworkWithoutApproval", "allowExternalAts",
            "allowBrowserAutomation", "allowFullM2Automation",
        ),
    }
    required_true = {
        "scopeEscalation": (
            "requiresNewApprovalArtifact", "requiresA5ForTier4", "requiresA5ForM2",
        ),
        "budgetExhaustionPolicy": (
            "stopAutomaticPatch", "stopScopeEscalation", "requireHumanDecision",
        ),
    }
    for section, fields in required_false.items():
        value = payload.get(section)
        if not isinstance(value, dict):
            if section in payload:
                errors.append(f"AUTOMATION_POLICY_SECTION_NOT_OBJECT:{section}")
            continue
        for field in fields:
            if value.get(field) is not False:
                errors.append(f"AUTOMATION_POLICY_FALSE_REQUIRED:{section}.{field}")
    for section, fields in required_true.items():
        value = payload.get(section)
        if not isinstance(value, dict):
            if section in payload:
                errors.append(f"AUTOMATION_POLICY_SECTION_NOT_OBJECT:{section}")
            continue
        for field in fields:
            if value.get(field) is not True:
                errors.append(f"AUTOMATION_POLICY_TRUE_REQUIRED:{section}.{field}")
    return payload, errors


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_blocked_packet(
    report_root: Path,
    policy_path: Path,
    errors: list[str],
    metadata: dict[str, str],
) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    iteration_id = metadata["iterationId"]
    open_defects = ["AUTOMATION-P1-POLICY-INCOMPLETE", *metadata["inheritedP1"].split(",")]
    state = {
        "agentId": AGENT_ID,
        "state": "BLOCKED_BY_EVIDENCE",
        "tier": "TIER0",
        "iterationId": iteration_id,
        "updatedAtUtc": now,
        "automationPolicyPath": metadata["policyLocator"],
        "automationPolicyStatus": "INCOMPLETE",
        "automationPolicyErrors": errors,
        "blockedReason": "AUTOMATION_POLICY_INCOMPLETE",
        "latestAcceptedBaseSha": metadata["a3Head"],
        "a1CanonicalHandoff": {
            "branch": metadata["a1Branch"],
            "headCommit": metadata["a1Head"],
            "runId": metadata["runId"],
            "artifactCount": 16,
            "status": "EVIDENCE_AVAILABLE_NOT_CONSUMED_BY_AUTOMATION_LOOP",
        },
        "a3ExistingAcceptance": {
            "branch": metadata["a3Branch"],
            "headCommit": metadata["a3Head"],
            "status": "EXISTING_REACCEPTANCE_AVAILABLE",
        },
        "a5Status": "NOT_REQUIRED",
        "approvalStatus": "NOT_EVALUATED",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "acceptedScope": None,
        "nextRequiredAction": "PROVIDE_COMPLETE_AUTOMATION_POLICY",
        "fixedDefects": ["CANARY-P1-EVIDENCE-BUNDLE"],
        "openDefects": open_defects,
        "m2FullCrawlEligible": False,
        "crawlReleaseEligible": False,
        "analysisEligible": False,
    }
    (report_root / OUTPUT_NAMES[0]).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    iteration = {
        "iterationId": iteration_id,
        "tier": "TIER0",
        "runId": metadata["runId"],
        "inputCommit": metadata["a3Head"],
        "outputCommit": None,
        "approvalId": "NONE",
        "networkCalls": 0,
        "scope": None,
        "defectFamily": "AUTOMATION_POLICY",
        "repairAction": "NONE_FAIL_CLOSED",
        "testResult": "NOT_RUN_POLICY_PRECONDITION_FAILED",
        "acceptanceStatus": "NOT_EVALUATED",
        "nextState": "BLOCKED_BY_EVIDENCE",
        "blockedReason": "AUTOMATION_POLICY_INCOMPLETE",
        "recordedAtUtc": now,
    }
    (report_root / OUTPUT_NAMES[1]).write_text(
        json.dumps(iteration, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    write_csv(
        report_root / OUTPUT_NAMES[2],
        ["defectId", "severity", "family", "status", "evidence", "requiredAction"],
        [{
            "defectId": "AUTOMATION-P1-POLICY-INCOMPLETE",
            "severity": "P1",
            "family": "AUTOMATION_POLICY",
            "status": "OPEN",
            "evidence": ";".join(errors),
            "requiredAction": "Provide a complete automation_policy.yaml; do not infer budgets or scopes",
        }],
    )
    write_csv(
        report_root / OUTPUT_NAMES[3],
        ["tier", "state", "acceptedScope", "approvalRequired", "networkAllowed", "blockedReason"],
        [
            {
                "tier": tier,
                "state": "EVIDENCE_AVAILABLE" if tier == "TIER0" else "NOT_STARTED",
                "acceptedScope": "NONE",
                "approvalRequired": "false" if tier == "TIER0" else "true",
                "networkAllowed": "false",
                "blockedReason": "AUTOMATION_POLICY_INCOMPLETE",
            }
            for tier in REQUIRED_TIERS
        ],
    )
    (report_root / OUTPUT_NAMES[4]).write_text(
        "# P4 Automation Approval Queue\n\n"
        "Current state: `BLOCKED_BY_EVIDENCE`\n\n"
        "No network or scope approval is requested yet. The controller must first receive "
        "a complete `automation_policy.yaml` containing every required field and explicit "
        "retry, branch, write-root, artifact, tier, approval-schema, and source-policy value. "
        "No missing value was inferred.\n",
        encoding="utf-8",
    )
    write_csv(
        report_root / OUTPUT_NAMES[5],
        ["agent", "branch", "headCommit", "status", "nextAction"],
        [
            {"agent": "A1", "branch": metadata["a1Branch"], "headCommit": metadata["a1Head"], "status": "CANONICAL_HANDOFF_PUBLISHED", "nextAction": "WAIT"},
            {"agent": "A3", "branch": metadata["a3Branch"], "headCommit": metadata["a3Head"], "status": "AUTOMATION_BOOTSTRAP_BLOCKED", "nextAction": "VALIDATE_COMPLETE_POLICY"},
            {"agent": "A5", "branch": "NONE", "headCommit": "NONE", "status": "NOT_REQUIRED", "nextAction": "NONE"},
        ],
    )
    write_csv(
        report_root / OUTPUT_NAMES[6],
        ["gate", "decision", "evidence", "eligible"],
        [
            {"gate": "TIER0_GLOBAL_ACCEPTANCE", "decision": "NOT_EVALUATED", "evidence": "automation policy precondition failed", "eligible": "false"},
            {"gate": "TIER1_NETWORK_CANARY", "decision": "BLOCKED", "evidence": "Tier 0 automation acceptance not completed and no Tier 1 approval", "eligible": "false"},
            {"gate": "M2_FULL_CRAWL", "decision": "BLOCKED", "evidence": "Tier 0-4 and human approval gates unmet", "eligible": "false"},
            {"gate": "CRAWL_RELEASE", "decision": "BLOCKED", "evidence": "no production release", "eligible": "false"},
            {"gate": "ANALYSIS", "decision": "BLOCKED", "evidence": "no production data readiness", "eligible": "false"},
        ],
    )
    lines = [f"{sha256(report_root / name)}  {name}" for name in OUTPUT_NAMES]
    (report_root / "EVIDENCE_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tier0_accepted_packet(
    report_root: Path,
    policy_path: Path,
    policy: dict[str, Any],
    decision: dict[str, Any],
    metadata: dict[str, str],
) -> None:
    """Publish the controller state after a zero-network Tier 0 acceptance."""
    report_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    iteration_id = metadata["iterationId"]
    inherited_p1 = [value for value in metadata["inheritedP1"].split(",") if value]
    state = {
        "agentId": AGENT_ID,
        "state": "AWAIT_TIER1_APPROVAL",
        "tier": "TIER1",
        "iterationId": iteration_id,
        "updatedAtUtc": now,
        "automationPolicyPath": metadata["policyLocator"],
        "automationPolicySha256": sha256(policy_path),
        "automationPolicyStatus": "PASS",
        "maxAutoRepairIterationsPerTier": policy["maxAutoRepairIterationsPerTier"],
        "maxCanaryRunsPerScope": policy["maxCanaryRunsPerScope"],
        "a1CanonicalHandoff": {
            "branch": metadata["a1Branch"],
            "headCommit": metadata["a1Head"],
            "runId": metadata["runId"],
            "artifactCount": decision["canonicalHandoffArtifactCount"],
            "manifestSha256": decision["canonicalHandoffManifestSha256"],
            "status": "ACCEPTED",
        },
        "a3Acceptance": {
            "branch": metadata["a3Branch"],
            "headCommitBeforeAutomationReport": metadata["a3Head"],
            "status": decision["status"],
        },
        "a5Status": "NOT_REQUIRED",
        "approvalStatus": "TIER1_APPROVAL_MISSING",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "acceptedScope": "TIER0_FIXTURE_ONLY",
        "nextRequiredAction": "USER_TIER1_INDEX_CANARY_APPROVAL_ARTIFACT",
        "fixedDefects": ["CANARY-P1-EVIDENCE-BUNDLE", "AUTOMATION-P1-POLICY-INCOMPLETE"],
        "openDefects": inherited_p1,
        "m2FullCrawlEligible": False,
        "crawlReleaseEligible": False,
        "analysisEligible": False,
    }
    (report_root / OUTPUT_NAMES[0]).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    previous_log = ""
    log_path = report_root / OUTPUT_NAMES[1]
    if log_path.is_file():
        retained: list[str] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("iterationId") != iteration_id:
                retained.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
        previous_log = "".join(f"{line}\n" for line in retained)
    iteration = {
        "iterationId": iteration_id,
        "tier": "TIER0",
        "runId": metadata["runId"],
        "inputCommit": metadata["a3Head"],
        "outputCommit": None,
        "approvalId": "NONE",
        "networkCalls": 0,
        "scope": "TIER0_FIXTURE_ONLY",
        "defectFamily": "POLICY_PORTABILITY_BASELINE",
        "repairAction": "CREATE_APPROVED_AUTOMATION_POLICY_AND_REACCEPT_TIER0",
        "testResult": metadata["testResult"],
        "acceptanceStatus": "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE",
        "nextState": "AWAIT_TIER1_APPROVAL",
        "blockedReason": None,
        "recordedAtUtc": now,
    }
    log_path.write_text(
        previous_log + json.dumps(iteration, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    defect_rows = [{
        "defectId": defect_id,
        "severity": "P1",
        "family": "INHERITED_M1_5",
        "status": "OPEN",
        "evidence": "M1.5 reconciliation finding; not repaired by Tier 0 automation",
        "requiredAction": "Keep downstream production, NCS-quality, M3, or analysis gate blocked as applicable",
    } for defect_id in inherited_p1]
    defect_rows.extend([
        {
            "defectId": "AUTOMATION-P1-POLICY-INCOMPLETE",
            "severity": "P1",
            "family": "AUTOMATION_POLICY",
            "status": "FIXED",
            "evidence": f"automation_policy.yaml SHA-256 {sha256(policy_path)}",
            "requiredAction": "NONE",
        },
        {
            "defectId": "CANARY-P1-EVIDENCE-BUNDLE",
            "severity": "P1",
            "family": "LINEAGE",
            "status": "FIXED",
            "evidence": f"16/16 canonical handoff; manifest {decision['canonicalHandoffManifestSha256']}",
            "requiredAction": "NONE",
        },
    ])
    write_csv(
        report_root / OUTPUT_NAMES[2],
        ["defectId", "severity", "family", "status", "evidence", "requiredAction"],
        defect_rows,
    )
    scope_rows = [
        {"tier": "TIER0", "state": "ACCEPTED", "acceptedScope": "TIER0_FIXTURE_ONLY", "approvalRequired": "false", "networkAllowed": "false", "blockedReason": "NONE"},
        {"tier": "TIER1", "state": "AWAITING_APPROVAL", "acceptedScope": "NONE", "approvalRequired": "true", "networkAllowed": "false", "blockedReason": "TIER1_APPROVAL_MISSING"},
    ]
    scope_rows.extend({
        "tier": tier,
        "state": "NOT_STARTED",
        "acceptedScope": "NONE",
        "approvalRequired": "true",
        "networkAllowed": "false",
        "blockedReason": "UPSTREAM_TIER_NOT_ACCEPTED",
    } for tier in ("TIER2", "TIER3", "TIER4"))
    write_csv(
        report_root / OUTPUT_NAMES[3],
        ["tier", "state", "acceptedScope", "approvalRequired", "networkAllowed", "blockedReason"],
        scope_rows,
    )
    (report_root / OUTPUT_NAMES[4]).write_text(
        "# P4 Automation Approval Queue\n\n"
        "## D-CANARY-T1-001\n\n"
        "- Question: Approve a separate Tier 1 Linkareer index-only network canary?\n"
        "- Current evidence: Tier 0 fixture-only canonical handoff accepted; network calls remain 0.\n"
        "- Requested scope: `USER_DECISION_REQUIRED`\n"
        "- Request budget: `USER_DECISION_REQUIRED`\n"
        "- Detail budget: `0`\n"
        "- Asset budget: `0`\n"
        "- Rate-limit policy version: `USER_DECISION_REQUIRED`\n"
        "- Kill-switch policy version: `USER_DECISION_REQUIRED`\n"
        "- Source-policy constraints: Linkareer index only; external ATS and browser automation denied.\n"
        "- Expiration: `USER_DECISION_REQUIRED`\n"
        "- Recommended option: defer until a complete signed approval artifact is supplied.\n"
        "- Impact if approved: only the approved Tier 1 index request scope may run.\n"
        "- Impact if denied or deferred: network calls remain 0 and no scope expands.\n\n"
        "This queue is not an approval artifact and authorizes no transport.\n",
        encoding="utf-8",
    )
    write_csv(
        report_root / OUTPUT_NAMES[5],
        ["agent", "branch", "headCommit", "status", "nextAction"],
        [
            {"agent": "A1", "branch": metadata["a1Branch"], "headCommit": metadata["a1Head"], "status": "CANONICAL_HANDOFF_ACCEPTED", "nextAction": "AWAIT_TIER1_APPROVAL"},
            {"agent": "A3", "branch": metadata["a3Branch"], "headCommit": metadata["a3Head"], "status": "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE", "nextAction": "HOLD_NETWORK_GATE"},
            {"agent": "A5", "branch": "NONE", "headCommit": "NONE", "status": "NOT_REQUIRED", "nextAction": "TIER4_ONLY"},
        ],
    )
    write_csv(
        report_root / OUTPUT_NAMES[6],
        ["gate", "decision", "evidence", "eligible"],
        [
            {"gate": "TIER0_GLOBAL_ACCEPTANCE", "decision": "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE", "evidence": decision["canonicalHandoffManifestSha256"], "eligible": "true"},
            {"gate": "TIER1_NETWORK_CANARY", "decision": "AWAITING_USER_APPROVAL", "evidence": "no production_crawl_approval.json", "eligible": "false"},
            {"gate": "M2_FULL_CRAWL", "decision": "BLOCKED", "evidence": "Tier 1-4 and human approval gates unmet", "eligible": "false"},
            {"gate": "CRAWL_RELEASE", "decision": "BLOCKED", "evidence": "no production release", "eligible": "false"},
            {"gate": "ANALYSIS", "decision": "BLOCKED", "evidence": "no production data readiness", "eligible": "false"},
        ],
    )
    lines = [f"{sha256(report_root / name)}  {name}" for name in OUTPUT_NAMES]
    (report_root / "EVIDENCE_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--report-root", type=Path)
    parser.add_argument("--iteration-id", default="P4_AUTO_T0_20260807_01")
    parser.add_argument("--run-id", default="CANARY_T0_20260807_03")
    parser.add_argument("--a1-branch", default="agent/p4-a1-canary-crawl-v1")
    parser.add_argument("--a1-head", default="13205c11e7de3dfc7b005b0fde16197281eb857f")
    parser.add_argument("--a3-branch", default="integration/p4-canary-acceptance-v1")
    parser.add_argument("--a3-head", required=True)
    parser.add_argument("--a1-handoff-root", type=Path)
    parser.add_argument("--test-command", default="python -m pytest -q integration/tests")
    parser.add_argument("--test-exit-code", type=int, default=0)
    parser.add_argument("--test-pass-count", type=int, default=0)
    parser.add_argument("--inherited-p1", default="P1-UNIFIED-001,P1-UNIFIED-002,P1-UNIFIED-003,P1-UNIFIED-004,P1-UNIFIED-005")
    args = parser.parse_args()

    project = args.project_root.resolve()
    policy_path = (args.policy or project / "automation_policy.yaml").resolve()
    report_root = (args.report_root or project / "reports/automation").resolve()
    try:
        policy_locator = policy_path.relative_to(project).as_posix()
    except ValueError:
        policy_locator = "EXTERNAL_POLICY_PATH_REDACTED"
    policy, errors = validate_automation_policy(policy_path)
    if errors:
        write_blocked_packet(
            report_root,
            policy_path,
            errors,
            {
                "iterationId": args.iteration_id,
                "runId": args.run_id,
                "a1Branch": args.a1_branch,
                "a1Head": args.a1_head,
                "a3Branch": args.a3_branch,
                "a3Head": args.a3_head,
                "inheritedP1": args.inherited_p1,
                "policyLocator": policy_locator,
            },
        )
        return 2
    assert policy is not None
    if args.a1_handoff_root is None:
        raise SystemExit("--a1-handoff-root is required after policy validation")
    handoff = args.a1_handoff_root.resolve()
    plan_path = handoff / "canary_plan.json"
    if not plan_path.is_file():
        raise SystemExit("Tier 0 canary_plan.json is missing")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    scope = plan.get("canaryScope") if isinstance(plan.get("canaryScope"), dict) else {}
    if not (
        int(plan.get("networkCalls", -1)) == 0
        and int(plan.get("detailRequestCount", -1)) == 0
        and int(plan.get("assetRequestCount", -1)) == 0
        and scope.get("tier") == 0
        and scope.get("mode") == "fixture-only"
    ):
        raise SystemExit("Tier 0 plan is not a zero-network fixture-only run")
    actual_names = {path.name for path in handoff.iterdir() if path.is_file()}
    expected_names = set(policy["requiredA1HandoffArtifacts"])
    if actual_names != expected_names:
        raise SystemExit("Tier 0 handoff does not match requiredA1HandoffArtifacts")
    if not any(args.a1_branch.startswith(prefix) for prefix in policy["allowedBranchPrefixes"]):
        raise SystemExit("A1 branch is outside allowedBranchPrefixes")
    if not any(args.a3_branch.startswith(prefix) for prefix in policy["allowedBranchPrefixes"]):
        raise SystemExit("A3 branch is outside allowedBranchPrefixes")

    canary_report_root = project / "reports/canary_integration"
    validator_command = [
        sys.executable,
        str(project / "integration/validate_canary_handoff.py"),
        "--project-root", str(project),
        "--handoff-root", str(handoff),
        "--report-root", str(canary_report_root),
        "--a1-branch", args.a1_branch,
        "--a1-commit", args.a1_head,
        "--a5-status", "NOT_REQUIRED",
        "--a5-commit", "NONE",
        "--test-command", args.test_command,
        "--test-exit-code", str(args.test_exit_code),
        "--test-pass-count", str(args.test_pass_count),
    ]
    completed = subprocess.run(validator_command, cwd=project, text=True, capture_output=True)
    if completed.returncode != 0:
        raise SystemExit(f"Tier 0 A3 acceptance failed: {completed.stdout.strip()} {completed.stderr.strip()}")
    decision_path = canary_report_root / f"P4_CANARY_SCOPE_ESCALATION_DECISION_{args.run_id}.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if decision.get("status") != "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE":
        raise SystemExit("Tier 0 A3 decision did not accept the debug scope")
    for pattern in policy["requiredA3AcceptanceArtifacts"]:
        if not list(canary_report_root.glob(pattern)):
            raise SystemExit(f"Required A3 acceptance artifact missing: {pattern}")

    write_tier0_accepted_packet(
        report_root,
        policy_path,
        policy,
        decision,
        {
            "iterationId": args.iteration_id,
            "runId": args.run_id,
            "a1Branch": args.a1_branch,
            "a1Head": args.a1_head,
            "a3Branch": args.a3_branch,
            "a3Head": args.a3_head,
            "inheritedP1": args.inherited_p1,
            "policyLocator": policy_locator,
            "testResult": f"exit={args.test_exit_code};passed={args.test_pass_count}",
        },
    )
    print(json.dumps({
        "state": "AWAIT_TIER1_APPROVAL",
        "tier0Status": decision["status"],
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
