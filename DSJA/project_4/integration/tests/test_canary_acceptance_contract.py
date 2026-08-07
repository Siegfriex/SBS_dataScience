from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import sys

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_ROOT))

from canary_acceptance_contract import (  # noqa: E402
    canonical_json_sha256, read_jsonl_artifact, request_key_for, validate_approval,
    validate_checkpoint_chain, validate_coverage, validate_kill_switch,
    validate_plan_and_stage, validate_raw_objects, validate_redacted_handoff, validate_request_ledger,
    validate_response_manifest,
)


def request_row(**updates):
    params = {"page": "1", "query": "REDACTED"}
    row = {
        "requestAttemptId": "ATT-1", "logicalRequestType": "INDEX",
        "normalizedRedactedParameters": params,
        "requestParamsRedactedSha256": canonical_json_sha256(params),
        "periodMonth": "2026-01", "postingId": None, "assetId": None,
        "attemptNo": 1, "idempotencyKey": "IDEMPOTENT-1",
        "requestFingerprintSha256": "1" * 64,
        "startedAtUtc": "2026-08-07T00:00:00Z", "completedAtUtc": "2026-08-07T00:00:01Z",
        "httpStatus": 200, "contentType": "text/html", "responseByteCount": 10,
        "responseSha256": "2" * 64, "retryDecision": "STOP", "retryReason": "TERMINAL",
        "killSwitchState": "ARMED", "checkpointId": "CP-1", "terminalStatus": "FETCHED_VALID",
    }
    row.update(updates); row["requestKey"] = request_key_for(row)
    return row


def raw_row(locator="objects/a.raw", sha=None, **updates):
    data = b"raw-canary"
    row = {
        "objectId": "OBJ-1", "logicalEntityType": "POSTING", "storageRootId": "CANARY_RAW",
        "objectLocatorRelative": locator, "requestFingerprintSha256": "1" * 64,
        "sourceUrlFingerprint": "3" * 64, "contentSha256": sha or hashlib.sha256(data).hexdigest(),
        "byteCount": len(data), "mime": "text/html", "retrievedAtUtc": "2026-08-07T00:00:01Z",
        "terminalStatus": "FETCHED_VALID", "dedupOfObjectId": None,
    }
    row.update(updates)
    return row


def test_valid_request_key_and_ledger_pass():
    errors, conflicts = validate_request_ledger([request_row()])
    assert errors == [] and conflicts == 0


def test_request_key_mismatch_fails():
    row = request_row(); row["requestKey"] = "0" * 64
    errors, _ = validate_request_ledger([row])
    assert "REQUEST_KEY_MISMATCH:0" in errors


def test_response_conflict_rejects():
    first = request_row(terminalStatus="RETRY_EXHAUSTED")
    second = request_row(requestAttemptId="ATT-2", attemptNo=2, responseSha256="4" * 64)
    errors, conflicts = validate_request_ledger([first, second])
    assert conflicts == 1
    assert "REQUEST_RESPONSE_CONFLICT:1" in errors


def test_terminal_request_reissue_rejects():
    first = request_row()
    second = request_row(requestAttemptId="ATT-2", attemptNo=2)
    errors, _ = validate_request_ledger([first, second])
    assert any(error.startswith("TERMINAL_REQUEST_REISSUED") for error in errors)


def test_relative_raw_mount_passes(tmp_path):
    target = tmp_path / "objects/a.raw"; target.parent.mkdir(); target.write_bytes(b"raw-canary")
    errors, stats = validate_raw_objects([raw_row()], tmp_path)
    assert errors == [] and stats["resolved"] == 1


def test_absolute_and_traversal_locator_reject():
    for locator in ("/tmp/raw", "../raw", "objects/../../raw"):
        errors, _ = validate_raw_objects([raw_row(locator=locator)], None)
        assert "RAW_LOCATOR_INVALID:0" in errors


def test_unmounted_raw_is_not_silently_resolved():
    errors, stats = validate_raw_objects([raw_row()], None)
    assert errors == [] and stats == {"rows": 1, "resolved": 0, "quarantined": 1}


def test_wrong_raw_sha_fails(tmp_path):
    target = tmp_path / "objects/a.raw"; target.parent.mkdir(); target.write_bytes(b"raw-canary")
    errors, stats = validate_raw_objects([raw_row(sha="0" * 64)], tmp_path)
    assert "RAW_SHA_MISMATCH:0" in errors and stats["resolved"] == 0


def test_checkpoint_chain_and_raw_binding_pass():
    raw_sha = "a" * 64
    first = {"checkpointId": "CP-1", "previousCheckpointSha256": None, "rawObjectManifestSha256": raw_sha}
    second = {"checkpointId": "CP-2", "previousCheckpointSha256": canonical_json_sha256(first), "rawObjectManifestSha256": raw_sha}
    assert validate_checkpoint_chain({"checkpoints": [first, second]}, raw_sha) == []


def test_checkpoint_chain_break_rejects():
    raw_sha = "a" * 64
    rows = [{"checkpointId": "CP-1", "previousCheckpointSha256": "0" * 64, "rawObjectManifestSha256": raw_sha}]
    assert "CHECKPOINT_CHAIN_BREAK:0" in validate_checkpoint_chain({"checkpoints": rows}, raw_sha)


def test_request_after_kill_switch_rejects():
    event = {"eventId": "KS-1", "timestampUtc": "2026-08-06T23:59:59Z", "lastSafeCheckpointId": "CP-0"}
    assert "REQUEST_AFTER_KILL_SWITCH:KS-1" in validate_kill_switch([request_row()], [event])


def test_network_without_approval_is_policy_block(tmp_path):
    (tmp_path / "approval_binding.json").write_text("{}\n", encoding="utf-8")
    errors = validate_approval(tmp_path, {"networkCalls": 1}, 1, datetime(2026, 8, 7, tzinfo=UTC))
    assert errors == ["NETWORK_WITHOUT_APPROVAL_ARTIFACT"]


def test_zero_network_does_not_require_network_approval(tmp_path):
    (tmp_path / "approval_binding.json").write_text(
        '{"approvalId":"NONE","status":"CANARY_APPROVAL_MISSING","networkCalls":0}\n',
        encoding="utf-8",
    )
    assert validate_approval(tmp_path, {"networkCalls": 0}, 0, datetime(2026, 8, 7, tzinfo=UTC)) == []


def test_response_manifest_orphan_fails():
    request = request_row()
    response = {"requestAttemptId": "UNKNOWN", "requestKey": request["requestKey"], "responseSha256": "2" * 64, "objectId": "OBJ-1"}
    errors = validate_response_manifest([request], [response], [raw_row()])
    assert "RESPONSE_ATTEMPT_ORPHAN:0" in errors


def test_coverage_requires_all_denominators_and_quarantine(tmp_path):
    coverage = tmp_path / "coverage.csv"
    coverage.write_text(
        "coverageLayer,plannedCount,terminalCount,coverage,unknownTerminalStatusCount,nullTerminalStatusCount,quarantineIncluded\n"
        "MONTH,1,1,1.0,0,0,true\nPAGE,2,2,1.0,0,0,true\n"
        "POSTING,3,3,1.0,0,0,true\nASSET,0,0,1.0,0,0,true\n",
        encoding="utf-8",
    )
    errors, rows = validate_coverage(coverage)
    assert errors == [] and set(rows) == {"MONTH", "PAGE", "POSTING", "ASSET"}


def test_canary_plan_prevents_promotion_and_contamination():
    plan = {
        "canaryRunId": "CANARY-FIXTURE-1", "canaryDataVersion": "canary-fixture-1",
        "canaryStorageRootId": "CANARY_RAW", "defectFamily": "PAGINATION",
        "analysisPromotionAllowed": False, "releasePromotionAllowed": False,
        "externalAtsTransportAllowed": False, "networkCalls": 0,
        "outputRootRelative": "crawl/runs/canary/CANARY-FIXTURE-1",
    }
    stage = {"runId": "CANARY-FIXTURE-1", "dataVersion": "canary-fixture-1", "status": "CANARY_FIXTURE_REGRESSION"}
    metrics = {"networkCalls": 0, "externalAtsTransportCalls": 0, "analysisPromotionAllowed": False, "releasePromotionAllowed": False}
    assert validate_plan_and_stage(plan, stage, metrics) == []
    plan["outputRootRelative"] = "pipeline/data/exports/observed-dev/CANARY-FIXTURE-1"
    assert "CANARY_OUTPUT_ROOT_INVALID" in validate_plan_and_stage(plan, stage, metrics)


def test_empty_jsonl_envelope_is_valid_data_zero(tmp_path):
    path = tmp_path / "request_attempt.jsonl"
    path.write_text(
        json.dumps({
            "recordType": "EMPTY_ARTIFACT", "artifactType": "REQUEST_ATTEMPT",
            "runId": "CANARY-0", "schemaVersion": "p4-canary-handoff-v1",
            "emptyReason": "NETWORK_NOT_AUTHORIZED", "rowCount": 0,
        }) + "\n",
        encoding="utf-8",
    )
    rows, errors, envelope = read_jsonl_artifact(path, "REQUEST_ATTEMPT", "CANARY-0")
    assert rows == [] and errors == [] and envelope["emptyReason"] == "NETWORK_NOT_AUTHORIZED"


def test_not_evaluated_coverage_requires_explicit_empty_reason(tmp_path):
    path = tmp_path / "coverage.csv"
    path.write_text(
        "coverageLayer,plannedCount,terminalCount,coverage,unknownTerminalStatusCount,nullTerminalStatusCount,quarantineIncluded,emptyReason\n"
        + "".join(f"{layer},0,0,NOT_EVALUATED,0,0,true,NETWORK_NOT_AUTHORIZED\n" for layer in ("MONTH", "PAGE", "POSTING", "ASSET")),
        encoding="utf-8",
    )
    errors, _ = validate_coverage(path)
    assert errors == []


def test_redacted_handoff_rejects_zero_byte(tmp_path):
    from canary_acceptance_contract import REQUIRED_ARTIFACTS
    for name in REQUIRED_ARTIFACTS:
        (tmp_path / name).write_text("safe\n", encoding="utf-8")
    (tmp_path / "raw_object_manifest.jsonl").write_bytes(b"")
    assert "HANDOFF_ZERO_BYTE:raw_object_manifest.jsonl" in validate_redacted_handoff(tmp_path)
