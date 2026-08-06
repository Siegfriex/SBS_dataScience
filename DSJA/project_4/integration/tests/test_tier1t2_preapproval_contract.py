from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_ROOT))

from tier1t2_preapproval_contract import combined_approval_schema  # noqa: E402


def proposal() -> dict:
    return {
        "tier1": {
            "periodMonths": ["2026-03"],
            "queryOperations": ["INDEX"],
            "proposedMaxIndexRequests": 28,
        },
        "tier3": {"proposedMaxAssetRequests": 20},
        "queryRegistrySha256": "1" * 64,
        "sourcePolicyAuditSha256": "2" * 64,
        "rateLimitPolicyVersion": "rate-v1",
        "rateLimitPolicySha256": "3" * 64,
        "killSwitchPolicyVersion": "kill-v1",
        "killSwitchPolicySha256": "4" * 64,
        "storagePlanSha256": "7" * 64,
        "proposedRateLimitRequestsPerMinute": 60,
        "proposedRetryBudget": 3,
    }


def valid_approval() -> dict:
    return {
        "approvalId": "USER-T1T2-1",
        "approvedBy": "user",
        "approvedAtUtc": "2026-08-07T00:00:00Z",
        "expiresAtUtc": "2026-08-07T02:00:00Z",
        "approvalStatus": "APPROVED",
        "approvedSource": "LINKAREER",
        "approvedCanaryScope": {
            "periodMonths": proposal()["tier1"]["periodMonths"],
            "queryOperations": proposal()["tier1"]["queryOperations"],
        },
        "approvedScopeHash": "5" * 64,
        "approvedMaxIndexRequests": 28,
        "approvedMaxDetailRequests": 10,
        "approvedMaxAssetRequests": 20,
        "detailSamplingMethod": "DETERMINISTIC_RANDOM_WITHOUT_REPLACEMENT",
        "detailSamplingSeedFormula": "SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)",
        "replaceTerminalFailures": False,
        "linkareerHostedAssetAllowed": True,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
        "ocrMode": "QUEUE_MIME_SHA_TEXT_VOLUME_ONLY",
        "rawStorageMode": "IMMUTABLE_CONTENT_ADDRESSED_EXTERNAL_STORAGE",
        "queryRegistrySha256": "1" * 64,
        "sourcePolicyAuditSha256": "2" * 64,
        "sourcePolicyHumanApprovalRecordSha256": "6" * 64,
        "rateLimitPolicyVersion": "rate-v1",
        "rateLimitPolicySha256": "3" * 64,
        "killSwitchPolicyVersion": "kill-v1",
        "killSwitchPolicySha256": "4" * 64,
        "storagePlanSha256": "7" * 64,
        "approvedRateLimitRequestsPerMinute": 60,
        "approvedRetryBudget": 3,
    }


def test_combined_approval_schema_is_valid():
    schema = combined_approval_schema(proposal())
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(valid_approval())) == []


def test_combined_approval_rejects_budget_and_policy_expansion():
    validator = Draft202012Validator(combined_approval_schema(proposal()))
    approval = valid_approval()
    approval.update({
        "approvedMaxIndexRequests": 29,
        "approvedMaxDetailRequests": 11,
        "approvedMaxAssetRequests": 21,
        "externalAtsTransportAllowed": True,
        "browserAutomationAllowed": True,
    })
    paths = {".".join(str(part) for part in error.absolute_path) for error in validator.iter_errors(approval)}
    assert {
        "approvedMaxIndexRequests",
        "approvedMaxDetailRequests",
        "approvedMaxAssetRequests",
        "externalAtsTransportAllowed",
        "browserAutomationAllowed",
    } <= paths


def test_combined_approval_requires_human_source_policy_and_user_budget():
    validator = Draft202012Validator(combined_approval_schema(proposal()))
    approval = deepcopy(valid_approval())
    del approval["sourcePolicyHumanApprovalRecordSha256"]
    del approval["approvedRateLimitRequestsPerMinute"]
    del approval["approvedRetryBudget"]
    messages = [error.message for error in validator.iter_errors(approval)]
    assert any("sourcePolicyHumanApprovalRecordSha256" in message for message in messages)
    assert any("approvedRateLimitRequestsPerMinute" in message for message in messages)
    assert any("approvedRetryBudget" in message for message in messages)


def test_terminal_failures_cannot_be_replaced():
    validator = Draft202012Validator(combined_approval_schema(proposal()))
    approval = valid_approval()
    approval["replaceTerminalFailures"] = True
    paths = {".".join(str(part) for part in error.absolute_path) for error in validator.iter_errors(approval)}
    assert "replaceTerminalFailures" in paths
