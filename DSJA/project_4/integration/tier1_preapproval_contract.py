"""Fail-closed validation helpers for Tier 1 no-network preapproval evidence."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


REQUIRED_A1_PREAPPROVAL_ARTIFACTS = (
    "P4_TIER1_SCOPE_PROPOSAL.json",
    "P4_TIER1_REQUEST_ESTIMATE.json",
    "P4_TIER1_STORAGE_ESTIMATE.json",
    "P4_TIER1_QUERY_REGISTRY_AUDIT.csv",
    "P4_TIER1_KILL_SWITCH_AUDIT.csv",
    "P4_TIER1_CHECKPOINT_DRY_RUN.csv",
    "P4_TIER1_REQUESTKEY_DRY_RUN.csv",
    "P4_TIER1_APPROVAL_PACKET.md",
    "P4_TIER1_EMPTY_HANDOFF_SCHEMA.json",
    "P4_TIER1_PREAPPROVAL_TEST_SUMMARY.csv",
    "EVIDENCE_MANIFEST.sha256",
)
FORBIDDEN_APPROVAL_KEYS = {
    "approvedCanaryScope",
    "approvedMaxRequests",
    "approvedMaxDetailRequests",
    "approvedMaxAssetRequests",
    "approvedExpiry",
    "approvedRateLimit",
    "approvedRetryBudget",
    "approvedSourcePolicyHumanRecord",
    "approvedSource",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_evidence_manifest(root: Path) -> list[str]:
    manifest = root / "EVIDENCE_MANIFEST.sha256"
    if not manifest.is_file():
        return ["A1_EVIDENCE_MANIFEST_MISSING"]
    errors: list[str] = []
    declared: set[str] = set()
    for line_no, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            errors.append(f"A1_EVIDENCE_MANIFEST_LINE_INVALID:{line_no}")
            continue
        expected, name = parts[0], parts[1].strip()
        declared.add(name)
        target = root / name
        if not target.is_file():
            errors.append(f"A1_EVIDENCE_TARGET_MISSING:{name}")
        elif file_sha256(target) != expected:
            errors.append(f"A1_EVIDENCE_SHA_MISMATCH:{name}")
    expected_names = set(REQUIRED_A1_PREAPPROVAL_ARTIFACTS) - {"EVIDENCE_MANIFEST.sha256"}
    if declared != expected_names:
        errors.append("A1_EVIDENCE_DECLARATION_SET_MISMATCH")
    return errors


def forbidden_key_paths(value: Any, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            locator = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_APPROVAL_KEYS:
                hits.append(locator)
            hits.extend(forbidden_key_paths(child, locator))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(forbidden_key_paths(child, f"{prefix}[{index}]"))
    return hits


def validate_scope_proposal(proposal: dict[str, Any], tier0_manifest_sha: str) -> list[str]:
    errors: list[str] = []
    required = (
        "candidateScopeId", "candidatePeriodOrQuery", "estimatedIndexRequests",
        "proposedMaxIndexRequests", "estimatedStorageBytes", "expectedPaginationDepth",
        "queryRegistrySha256", "rateLimitPolicyVersion", "rateLimitPolicySha256",
        "killSwitchPolicyVersion", "killSwitchPolicySha256",
        "approvalExpiryRecommendation", "riskLevel", "riskReason",
    )
    for field in required:
        if field not in proposal:
            errors.append(f"TIER1_SCOPE_FIELD_MISSING:{field}")
    exact = {
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "logicalRequestType": "INDEX",
        "networkCalls": 0,
        "detailRequestCount": 0,
        "assetRequestCount": 0,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
        "tier0CanonicalHandoffManifestSha256": tier0_manifest_sha,
    }
    for field, expected in exact.items():
        if proposal.get(field) != expected:
            errors.append(f"TIER1_SCOPE_FIELD_MISMATCH:{field}")
    for field in ("estimatedIndexRequests", "proposedMaxIndexRequests", "estimatedStorageBytes", "expectedPaginationDepth"):
        value = proposal.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"TIER1_SCOPE_POSITIVE_INTEGER_REQUIRED:{field}")
    if (
        isinstance(proposal.get("estimatedIndexRequests"), int)
        and isinstance(proposal.get("proposedMaxIndexRequests"), int)
        and proposal["estimatedIndexRequests"] > proposal["proposedMaxIndexRequests"]
    ):
        errors.append("TIER1_SCOPE_ESTIMATE_EXCEEDS_PROPOSED_MAX")
    if proposal.get("riskLevel") not in {"LOW", "MEDIUM", "HIGH"}:
        errors.append("TIER1_SCOPE_RISK_LEVEL_INVALID")
    for locator in forbidden_key_paths(proposal):
        errors.append(f"TIER1_APPROVAL_VALUE_PREMATURE:{locator}")
    return errors


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_pass_csv(
    path: Path, *, allow_not_evaluated: bool = False, allow_findings: bool = False
) -> list[str]:
    rows = read_csv_rows(path)
    if not rows:
        return [f"TIER1_AUDIT_EMPTY:{path.name}"]
    allowed = {"PASS"}
    if allow_not_evaluated:
        allowed.add("NOT_EVALUATED")
    if allow_findings:
        allowed.add("PASS_WITH_FINDINGS")
    errors = []
    for index, row in enumerate(rows):
        if row.get("status") not in allowed:
            errors.append(f"TIER1_AUDIT_STATUS_INVALID:{path.name}:{index}:{row.get('status')}")
        if int(row.get("networkCalls", "0")) != 0:
            errors.append(f"TIER1_AUDIT_NETWORK_NONZERO:{path.name}:{index}")
        if int(row.get("externalAtsTransportCalls", "0")) != 0:
            errors.append(f"TIER1_AUDIT_EXTERNAL_ATS_NONZERO:{path.name}:{index}")
    return errors


def validate_empty_handoff_schema(path: Path) -> list[str]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # fail closed on malformed schema evidence
        return [f"TIER1_EMPTY_HANDOFF_SCHEMA_INVALID:{type(exc).__name__}"]
    required = set(schema.get("required", []))
    expected = {
        "runId", "dataVersion", "approvalId", "networkCalls",
        "detailRequestCount", "assetRequestCount", "status",
    }
    return [] if expected <= required else ["TIER1_EMPTY_HANDOFF_SCHEMA_REQUIRED_FIELDS_MISSING"]


def validate_a1_preapproval_bundle(root: Path, tier0_manifest_sha: str) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    actual = {path.name for path in root.iterdir() if path.is_file()} if root.is_dir() else set()
    if actual != set(REQUIRED_A1_PREAPPROVAL_ARTIFACTS):
        errors.append("A1_PREAPPROVAL_FILE_SET_MISMATCH")
    errors.extend(validate_evidence_manifest(root))
    proposal_path = root / "P4_TIER1_SCOPE_PROPOSAL.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8")) if proposal_path.is_file() else {}
    errors.extend(validate_scope_proposal(proposal, tier0_manifest_sha))
    for name in (
        "P4_TIER1_QUERY_REGISTRY_AUDIT.csv",
        "P4_TIER1_KILL_SWITCH_AUDIT.csv",
        "P4_TIER1_CHECKPOINT_DRY_RUN.csv",
        "P4_TIER1_REQUESTKEY_DRY_RUN.csv",
    ):
        if (root / name).is_file():
            errors.extend(validate_pass_csv(root / name))
    test_summary = root / "P4_TIER1_PREAPPROVAL_TEST_SUMMARY.csv"
    if test_summary.is_file():
        errors.extend(validate_pass_csv(test_summary, allow_findings=True))
    if (root / "P4_TIER1_EMPTY_HANDOFF_SCHEMA.json").is_file():
        errors.extend(validate_empty_handoff_schema(root / "P4_TIER1_EMPTY_HANDOFF_SCHEMA.json"))
    for name in ("P4_TIER1_REQUEST_ESTIMATE.json", "P4_TIER1_STORAGE_ESTIMATE.json"):
        path = root / name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            for locator in forbidden_key_paths(payload):
                errors.append(f"TIER1_APPROVAL_VALUE_PREMATURE:{name}:{locator}")
            if int(payload.get("networkCalls", -1)) != 0:
                errors.append(f"TIER1_DRY_RUN_NETWORK_NONZERO:{name}")
    return sorted(set(errors)), proposal
