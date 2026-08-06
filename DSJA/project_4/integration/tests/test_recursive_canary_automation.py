from __future__ import annotations

from pathlib import Path
import sys

import yaml

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_ROOT))

from recursive_canary_automation import (  # noqa: E402
    OUTPUT_NAMES,
    REQUIRED_POLICY_FIELDS,
    sha256,
    validate_automation_policy,
    write_blocked_packet,
)


def complete_policy() -> dict:
    return {
        "schemaVersion": "p4-canary-automation-v1",
        "maxAutoRepairIterationsPerTier": 1,
        "maxCanaryRunsPerScope": 1,
        "allowedBranchPrefixes": ["integration/p4-"],
        "allowedWriteRoots": ["integration/**"],
        "requiredA1HandoffArtifacts": ["canary_plan.json"],
        "requiredA3AcceptanceArtifacts": ["P4_CANARY_GATE_STATUS.csv"],
        "requiredA5AuditArtifacts": ["P4_A5_CANARY_AUDIT.md"],
        "canaryTierDefinitions": {tier: {"mode": "TEST_ONLY"} for tier in ("TIER0", "TIER1", "TIER2", "TIER3", "TIER4")},
        "approvalSchemaVersion": "test-approval-v1",
        "sourcePolicySchemaVersion": "test-source-policy-v1",
        "networkPolicy": {
            "allowNetworkWithoutApproval": False,
            "allowExternalAts": False,
            "allowBrowserAutomation": False,
            "allowFullM2Automation": False,
        },
        "scopeEscalation": {
            "requiresNewApprovalArtifact": True,
            "requiresA5ForTier4": True,
            "requiresA5ForM2": True,
        },
        "budgetExhaustionPolicy": {
            "stopAutomaticPatch": True,
            "stopScopeEscalation": True,
            "requireHumanDecision": True,
        },
    }


def test_missing_policy_fails_closed(tmp_path):
    payload, errors = validate_automation_policy(tmp_path / "automation_policy.yaml")
    assert payload is None
    assert errors == ["AUTOMATION_POLICY_FILE_MISSING"]


def test_every_required_field_is_fail_closed(tmp_path):
    for field in REQUIRED_POLICY_FIELDS:
        policy = complete_policy()
        del policy[field]
        path = tmp_path / f"{field}.yaml"
        path.write_text(yaml.safe_dump(policy), encoding="utf-8")
        _, errors = validate_automation_policy(path)
        assert f"AUTOMATION_POLICY_FIELD_MISSING:{field}" in errors


def test_retry_and_run_budget_must_be_explicit_positive_integers(tmp_path):
    for field, value in (("maxAutoRepairIterationsPerTier", 0), ("maxCanaryRunsPerScope", None)):
        policy = complete_policy()
        policy[field] = value
        path = tmp_path / f"{field}.yaml"
        path.write_text(yaml.safe_dump(policy), encoding="utf-8")
        _, errors = validate_automation_policy(path)
        assert f"AUTOMATION_POLICY_POSITIVE_INTEGER_REQUIRED:{field}" in errors


def test_all_tiers_must_be_defined(tmp_path):
    policy = complete_policy()
    del policy["canaryTierDefinitions"]["TIER3"]
    path = tmp_path / "automation_policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    _, errors = validate_automation_policy(path)
    assert "AUTOMATION_POLICY_TIER_DEFINITION_MISSING:TIER3" in errors


def test_network_and_escalation_safety_flags_are_fail_closed(tmp_path):
    policy = complete_policy()
    policy["networkPolicy"]["allowNetworkWithoutApproval"] = True
    policy["scopeEscalation"]["requiresNewApprovalArtifact"] = False
    path = tmp_path / "automation_policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    _, errors = validate_automation_policy(path)
    assert "AUTOMATION_POLICY_FALSE_REQUIRED:networkPolicy.allowNetworkWithoutApproval" in errors
    assert "AUTOMATION_POLICY_TRUE_REQUIRED:scopeEscalation.requiresNewApprovalArtifact" in errors


def test_complete_policy_passes_structure_validation(tmp_path):
    path = tmp_path / "automation_policy.yaml"
    path.write_text(yaml.safe_dump(complete_policy()), encoding="utf-8")
    payload, errors = validate_automation_policy(path)
    assert payload is not None
    assert errors == []


def test_repository_policy_encodes_user_approved_three_two_budget():
    path = INTEGRATION_ROOT.parent / "automation_policy.yaml"
    payload, errors = validate_automation_policy(path)
    assert errors == []
    assert payload is not None
    assert payload["maxAutoRepairIterationsPerTier"] == 3
    assert payload["maxCanaryRunsPerScope"] == 2
    assert payload["networkPolicy"]["allowNetworkWithoutApproval"] is False


def test_blocked_packet_is_complete_and_checksum_bound(tmp_path):
    report = tmp_path / "reports"
    write_blocked_packet(
        report,
        tmp_path / "automation_policy.yaml",
        ["AUTOMATION_POLICY_FILE_MISSING"],
        {
            "iterationId": "TEST-ITERATION",
            "runId": "CANARY-TEST",
            "a1Branch": "agent/test",
            "a1Head": "1" * 40,
            "a3Branch": "integration/test",
            "a3Head": "2" * 40,
            "inheritedP1": "P1-TEST",
            "policyLocator": "automation_policy.yaml",
        },
    )
    assert {path.name for path in report.iterdir()} == {*OUTPUT_NAMES, "EVIDENCE_MANIFEST.sha256"}
    for line in (report / "EVIDENCE_MANIFEST.sha256").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        assert sha256(report / name) == expected
    assert "/home/" not in (report / "P4_AUTOMATION_STATE.json").read_text()
