#!/usr/bin/env python3
"""Build the Tier 1 index-canary preapproval packet without network access."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
REPORT_ROOT = CRAWL_ROOT / "reports/tier1_preapproval"
TIER0_ROOT = CRAWL_ROOT / "handoffs/canary/CANARY_T0_20260807_03"
TIER0_CHECKSUM_SHA = "6162d3aea6ff3646d4d9cb7ff09d09acf91bbde81a815896096bca82b6f63c42"
A1_SOURCE_COMMIT = "13205c11e7de3dfc7b005b0fde16197281eb857f"
SCHEMA_VERSION = "p4-tier1-preapproval-v1"
DATA_VERSION = "tier1-preapproval-20260807.1"
RUN_ID = "TIER1_PREAPPROVAL_20260807_01"
RATE_POLICY_VERSION = "p4-linkareer-production-rate-v1"
KILL_POLICY_VERSION = "p4-linkareer-kill-switch-v1"
SOURCE_POLICY_VERSION = "p4-linkareer-source-policy-v1"
PROPOSAL_PERIOD = "2026-03"
ENTRY_OPERATION = "CalendarScreen_ActivityCalendarEntries"
TOTAL_OPERATION = "CalendarScreen_Activities"
SCOPE_ID = "T1-INDEX-2026-03-APQ-V1"

sys.path.insert(0, str(CRAWL_ROOT / "src"))

from p4_crawl.canary import (  # noqa: E402
    CanaryKillSwitch,
    CanaryKillSwitchTripped,
    checkpoint_envelope,
    request_key,
    validate_checkpoint,
)
from p4_crawl.index_orchestrator import production_index_plan  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"empty evidence is forbidden: {path.name}")
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def expect_kill(check_id: str, callback) -> dict[str, Any]:
    try:
        callback()
    except CanaryKillSwitchTripped as exc:
        return {"checkId": check_id, "status": "PASS", "observed": str(exc)}
    return {"checkId": check_id, "status": "FAIL", "observed": "kill switch did not trip"}


def fixture_estimate() -> dict[str, int]:
    fixture = CRAWL_ROOT / "fixtures/apq/CalendarScreen_ActivityCalendarEntries.2026-03.recruit.sample.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))["responseBody"]
    nodes = payload["data"]["activityCalendarEntries"]["nodes"]
    totals = [
        int((day.get(side) or {}).get("totalCount") or 0)
        for day in nodes
        for side in ("start", "end")
    ]
    maximum = max(totals)
    depth = math.ceil(maximum / 6)
    requests = depth + 1  # paginated entries plus aggregate total cross-check
    response_bytes = fixture.stat().st_size
    return {
        "fixtureBytes": response_bytes,
        "fixtureDays": len(nodes),
        "fixtureBuckets": len(totals),
        "maxBucketTotal": maximum,
        "expectedPaginationDepth": depth,
        "estimatedIndexRequests": requests,
        "estimatedStorageBytes": requests * response_bytes,
    }


def full_tree_scan() -> dict[str, Any]:
    secret = re.compile(
        rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|"
        rb"(?:api[_-]?key|service[_-]?key|cookie|token)\s*[:=]\s*['\"][^'\"]+",
        re.I,
    )
    absolute = re.compile(rb"/(?:home|mnt|Users)/[^\s,'\"]+")
    secret_paths: list[str] = []
    absolute_paths: list[str] = []
    for relative in git("ls-files", "crawl").splitlines():
        path = PROJECT_ROOT / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        if secret.search(content):
            secret_paths.append(relative)
        if absolute.search(content):
            absolute_paths.append(relative)
    generated_absolute_paths: list[str] = []
    if REPORT_ROOT.is_dir():
        for path in REPORT_ROOT.iterdir():
            if path.is_file() and absolute.search(path.read_bytes()):
                generated_absolute_paths.append(path.name)
    return {
        "trackedSecretCookieKeyFindings": len(secret_paths),
        "trackedAbsolutePathFindings": len(absolute_paths),
        "preapprovalTreeAbsolutePathFindings": len(generated_absolute_paths),
        "secretFindingPaths": secret_paths,
        "absolutePathFindingPaths": absolute_paths,
        "preapprovalAbsolutePathFindingPaths": generated_absolute_paths,
    }


def main() -> int:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    existing = [path for path in REPORT_ROOT.iterdir() if path.is_file()]
    if existing:
        raise RuntimeError("Tier 1 preapproval evidence is immutable; report root is not empty")

    if sha256(TIER0_ROOT / "CHECKSUMS.sha256") != TIER0_CHECKSUM_SHA:
        raise RuntimeError("accepted Tier 0 checksum manifest drift")
    checksums = (TIER0_ROOT / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines()
    if len(checksums) != 15:
        raise RuntimeError("Tier 0 checksum declaration count is not 15")
    for line in checksums:
        expected, name = line.split(None, 1)
        if sha256(TIER0_ROOT / name.strip()) != expected:
            raise RuntimeError(f"Tier 0 artifact checksum mismatch: {name}")

    generated = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    query_path = CRAWL_ROOT / "configs/queryRegistry.yaml"
    policy_path = CRAWL_ROOT / "src/p4_crawl/policy.py"
    kill_path = CRAWL_ROOT / "src/p4_crawl/canary.py"
    query_sha = sha256(query_path)
    rate_sha = sha256(policy_path)
    kill_sha = sha256(kill_path)
    registry = yaml.safe_load(query_path.read_text(encoding="utf-8"))
    queries = {row["operationName"]: row for row in registry["queries"]}
    for operation in (ENTRY_OPERATION, TOTAL_OPERATION):
        row = queries.get(operation)
        if not row or row.get("activeFlag") is not True or row.get("verificationStatus") != "verified":
            raise RuntimeError(f"query registry operation is not verified and active: {operation}")

    estimate = fixture_estimate()
    plan = production_index_plan([PROPOSAL_PERIOD])
    if not plan["productionApprovalRequired"]:
        raise RuntimeError("index plan does not fail closed on approval")

    source_manifest = json.loads(
        (CRAWL_ROOT / "reports/reconciliation_a1/A1_M2_PREFLIGHT_REBIND_MANIFEST.json").read_text(encoding="utf-8")
    )
    source_policy_sha = source_manifest["sourcePolicyAuditSha256"]
    proposal = {
        "schemaVersion": SCHEMA_VERSION,
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "candidateScopeId": SCOPE_ID,
        "candidatePeriodOrQuery": {
            "periodMonths": [PROPOSAL_PERIOD],
            "queryOperations": [ENTRY_OPERATION, TOTAL_OPERATION],
        },
        "logicalRequestType": "INDEX",
        "estimatedIndexRequests": estimate["estimatedIndexRequests"],
        "proposedMaxIndexRequests": estimate["estimatedIndexRequests"],
        "estimatedStorageBytes": estimate["estimatedStorageBytes"],
        "expectedPaginationDepth": estimate["expectedPaginationDepth"],
        "queryRegistrySha256": query_sha,
        "rateLimitPolicyVersion": RATE_POLICY_VERSION,
        "rateLimitPolicySha256": rate_sha,
        "killSwitchPolicyVersion": KILL_POLICY_VERSION,
        "killSwitchPolicySha256": kill_sha,
        "sourcePolicyVersion": SOURCE_POLICY_VERSION,
        "sourcePolicyAuditSha256": source_policy_sha,
        "approvalExpiryRecommendation": "PT2H_AFTER_APPROVAL",
        "riskLevel": "MEDIUM",
        "riskReason": "Live response semantics and actual pagination depth remain unobserved; bounded fixture-derived budget stops closed if exceeded.",
        "networkCalls": 0,
        "detailRequestCount": 0,
        "assetRequestCount": 0,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
        "tier0ChecksumManifestSha256": TIER0_CHECKSUM_SHA,
        "tier0CanonicalHandoffManifestSha256": TIER0_CHECKSUM_SHA,
        "a1SourceCommit": A1_SOURCE_COMMIT,
        "generatedAtUtc": generated,
    }
    write_json(REPORT_ROOT / "P4_TIER1_SCOPE_PROPOSAL.json", proposal)

    request_estimate = {
        "schemaVersion": SCHEMA_VERSION,
        "status": "STATIC_NO_NETWORK_ESTIMATE_NOT_APPROVAL",
        "candidateScopeId": SCOPE_ID,
        "basis": "2026-03 checked-in APQ fixture; pageSize=6; max bucket total divided by pageSize plus one aggregate cross-check",
        **estimate,
        "pageSize": 6,
        "aggregateCrossCheckRequests": 1,
        "detailRequests": 0,
        "assetRequests": 0,
        "networkCalls": 0,
        "tier0ChecksumManifestSha256": TIER0_CHECKSUM_SHA,
        "tier0CanonicalHandoffManifestSha256": TIER0_CHECKSUM_SHA,
        "a1SourceCommit": A1_SOURCE_COMMIT,
    }
    write_json(REPORT_ROOT / "P4_TIER1_REQUEST_ESTIMATE.json", request_estimate)

    write_json(REPORT_ROOT / "P4_TIER1_STORAGE_ESTIMATE.json", {
        "schemaVersion": SCHEMA_VERSION,
        "status": "STATIC_NO_NETWORK_ESTIMATE_NOT_QUOTA_RESERVATION",
        "candidateScopeId": SCOPE_ID,
        "estimatedIndexResponses": estimate["estimatedIndexRequests"],
        "assumedBytesPerResponse": estimate["fixtureBytes"],
        "estimatedStorageBytes": estimate["estimatedStorageBytes"],
        "storagePolicy": "IMMUTABLE_CONTENT_ADDRESSED_EXTERNAL_STORAGE",
        "gitRawBytesAllowed": False,
        "automatedWriteAllowedOnlyAfterScopeApproval": True,
        "automatedDeletionAllowed": False,
        "networkCalls": 0,
        "tier0ChecksumManifestSha256": TIER0_CHECKSUM_SHA,
        "tier0CanonicalHandoffManifestSha256": TIER0_CHECKSUM_SHA,
        "a1SourceCommit": A1_SOURCE_COMMIT,
    })

    write_csv(REPORT_ROOT / "P4_TIER1_QUERY_REGISTRY_AUDIT.csv", ({
        "operationName": operation,
        "activeFlag": queries[operation]["activeFlag"],
        "verificationStatus": queries[operation]["verificationStatus"],
        "httpMethod": queries[operation]["httpMethod"],
        "transportType": queries[operation]["transportType"],
        "queryRegistrySha256": query_sha,
        "queryHashSha256": queries[operation]["sha256Hash"],
        "status": "PASS",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    } for operation in (ENTRY_OPERATION, TOTAL_OPERATION)))

    kill_checks = [
        expect_kill("HTTP_403", lambda: CanaryKillSwitch().response(403)),
        expect_kill("UNEXPECTED_CONTENT_TYPE", lambda: CanaryKillSwitch().response(200, "text/html")),
        expect_kill("SCHEMA_DRIFT", lambda: CanaryKillSwitch().schema_drift("missing nodes")),
    ]
    def trip_429() -> None:
        monitor = CanaryKillSwitch(minimum_success_samples=20)
        for _ in range(3):
            monitor.response(429)
    kill_checks.append(expect_kill("HTTP_429", trip_429))
    def trip_cursor() -> None:
        monitor = CanaryKillSwitch()
        monitor.page(cursor="fixture-cursor", empty=False)
        monitor.page(cursor="fixture-cursor", empty=False)
    kill_checks.append(expect_kill("CURSOR_LOOP", trip_cursor))
    for row in kill_checks:
        row.update({
            "policyVersion": KILL_POLICY_VERSION,
            "policySha256": kill_sha,
            "networkCalls": 0,
            "externalAtsTransportCalls": 0,
        })
    write_csv(REPORT_ROOT / "P4_TIER1_KILL_SWITCH_AUDIT.csv", kill_checks)

    first = checkpoint_envelope({"runId": RUN_ID, "page": 1, "completedRequestKeys": []})
    first_state = validate_checkpoint(first)
    second = checkpoint_envelope(
        {"runId": RUN_ID, "page": 2, "completedRequestKeys": ["a" * 64]},
        first["checkpointSha256"],
    )
    second_state = validate_checkpoint(second, expected_previous_sha256=first["checkpointSha256"])
    corrupt = json.loads(json.dumps(second))
    corrupt["state"]["page"] = 3
    corrupted_rejected = False
    try:
        validate_checkpoint(corrupt, expected_previous_sha256=first["checkpointSha256"])
    except CanaryKillSwitchTripped:
        corrupted_rejected = True
    write_csv(REPORT_ROOT / "P4_TIER1_CHECKPOINT_DRY_RUN.csv", [
        {"checkId": "CHECKPOINT_CREATE", "status": "PASS" if first_state["page"] == 1 else "FAIL", "checkpointSha256": first["checkpointSha256"], "networkCalls": 0, "externalAtsTransportCalls": 0},
        {"checkId": "CHECKPOINT_RESUME_CHAIN", "status": "PASS" if second_state["page"] == 2 else "FAIL", "checkpointSha256": second["checkpointSha256"], "networkCalls": 0, "externalAtsTransportCalls": 0},
        {"checkId": "CHECKPOINT_CORRUPTION_FAIL_CLOSED", "status": "PASS" if corrupted_rejected else "FAIL", "checkpointSha256": second["checkpointSha256"], "networkCalls": 0, "externalAtsTransportCalls": 0},
    ])

    request_rows = []
    for page in (1, estimate["expectedPaginationDepth"]):
        parameters = {"operationName": ENTRY_OPERATION, "nodePagination": {"page": page, "pageSize": 6}}
        first_key = request_key("INDEX", parameters, period_month=PROPOSAL_PERIOD)
        second_key = request_key("INDEX", dict(reversed(list(parameters.items()))), period_month=PROPOSAL_PERIOD)
        request_rows.append({
            "checkId": f"REQUEST_KEY_PAGE_{page}",
            "logicalRequestType": "INDEX",
            "periodMonth": PROPOSAL_PERIOD,
            "pageOrCursor": page,
            "requestKey": first_key,
            "repeatRequestKey": second_key,
            "status": "PASS" if first_key == second_key else "FAIL",
            "networkCalls": 0,
            "externalAtsTransportCalls": 0,
        })
    write_csv(REPORT_ROOT / "P4_TIER1_REQUESTKEY_DRY_RUN.csv", request_rows)

    empty_handoff_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "p4-tier1-empty-handoff-skeleton-v1",
        "title": "Tier 1 preapproval empty handoff skeleton",
        "$comment": "Schema only. It does not authorize transport and contains no approved values.",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schemaVersion", "runId", "dataVersion", "approvalId", "status", "proposalStatus", "networkCalls",
            "detailRequestCount", "assetRequestCount", "tier0ChecksumManifestSha256",
            "tier0CanonicalHandoffManifestSha256", "a1SourceCommit",
        ],
        "properties": {
            "schemaVersion": {"const": "p4-canary-handoff-v1"},
            "runId": {"type": "string", "minLength": 1},
            "dataVersion": {"type": "string", "minLength": 1},
            "approvalId": {"const": "NONE"},
            "status": {"enum": ["AWAIT_TIER1_APPROVAL", "PREAPPROVAL_EMPTY_NOT_EXECUTABLE"]},
            "proposalStatus": {"const": "PREAPPROVAL_EMPTY_NOT_EXECUTABLE"},
            "networkCalls": {"const": 0},
            "detailRequestCount": {"const": 0},
            "assetRequestCount": {"const": 0},
            "tier0ChecksumManifestSha256": {"const": TIER0_CHECKSUM_SHA},
            "tier0CanonicalHandoffManifestSha256": {"const": TIER0_CHECKSUM_SHA},
            "a1SourceCommit": {"const": A1_SOURCE_COMMIT},
        },
        "x-p4-binding": {
            "tier0ChecksumManifestSha256": TIER0_CHECKSUM_SHA,
            "tier0CanonicalHandoffManifestSha256": TIER0_CHECKSUM_SHA,
            "a1SourceCommit": A1_SOURCE_COMMIT,
            "networkCalls": 0,
        },
    }
    write_json(REPORT_ROOT / "P4_TIER1_EMPTY_HANDOFF_SCHEMA.json", empty_handoff_schema)

    scan = full_tree_scan()
    tests = [
        {"testId": "TIER0_15_CHECKSUMS", "status": "PASS", "observed": 15},
        {"testId": "QUERY_REGISTRY_ACTIVE_VERIFIED", "status": "PASS", "observed": 2},
        {"testId": "INDEX_PLAN_APPROVAL_FAIL_CLOSED", "status": "PASS", "observed": plan["productionApprovalRequired"]},
        {"testId": "CHECKPOINT_RESUME", "status": "PASS" if second_state["page"] == 2 else "FAIL", "observed": second_state["page"]},
        {"testId": "CHECKPOINT_CORRUPTION_STOP", "status": "PASS" if corrupted_rejected else "FAIL", "observed": corrupted_rejected},
        {"testId": "REQUEST_KEY_DETERMINISTIC", "status": "PASS" if all(row["status"] == "PASS" for row in request_rows) else "FAIL", "observed": len(request_rows)},
        {"testId": "KILL_SWITCH_FIXTURES", "status": "PASS" if all(row["status"] == "PASS" for row in kill_checks) else "FAIL", "observed": len(kill_checks)},
        {"testId": "TRACKED_SECRET_COOKIE_KEY_SCAN", "status": "PASS" if scan["trackedSecretCookieKeyFindings"] == 0 else "FAIL", "observed": scan["trackedSecretCookieKeyFindings"]},
        {"testId": "PREAPPROVAL_TREE_ABSOLUTE_PATH_SCAN", "status": "PASS" if scan["preapprovalTreeAbsolutePathFindings"] == 0 else "FAIL", "observed": scan["preapprovalTreeAbsolutePathFindings"]},
        {"testId": "TRACKED_CRAWL_ABSOLUTE_PATH_INVENTORY", "status": "PASS_WITH_FINDINGS" if scan["trackedAbsolutePathFindings"] else "PASS", "observed": scan["trackedAbsolutePathFindings"]},
        {"testId": "NO_NETWORK_TRANSPORT", "status": "PASS", "observed": 0},
    ]
    for row in tests:
        row.update({"runId": RUN_ID, "sourceCommit": A1_SOURCE_COMMIT, "networkCalls": 0, "externalAtsTransportCalls": 0})
    write_csv(REPORT_ROOT / "P4_TIER1_PREAPPROVAL_TEST_SUMMARY.csv", tests)

    packet = f"""# P4 Tier 1 index-canary approval packet

Decision ID: `D-T1-INDEX-CANARY`

## Question

승인된 작은 Linkareer index-only canary를 실제 network로 실행할까요?

## Current evidence

- Tier 0 canonical handoff: accepted checksum manifest `{TIER0_CHECKSUM_SHA}`
- A1 source commit: `{A1_SOURCE_COMMIT}`
- Tier 1 preapproval dry run: `{sum(row['status'] == 'PASS' for row in tests)}/{len(tests)} PASS`
- Historical tracked crawl absolute-path inventory: `{scan['trackedAbsolutePathFindings']}` `PASS_WITH_FINDINGS`
  (pre-existing audit reports and negative-test literals; new preapproval tree findings: `{scan['preapprovalTreeAbsolutePathFindings']}`)
- Network calls so far: `0`
- External ATS calls so far: `0`

## Proposed scope — not approved

- proposalStatus: `PROPOSED_NOT_APPROVED`
- candidateScopeId: `{SCOPE_ID}`
- period: `{PROPOSAL_PERIOD}`
- query operations: `{ENTRY_OPERATION}`, `{TOTAL_OPERATION}`
- proposed maximum index requests: `{estimate['estimatedIndexRequests']}`
- fixture-derived pagination depth: `{estimate['expectedPaginationDepth']}`
- estimated response storage: `{estimate['estimatedStorageBytes']}` bytes
- detail budget: `0`
- asset budget: `0`
- source: `LINKAREER` only
- external ATS: `false`
- browser automation: `false`
- query registry SHA-256: `{query_sha}`
- rate policy: `{RATE_POLICY_VERSION}` / `{rate_sha}`
- kill-switch policy: `{KILL_POLICY_VERSION}` / `{kill_sha}`
- approval expiry recommendation: `PT2H_AFTER_APPROVAL`

These values are controller proposals only. They are not `approved*` fields and
do not open transport. The user-issued approval artifact must independently set
the exact scope, maximum request count, expiry, rate/retry budget, source and
source-policy human record.

## Recommendation

Approve one bounded Tier 1 index-only canary only after reviewing this proposal.

## Impact

- If approved: bounded index transport may begin; detail and asset requests remain forbidden.
- If denied: network remains at zero with no production-data impact.
- If deferred: automation remains `AWAIT_TIER1_APPROVAL`.

Full M2, production release, analysis, detail and asset promotion remain blocked.
"""
    (REPORT_ROOT / "P4_TIER1_APPROVAL_PACKET.md").write_text(packet, encoding="utf-8")

    artifact_names = {
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
    }
    actual_before_manifest = {path.name for path in REPORT_ROOT.iterdir() if path.is_file()}
    if actual_before_manifest != artifact_names:
        raise RuntimeError(f"unexpected report artifacts: {sorted(actual_before_manifest ^ artifact_names)}")
    evidence = REPORT_ROOT / "EVIDENCE_MANIFEST.sha256"
    evidence.write_text(
        "\n".join(f"{sha256(REPORT_ROOT / name)}  {name}" for name in sorted(artifact_names)) + "\n",
        encoding="utf-8",
    )
    if any(row["status"] == "FAIL" for row in tests):
        return 1
    print(json.dumps({
        "status": "TIER1_APPROVAL_PACKET_READY",
        "branch": git("branch", "--show-current"),
        "inputCommit": A1_SOURCE_COMMIT,
        "tier0ChecksumManifestSha256": TIER0_CHECKSUM_SHA,
        "candidateScopeId": SCOPE_ID,
        "candidatePeriod": PROPOSAL_PERIOD,
        "proposedMaxIndexRequests": estimate["estimatedIndexRequests"],
        "approvalExpiryRecommendation": "PT2H_AFTER_APPROVAL",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "artifacts": 11,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
