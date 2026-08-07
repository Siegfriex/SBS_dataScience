"""Fail-closed contracts for the combined Tier 1 index/detail/asset proposal.

This module validates proposal evidence only.  It never grants transport
authority and it cannot turn proposed limits into approved limits.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REQUIRED_A1_TIER1T2_ARTIFACTS = (
    "P4_TIER1T2_SCOPE_PROPOSAL.json",
    "P4_TIER2_DETAIL_SAMPLE_CONTRACT.json",
    "P4_TIER3_ASSET_REQUEST_ESTIMATE.json",
    "P4_TIER1T2_STORAGE_ESTIMATE.json",
    "P4_TIER1T2_POLICY_AUDIT.csv",
    "P4_TIER1T2_PREAPPROVAL_TEST_SUMMARY.csv",
    "P4_TIER1T2_COMBINED_APPROVAL_PACKET.md",
    "EVIDENCE_MANIFEST.sha256",
)

FORBIDDEN_APPROVAL_KEYS = {
    "approvalId",
    "approvedBy",
    "approvedAtUtc",
    "expiresAtUtc",
    "approvedCanaryScope",
    "approvedMaxRequests",
    "approvedMaxIndexRequests",
    "approvedMaxDetailRequests",
    "approvedMaxAssetRequests",
    "approvedRateLimit",
    "approvedRetryBudget",
    "approvedSource",
    "sourcePolicyHumanApprovalRecordSha256",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _forbidden_paths(value: Any, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            locator = f"{prefix}.{key}" if prefix else key
            if key in FORBIDDEN_APPROVAL_KEYS:
                hits.append(locator)
            hits.extend(_forbidden_paths(child, locator))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_forbidden_paths(child, f"{prefix}[{index}]"))
    return hits


def validate_evidence_manifest(root: Path) -> list[str]:
    manifest = root / "EVIDENCE_MANIFEST.sha256"
    if not manifest.is_file():
        return ["TIER1T2_EVIDENCE_MANIFEST_MISSING"]
    errors: list[str] = []
    declared: set[str] = set()
    for line_no, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            errors.append(f"TIER1T2_EVIDENCE_LINE_INVALID:{line_no}")
            continue
        expected, name = parts[0], parts[1].strip()
        declared.add(name)
        target = root / name
        if not target.is_file():
            errors.append(f"TIER1T2_EVIDENCE_TARGET_MISSING:{name}")
        elif file_sha256(target) != expected:
            errors.append(f"TIER1T2_EVIDENCE_SHA_MISMATCH:{name}")
    expected_names = set(REQUIRED_A1_TIER1T2_ARTIFACTS) - {"EVIDENCE_MANIFEST.sha256"}
    if declared != expected_names:
        errors.append("TIER1T2_EVIDENCE_DECLARATION_SET_MISMATCH")
    return errors


def validate_a1_bundle(root: Path, tier1_head: str) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    actual = {path.name for path in root.iterdir() if path.is_file()} if root.is_dir() else set()
    if actual != set(REQUIRED_A1_TIER1T2_ARTIFACTS):
        errors.append("TIER1T2_FILE_SET_MISMATCH")
    errors.extend(validate_evidence_manifest(root))

    payloads: dict[str, Any] = {}
    for name in REQUIRED_A1_TIER1T2_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            payloads[name] = json.loads((root / name).read_text(encoding="utf-8"))
            for locator in _forbidden_paths(payloads[name]):
                errors.append(f"TIER1T2_APPROVAL_VALUE_PREMATURE:{name}:{locator}")

    proposal = payloads.get("P4_TIER1T2_SCOPE_PROPOSAL.json", {})
    sample = payloads.get("P4_TIER2_DETAIL_SAMPLE_CONTRACT.json", {})
    asset = payloads.get("P4_TIER3_ASSET_REQUEST_ESTIMATE.json", {})
    storage = payloads.get("P4_TIER1T2_STORAGE_ESTIMATE.json", {})

    exact = {
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "networkCalls": 0,
        "credentialedApiCalls": 0,
        "externalAtsTransportCalls": 0,
        "browserAutomationCalls": 0,
        "tier1SourceCommit": tier1_head,
        "sequentialApprovalRequired": True,
    }
    for field, expected in exact.items():
        if proposal.get(field) != expected:
            errors.append(f"TIER1T2_PROPOSAL_FIELD_MISMATCH:{field}")
    tier1 = proposal.get("tier1", {})
    tier2 = proposal.get("tier2", {})
    tier3 = proposal.get("tier3", {})
    for field, value in (
        ("proposedMaxIndexRequests", tier1.get("proposedMaxIndexRequests")),
        ("proposedMaxAssetRequests", tier3.get("proposedMaxAssetRequests")),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"TIER1T2_POSITIVE_INTEGER_REQUIRED:{field}")
    if tier2.get("sampleSize") != 10 or tier2.get("proposedMaxDetailRequests") != 10:
        errors.append("TIER1T2_DETAIL_SAMPLE_OR_MAX_MISMATCH")

    sample_exact = {
        "contractStatus": "NOT_EVALUATED_AWAITING_TIER1_DISCOVERY",
        "sampleFrame": "UNIQUE_POSTING_IDS_FROM_ACCEPTED_TIER1_DISCOVERY_MANIFEST",
        "sampleSize": 10,
        "samplingMethod": "DETERMINISTIC_RANDOM_WITHOUT_REPLACEMENT",
        "replacement": False,
        "terminalFailureReplacementAllowed": False,
        "selectionManifest": "detail_canary_sample_manifest.json",
    }
    for field, expected in sample_exact.items():
        if sample.get(field) != expected:
            errors.append(f"TIER1T2_SAMPLE_FIELD_MISMATCH:{field}")
    if sample.get("samplingSeedExpression") != "SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)":
        errors.append("TIER1T2_SAMPLE_SEED_FORMULA_MISMATCH")
    if sample.get("postingIds") not in (None, []):
        errors.append("TIER1T2_SAMPLE_IDS_PREMATURE")

    proposed_asset_max = tier3.get("proposedMaxAssetRequests")
    if asset.get("proposalStatus") != "PROPOSED_NOT_APPROVED":
        errors.append("TIER1T2_ASSET_ESTIMATE_STATUS_INVALID")
    if asset.get("networkCalls") != 0:
        errors.append("TIER1T2_ASSET_ESTIMATE_NETWORK_NONZERO")
    if asset.get("proposedMaxAssetRequests") != proposed_asset_max:
        errors.append("TIER1T2_ASSET_MAX_BINDING_MISMATCH")
    if asset.get("externalAtsCandidateRows") != 0 or asset.get("hostEvidence") != ["api.linkareer.com"]:
        errors.append("TIER1T2_ASSET_HOST_POLICY_MISMATCH")
    if not isinstance(asset.get("evidencePostingRows"), int) or asset.get("evidencePostingRows", 0) < 1:
        errors.append("TIER1T2_ASSET_EVIDENCE_POSTING_COUNT_INVALID")
    if not isinstance(asset.get("linkareerHostedCandidateRows"), int):
        errors.append("TIER1T2_ASSET_EVIDENCE_COUNT_INVALID")

    if storage.get("rawStorageMode") != "IMMUTABLE_CONTENT_ADDRESSED_EXTERNAL_STORAGE":
        errors.append("TIER1T2_STORAGE_IMMUTABILITY_REQUIRED")
    if storage.get("gitRawBytesAllowed") is not False or storage.get("automatedDeletionAllowed") is not False:
        errors.append("TIER1T2_STORAGE_GIT_OR_DELETE_DENY_REQUIRED")
    return sorted(set(errors)), payloads


def combined_approval_schema(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return the approval schema; this does not create an approval artifact."""

    tier1 = proposal["tier1"]
    tier3 = proposal["tier3"]
    scope = {
        "periodMonths": tier1["periodMonths"],
        "queryOperations": tier1["queryOperations"],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:p4:canary:tier1t2-detail-asset-approval:v1",
        "title": "P4 bounded index, detail-10 and Linkareer asset canary approval",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "approvalId", "approvedBy", "approvedAtUtc", "expiresAtUtc", "approvalStatus",
            "approvedSource", "approvedCanaryScope", "approvedScopeHash",
            "approvedMaxIndexRequests", "approvedMaxDetailRequests", "approvedMaxAssetRequests",
            "detailSamplingMethod", "detailSamplingSeedFormula", "replaceTerminalFailures",
            "linkareerHostedAssetAllowed", "externalAtsTransportAllowed", "browserAutomationAllowed",
            "ocrMode", "rawStorageMode", "queryRegistrySha256", "sourcePolicyAuditSha256",
            "sourcePolicyHumanApprovalRecordSha256", "rateLimitPolicyVersion",
            "rateLimitPolicySha256", "killSwitchPolicyVersion", "killSwitchPolicySha256",
            "storagePlanSha256", "approvedRateLimitRequestsPerMinute", "approvedRetryBudget",
        ],
        "properties": {
            "approvalId": {"type": "string", "minLength": 1},
            "approvedBy": {"type": "string", "minLength": 1},
            "approvedAtUtc": {"type": "string", "format": "date-time"},
            "expiresAtUtc": {"type": "string", "format": "date-time"},
            "approvalStatus": {"const": "APPROVED"},
            "approvedSource": {"const": "LINKAREER"},
            "approvedCanaryScope": {"const": scope},
            "approvedScopeHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "approvedMaxIndexRequests": {
                "type": "integer", "minimum": 1, "maximum": tier1["proposedMaxIndexRequests"],
            },
            "approvedMaxDetailRequests": {"const": 10},
            "approvedMaxAssetRequests": {
                "type": "integer", "minimum": 0, "maximum": tier3["proposedMaxAssetRequests"],
            },
            "detailSamplingMethod": {"const": "DETERMINISTIC_RANDOM_WITHOUT_REPLACEMENT"},
            "detailSamplingSeedFormula": {
                "const": "SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)",
            },
            "replaceTerminalFailures": {"const": False},
            "linkareerHostedAssetAllowed": {"const": True},
            "externalAtsTransportAllowed": {"const": False},
            "browserAutomationAllowed": {"const": False},
            "ocrMode": {"const": "QUEUE_MIME_SHA_TEXT_VOLUME_ONLY"},
            "rawStorageMode": {"const": "IMMUTABLE_CONTENT_ADDRESSED_EXTERNAL_STORAGE"},
            "queryRegistrySha256": {"const": proposal["queryRegistrySha256"]},
            "sourcePolicyAuditSha256": {"const": proposal["sourcePolicyAuditSha256"]},
            "sourcePolicyHumanApprovalRecordSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "rateLimitPolicyVersion": {"const": proposal["rateLimitPolicyVersion"]},
            "rateLimitPolicySha256": {"const": proposal["rateLimitPolicySha256"]},
            "killSwitchPolicyVersion": {"const": proposal["killSwitchPolicyVersion"]},
            "killSwitchPolicySha256": {"const": proposal["killSwitchPolicySha256"]},
            "storagePlanSha256": {"const": proposal["storagePlanSha256"]},
            "approvedRateLimitRequestsPerMinute": {"const": proposal["proposedRateLimitRequestsPerMinute"]},
            "approvedRetryBudget": {"const": proposal["proposedRetryBudget"]},
        },
    }


def validate_schema(schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
