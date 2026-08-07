from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_ROOT))

from tier1_preapproval_contract import (  # noqa: E402
    forbidden_key_paths,
    validate_empty_handoff_schema,
    validate_scope_proposal,
)
from prepare_tier1_preapproval import handoff_schema  # noqa: E402


def valid_proposal() -> dict:
    return {
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "logicalRequestType": "INDEX",
        "networkCalls": 0,
        "detailRequestCount": 0,
        "assetRequestCount": 0,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
        "tier0CanonicalHandoffManifestSha256": "a" * 64,
        "candidateScopeId": "PROPOSAL-1",
        "candidatePeriodOrQuery": {"periodMonth": "PROPOSAL_ONLY"},
        "estimatedIndexRequests": 2,
        "proposedMaxIndexRequests": 2,
        "estimatedStorageBytes": 1024,
        "expectedPaginationDepth": 1,
        "queryRegistrySha256": "b" * 64,
        "rateLimitPolicyVersion": "rate-v1",
        "rateLimitPolicySha256": "c" * 64,
        "killSwitchPolicyVersion": "kill-v1",
        "killSwitchPolicySha256": "d" * 64,
        "approvalExpiryRecommendation": "PT24H",
        "riskLevel": "LOW",
        "riskReason": "fixture evidence",
    }


def test_valid_scope_proposal_passes():
    assert validate_scope_proposal(valid_proposal(), "a" * 64) == []


def test_approved_values_are_forbidden_even_when_nested():
    proposal = valid_proposal()
    proposal["nested"] = {"approvedMaxRequests": 2}
    assert forbidden_key_paths(proposal) == ["nested.approvedMaxRequests"]
    assert any(error.startswith("TIER1_APPROVAL_VALUE_PREMATURE") for error in validate_scope_proposal(proposal, "a" * 64))


def test_scope_cannot_include_detail_asset_or_network():
    proposal = valid_proposal()
    proposal.update({"networkCalls": 1, "detailRequestCount": 1, "assetRequestCount": 1})
    errors = validate_scope_proposal(proposal, "a" * 64)
    assert "TIER1_SCOPE_FIELD_MISMATCH:networkCalls" in errors
    assert "TIER1_SCOPE_FIELD_MISMATCH:detailRequestCount" in errors
    assert "TIER1_SCOPE_FIELD_MISMATCH:assetRequestCount" in errors


def test_empty_handoff_schema_requires_transport_counts(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "required": ["runId"]}), encoding="utf-8")
    assert validate_empty_handoff_schema(path) == ["TIER1_EMPTY_HANDOFF_SCHEMA_REQUIRED_FIELDS_MISSING"]


def test_a3_tier1_handoff_schema_is_valid_and_budget_bounded():
    schema = handoff_schema(valid_proposal())
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["requestCount"]["maximum"] == 2
    assert schema["properties"]["detailRequestCount"] == {"const": 0}
    assert schema["properties"]["assetRequestCount"] == {"const": 0}
    assert schema["properties"]["requestsAfterKillSwitchStop"] == {"const": 0}


def test_a3_handoff_schema_rejects_budget_scope_and_cursor_violations():
    schema = handoff_schema(valid_proposal())
    payload = {
        "runId": "CANARY-T1-1",
        "dataVersion": "canary-t1-1",
        "approvalId": "USER-APPROVAL-1",
        "approvalArtifactSha256": "1" * 64,
        "logicalRequestType": "INDEX",
        "approvedScopeHash": "2" * 64,
        "requestCount": 1,
        "detailRequestCount": 0,
        "assetRequestCount": 0,
        "externalAtsTransportCalls": 0,
        "browserAutomationCalls": 0,
        "requestManifestSha256": "3" * 64,
        "checkpointManifestSha256": "4" * 64,
        "terminalPageEvidenceSha256": "5" * 64,
        "requestAttempts": [{
            "requestAttemptId": "ATT-1", "requestKey": "6" * 64,
            "logicalRequestType": "INDEX", "periodMonth": "2026-03",
            "pageOrCursor": 1, "startedAtUtc": "2026-08-07T00:00:00Z",
            "completedAtUtc": "2026-08-07T00:00:01Z", "responseSha256": "7" * 64,
            "checkpointId": "CP-1", "terminalStatus": "FETCHED_VALID",
        }],
        "terminalPages": [{
            "periodMonth": "2026-03", "pageOrCursor": 1, "terminal": True,
            "cursorLoopDetected": False, "evidenceSha256": "8" * 64,
        }],
        "checkpoint": {
            "checkpointId": "CP-1", "runId": "CANARY-T1-1",
            "completedRequestKeys": ["6" * 64], "requestLedgerOffset": 1,
            "rawObjectManifestSha256": "9" * 64, "coverageSnapshotSha256": "a" * 64,
        },
        "requestsAfterKillSwitchStop": 0,
        "status": "CANARY_VALIDATION",
    }
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(payload)) == []
    payload["requestCount"] = 3
    payload["detailRequestCount"] = 1
    payload["terminalPages"][0]["cursorLoopDetected"] = True
    paths = {".".join(str(value) for value in error.absolute_path) for error in validator.iter_errors(payload)}
    assert {"requestCount", "detailRequestCount", "terminalPages.0.cursorLoopDetected"} <= paths
