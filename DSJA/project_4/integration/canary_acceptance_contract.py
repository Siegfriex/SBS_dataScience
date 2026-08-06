"""Fail-closed contract checks for P4 crawl canary handoffs.

This module never performs transport.  It validates portable, redacted evidence
and optional externally-mounted raw objects supplied by an A1 canary run.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import re
import csv
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_REQUEST_STATUSES = {
    "FETCHED_VALID", "FETCHED_EMPTY_VALID", "NOT_FOUND", "EXPIRED",
    "POLICY_BLOCKED", "RETRY_EXHAUSTED", "PARSER_QUARANTINED",
}
ASSET_TERMINAL_STATUSES = {
    "FETCHED_VALID", "DUPLICATE_CONTENT", "UNSUPPORTED_MIME", "NOT_FOUND",
    "POLICY_BLOCKED", "RETRY_EXHAUSTED",
}
CANARY_RUN_STATUSES = {
    "CANARY_PLANNED", "CANARY_APPROVAL_VALIDATED", "CANARY_FIXTURE_REGRESSION",
    "CANARY_INDEX_RUNNING", "CANARY_DETAIL_RUNNING", "CANARY_ASSET_RUNNING",
    "CANARY_VALIDATION", "CANARY_READY_FOR_NEXT_SCOPE", "CANARY_BLOCKED_BY_POLICY",
    "CANARY_STOPPED_BY_KILL_SWITCH", "CANARY_STOPPED_BY_SCOPE_LIMIT",
    "CANARY_QUARANTINED", "CANARY_FAILED",
}
REQUIRED_ARTIFACTS = (
    "canary_plan.json", "approval_binding.json", "request_attempt.jsonl",
    "request_response_manifest.jsonl", "checkpoint_manifest.json",
    "raw_object_manifest.jsonl", "index_results.parquet", "detail_results.parquet",
    "asset_results.parquet", "canary_coverage.csv", "kill_switch_events.jsonl",
    "quarantine_manifest.jsonl", "stage_manifest.json", "stage_metrics.json",
    "stage_quality.csv", "CHECKSUMS.sha256",
)
REQUIRED_REQUEST_FIELDS = (
    "requestAttemptId", "requestKey", "logicalRequestType", "attemptNo",
    "idempotencyKey", "requestFingerprintSha256", "requestParamsRedactedSha256",
    "startedAtUtc", "completedAtUtc", "httpStatus", "contentType",
    "responseByteCount", "retryDecision", "retryReason", "killSwitchState",
    "checkpointId", "terminalStatus",
)
REQUIRED_RAW_FIELDS = (
    "objectId", "logicalEntityType", "storageRootId", "objectLocatorRelative",
    "requestFingerprintSha256", "sourceUrlFingerprint", "contentSha256",
    "byteCount", "mime", "retrievedAtUtc", "terminalStatus",
)
EMPTY_RECORD_TYPE = "EMPTY_ARTIFACT"
EMPTY_SCHEMA_VERSION = "p4-canary-handoff-v1"
ABSOLUTE_PATH_RE = re.compile(r"(?:/home/|/mnt/|[A-Za-z]:\\\\)")
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|session[_-]?cookie|authorization)\s*[:=]\s*[^,;\s]{8,}"
)


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_jsonl_artifact(
    path: Path, expected_type: str, run_id: str
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any] | None]:
    rows = read_jsonl(path)
    empty_rows = [row for row in rows if row.get("recordType") == EMPTY_RECORD_TYPE]
    if not empty_rows:
        return rows, [], None
    errors: list[str] = []
    if len(rows) != 1:
        errors.append(f"EMPTY_ARTIFACT_MIXED_WITH_DATA:{path.name}")
    envelope = empty_rows[0]
    expected = {
        "artifactType": expected_type,
        "runId": run_id,
        "schemaVersion": EMPTY_SCHEMA_VERSION,
        "rowCount": 0,
    }
    for field, value in expected.items():
        if envelope.get(field) != value:
            errors.append(f"EMPTY_ARTIFACT_FIELD_MISMATCH:{path.name}:{field}")
    if not envelope.get("emptyReason"):
        errors.append(f"EMPTY_ARTIFACT_REASON_MISSING:{path.name}")
    return [], errors, envelope


def validate_redacted_handoff(root: Path) -> list[str]:
    errors: list[str] = []
    actual = {path.name for path in root.iterdir() if path.is_file()}
    if actual != set(REQUIRED_ARTIFACTS):
        errors.append("HANDOFF_FILE_SET_MISMATCH")
    for path in root.iterdir():
        if not path.is_file():
            continue
        if path.stat().st_size == 0:
            errors.append(f"HANDOFF_ZERO_BYTE:{path.name}")
        if path.suffix in {".json", ".jsonl", ".csv", ".sha256"}:
            text = path.read_text(encoding="utf-8-sig", errors="strict")
            if ABSOLUTE_PATH_RE.search(text):
                errors.append(f"HANDOFF_ABSOLUTE_PATH:{path.name}")
            if SECRET_RE.search(text):
                errors.append(f"HANDOFF_SECRET_OR_COOKIE:{path.name}")
    return errors


def parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def relative_locator_valid(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def request_key_for(row: Mapping[str, Any]) -> str:
    redacted = row.get("normalizedRedactedParameters")
    if redacted is None:
        raise ValueError("normalizedRedactedParameters is required to recompute requestKey")
    params_sha = canonical_json_sha256(redacted)
    if params_sha != row.get("requestParamsRedactedSha256"):
        raise ValueError("requestParamsRedactedSha256 mismatch")
    material = "".join(
        str(value or "") for value in (
            row.get("logicalRequestType"),
            json.dumps(redacted, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            row.get("periodMonth"), row.get("postingId"), row.get("assetId"),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_checksum_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    checksum_path = root / "CHECKSUMS.sha256"
    if not checksum_path.is_file():
        return ["CHECKSUM_MANIFEST_MISSING"]
    declared: set[str] = set()
    for line_no, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0]):
            errors.append(f"CHECKSUM_LINE_INVALID:{line_no}")
            continue
        expected, relative = parts[0], parts[1].strip()
        if not relative_locator_valid(relative):
            errors.append(f"CHECKSUM_LOCATOR_INVALID:{relative}")
            continue
        declared.add(relative)
        target = root / relative
        if not target.is_file():
            errors.append(f"CHECKSUM_TARGET_MISSING:{relative}")
        elif file_sha256(target) != expected:
            errors.append(f"CHECKSUM_MISMATCH:{relative}")
    expected_names = set(REQUIRED_ARTIFACTS) - {"CHECKSUMS.sha256"}
    for missing in sorted(expected_names - declared):
        errors.append(f"CHECKSUM_DECLARATION_MISSING:{missing}")
    for extra in sorted(declared - expected_names):
        errors.append(f"CHECKSUM_DECLARATION_EXTRA:{extra}")
    return errors


def validate_plan_and_stage(
    plan: Mapping[str, Any], stage: Mapping[str, Any], metrics: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    required_plan = ("canaryRunId", "canaryDataVersion", "canaryStorageRootId", "defectFamily")
    for field in required_plan:
        if not plan.get(field):
            errors.append(f"CANARY_PLAN_FIELD_MISSING:{field}")
    for field in ("analysisPromotionAllowed", "releasePromotionAllowed", "externalAtsTransportAllowed"):
        if plan.get(field) is not False:
            errors.append(f"CANARY_PLAN_FORBIDDEN_FLAG:{field}")
    output_root = str(plan.get("outputRootRelative", ""))
    if output_root and (
        not relative_locator_valid(output_root)
        or "observed-dev" in output_root.casefold()
        or "production" in PurePosixPath(output_root).parts
    ):
        errors.append("CANARY_OUTPUT_ROOT_INVALID")
    if stage.get("runId") != plan.get("canaryRunId"):
        errors.append("CANARY_STAGE_RUN_ID_MISMATCH")
    if stage.get("dataVersion") != plan.get("canaryDataVersion"):
        errors.append("CANARY_STAGE_DATA_VERSION_MISMATCH")
    if stage.get("status") not in CANARY_RUN_STATUSES:
        errors.append("CANARY_STAGE_STATUS_INVALID")
    actual_requests = int(metrics.get("networkCalls", -1))
    if actual_requests != int(plan.get("networkCalls", -2)):
        errors.append("CANARY_STAGE_NETWORK_COUNT_MISMATCH")
    if int(metrics.get("externalAtsTransportCalls", -1)) != 0:
        errors.append("EXTERNAL_ATS_TRANSPORT_NONZERO")
    for field in ("analysisPromotionAllowed", "releasePromotionAllowed"):
        if metrics.get(field) is not False:
            errors.append(f"CANARY_METRIC_FORBIDDEN_FLAG:{field}")
    return errors


def validate_approval(root: Path, plan: Mapping[str, Any], network_calls: int, now: datetime) -> list[str]:
    errors: list[str] = []
    binding_path = root / "approval_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.is_file() else {}
    if network_calls == 0:
        return errors
    approval_path = root / "production_crawl_approval.json"
    if not approval_path.is_file():
        return ["NETWORK_WITHOUT_APPROVAL_ARTIFACT"]
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    required = (
        "approvalId", "approvedBy", "approvedAtUtc", "expiresAtUtc", "approvalStatus",
        "approvedSource", "approvedCanaryScope", "approvedMaxRequests",
        "approvedMaxDetailRequests", "approvedMaxAssetRequests", "linkareerHostedAssetAllowed",
        "externalAtsTransportAllowed", "browserAutomationAllowed", "rateLimitPolicyVersion",
        "killSwitchPolicyVersion", "queryRegistrySha256", "sourcePolicyAuditSha256",
        "storagePlanSha256",
    )
    for field in required:
        if field not in approval:
            errors.append(f"APPROVAL_FIELD_MISSING:{field}")
    if binding.get("approvalArtifactSha256") != file_sha256(approval_path):
        errors.append("APPROVAL_SHA_BINDING_MISMATCH")
    if binding.get("approvalId") != approval.get("approvalId"):
        errors.append("APPROVAL_ID_BINDING_MISMATCH")
    if approval.get("approvalStatus") != "APPROVED":
        errors.append("APPROVAL_STATUS_NOT_APPROVED")
    try:
        if parse_utc(approval.get("expiresAtUtc")) <= now.astimezone(UTC):
            errors.append("APPROVAL_EXPIRED")
    except ValueError:
        errors.append("APPROVAL_EXPIRY_INVALID")
    exact = {
        "approvedSource": "LINKAREER",
        "linkareerHostedAssetAllowed": True,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
    }
    for field, expected in exact.items():
        if approval.get(field) != expected:
            errors.append(f"APPROVAL_POLICY_MISMATCH:{field}")
    budgets = {
        "networkCalls": "approvedMaxRequests",
        "detailRequestCount": "approvedMaxDetailRequests",
        "assetRequestCount": "approvedMaxAssetRequests",
    }
    for actual_field, approved_field in budgets.items():
        if int(plan.get(actual_field, 0)) > int(approval.get(approved_field, -1)):
            errors.append(f"APPROVAL_BUDGET_EXCEEDED:{actual_field}")
    for field in ("queryRegistrySha256", "rateLimitPolicyVersion", "killSwitchPolicyVersion"):
        if plan.get(field) != approval.get(field):
            errors.append(f"APPROVAL_BINDING_MISMATCH:{field}")
    if plan.get("canaryScope") != approval.get("approvedCanaryScope"):
        errors.append("APPROVAL_SCOPE_MISMATCH")
    for field in ("queryRegistrySha256", "sourcePolicyAuditSha256", "storagePlanSha256"):
        if not SHA256_RE.fullmatch(str(approval.get(field, ""))):
            errors.append(f"APPROVAL_SHA_INVALID:{field}")
    return errors


def validate_request_ledger(rows: Iterable[Mapping[str, Any]]) -> tuple[list[str], int]:
    errors: list[str] = []
    responses: dict[str, set[str]] = {}
    terminal_seen: set[str] = set()
    for index, row in enumerate(rows):
        missing = [field for field in REQUIRED_REQUEST_FIELDS if row.get(field) is None]
        if missing:
            errors.append(f"REQUEST_FIELDS_MISSING:{index}:{','.join(missing)}")
            continue
        if not all(SHA256_RE.fullmatch(str(row.get(field, ""))) for field in (
            "requestKey", "requestFingerprintSha256", "requestParamsRedactedSha256"
        )):
            errors.append(f"REQUEST_SHA_INVALID:{index}")
        try:
            if request_key_for(row) != row.get("requestKey"):
                errors.append(f"REQUEST_KEY_MISMATCH:{index}")
            if parse_utc(row["completedAtUtc"]) < parse_utc(row["startedAtUtc"]):
                errors.append(f"REQUEST_TIMESTAMP_REVERSED:{index}")
        except ValueError as exc:
            errors.append(f"REQUEST_CONTRACT_INVALID:{index}:{exc}")
        key = str(row.get("requestKey"))
        if key in terminal_seen:
            errors.append(f"TERMINAL_REQUEST_REISSUED:{key}")
        response_sha = row.get("responseSha256")
        if response_sha is not None:
            if not SHA256_RE.fullmatch(str(response_sha)):
                errors.append(f"RESPONSE_SHA_INVALID:{index}")
            responses.setdefault(key, set()).add(str(response_sha))
        if row.get("terminalStatus") in TERMINAL_REQUEST_STATUSES | ASSET_TERMINAL_STATUSES:
            terminal_seen.add(key)
    conflicts = sum(len(values) > 1 for values in responses.values())
    if conflicts:
        errors.append(f"REQUEST_RESPONSE_CONFLICT:{conflicts}")
    return errors, conflicts


def validate_response_manifest(
    request_rows: Iterable[Mapping[str, Any]],
    response_rows: Iterable[Mapping[str, Any]],
    raw_rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    attempts = {str(row.get("requestAttemptId")): row for row in request_rows}
    raw_by_object = {str(row.get("objectId")): row for row in raw_rows}
    response_by_key: dict[str, set[str]] = {}
    object_ids_by_pair: dict[tuple[str, str], set[str]] = {}
    for index, row in enumerate(response_rows):
        attempt_id = str(row.get("requestAttemptId"))
        request_key = str(row.get("requestKey"))
        response_sha = str(row.get("responseSha256"))
        object_id = row.get("objectId")
        if attempt_id not in attempts:
            errors.append(f"RESPONSE_ATTEMPT_ORPHAN:{index}")
        elif attempts[attempt_id].get("requestKey") != request_key:
            errors.append(f"RESPONSE_REQUEST_KEY_MISMATCH:{index}")
        if not SHA256_RE.fullmatch(response_sha):
            errors.append(f"RESPONSE_MANIFEST_SHA_INVALID:{index}")
        response_by_key.setdefault(request_key, set()).add(response_sha)
        if object_id is not None:
            if str(object_id) not in raw_by_object:
                errors.append(f"RESPONSE_RAW_OBJECT_ORPHAN:{index}")
            object_ids_by_pair.setdefault((request_key, response_sha), set()).add(str(object_id))
    for key, values in response_by_key.items():
        if len(values) > 1:
            errors.append(f"REQUEST_RESPONSE_CONFLICT:{key}")
    for (key, response_sha), object_ids in object_ids_by_pair.items():
        if len(object_ids) <= 1:
            continue
        primary = sorted(object_ids)[0]
        if any(raw_by_object[object_id].get("dedupOfObjectId") != primary for object_id in sorted(object_ids)[1:]):
            errors.append(f"DUPLICATE_RESPONSE_RAW_RESTORE:{key}:{response_sha}")
    return errors


def validate_raw_objects(rows: Iterable[Mapping[str, Any]], raw_root: Path | None) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    stats = {"rows": 0, "resolved": 0, "quarantined": 0}
    content_ids: dict[str, str] = {}
    for index, row in enumerate(rows):
        stats["rows"] += 1
        missing = [field for field in REQUIRED_RAW_FIELDS if row.get(field) is None]
        if missing:
            errors.append(f"RAW_FIELDS_MISSING:{index}:{','.join(missing)}")
            continue
        locator = row.get("objectLocatorRelative")
        if not relative_locator_valid(locator):
            errors.append(f"RAW_LOCATOR_INVALID:{index}")
            continue
        if not SHA256_RE.fullmatch(str(row.get("contentSha256", ""))):
            errors.append(f"RAW_CONTENT_SHA_INVALID:{index}")
        content_sha = str(row.get("contentSha256"))
        prior = content_ids.get(content_sha)
        if prior and row.get("dedupOfObjectId") != prior:
            errors.append(f"RAW_DUPLICATE_WITHOUT_DECLARATION:{index}")
        content_ids.setdefault(content_sha, str(row.get("objectId")))
        if raw_root is None:
            stats["quarantined"] += 1
            continue
        target = raw_root / str(locator)
        if not target.is_file():
            errors.append(f"RAW_OBJECT_MISSING:{index}")
            stats["quarantined"] += 1
            continue
        stored_bytes = target.read_bytes()
        if len(stored_bytes) != int(row.get("byteCount", -1)):
            errors.append(f"RAW_BYTE_COUNT_MISMATCH:{index}")
        compressed_sha = row.get("compressedSha256")
        if compressed_sha is not None and hashlib.sha256(stored_bytes).hexdigest() != compressed_sha:
            errors.append(f"RAW_COMPRESSED_SHA_MISMATCH:{index}")
        try:
            content_bytes = gzip.decompress(stored_bytes) if compressed_sha is not None else stored_bytes
        except (OSError, EOFError):
            errors.append(f"RAW_DECOMPRESSION_FAILED:{index}")
            content_bytes = b""
        if hashlib.sha256(content_bytes).hexdigest() != row.get("contentSha256"):
            errors.append(f"RAW_SHA_MISMATCH:{index}")
        if row.get("contentByteCount") is not None and len(content_bytes) != int(row["contentByteCount"]):
            errors.append(f"RAW_CONTENT_BYTE_COUNT_MISMATCH:{index}")
        if not any(error.endswith(f":{index}") for error in errors):
            stats["resolved"] += 1
    return errors, stats


def validate_checkpoint_chain(payload: Mapping[str, Any], raw_manifest_sha: str) -> list[str]:
    errors: list[str] = []
    checkpoints = payload.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints:
        return ["CHECKPOINT_CHAIN_MISSING"]
    previous_sha: str | None = None
    for index, row in enumerate(checkpoints):
        if row.get("previousCheckpointSha256") != previous_sha:
            errors.append(f"CHECKPOINT_CHAIN_BREAK:{index}")
        if row.get("rawObjectManifestSha256") != raw_manifest_sha:
            errors.append(f"CHECKPOINT_RAW_MANIFEST_MISMATCH:{index}")
        previous_sha = canonical_json_sha256(row)
    return errors


def validate_kill_switch(request_rows: Iterable[Mapping[str, Any]], events: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    requests = list(request_rows)
    for event in events:
        try:
            stopped_at = parse_utc(event.get("timestampUtc"))
        except ValueError:
            errors.append("KILL_SWITCH_TIMESTAMP_INVALID")
            continue
        try:
            request_after_stop = any(parse_utc(row.get("startedAtUtc")) > stopped_at for row in requests)
        except ValueError:
            errors.append(f"KILL_SWITCH_REQUEST_TIMESTAMP_INVALID:{event.get('eventId', 'UNKNOWN')}")
            request_after_stop = False
        if request_after_stop:
            errors.append(f"REQUEST_AFTER_KILL_SWITCH:{event.get('eventId', 'UNKNOWN')}")
        if not event.get("lastSafeCheckpointId"):
            errors.append(f"KILL_SWITCH_CHECKPOINT_MISSING:{event.get('eventId', 'UNKNOWN')}")
    return errors


def validate_coverage(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    if not path.is_file():
        return ["COVERAGE_ARTIFACT_MISSING"], {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_layer = {str(row.get("coverageLayer", "")).upper(): row for row in rows}
    for layer in ("MONTH", "PAGE", "POSTING", "ASSET"):
        row = by_layer.get(layer)
        if row is None:
            errors.append(f"COVERAGE_LAYER_MISSING:{layer}")
            continue
        try:
            planned = int(row.get("plannedCount", ""))
            terminal = int(row.get("terminalCount", ""))
        except ValueError:
            errors.append(f"COVERAGE_VALUE_INVALID:{layer}")
            continue
        reported_value = row.get("coverage", "")
        if reported_value == "NOT_EVALUATED":
            if planned != 0 or terminal != 0 or not row.get("emptyReason"):
                errors.append(f"COVERAGE_NOT_EVALUATED_INVALID:{layer}")
        else:
            try:
                reported = float(reported_value)
            except ValueError:
                errors.append(f"COVERAGE_VALUE_INVALID:{layer}")
                continue
            expected = 1.0 if planned == 0 and terminal == 0 else terminal / planned if planned else -1.0
            if terminal > planned or abs(reported - expected) > 1e-12:
                errors.append(f"COVERAGE_DENOMINATOR_MISMATCH:{layer}")
        if int(row.get("unknownTerminalStatusCount", 0)) != 0 or int(row.get("nullTerminalStatusCount", 0)) != 0:
            errors.append(f"COVERAGE_TERMINAL_STATUS_INCOMPLETE:{layer}")
        if str(row.get("quarantineIncluded", "")).casefold() != "true":
            errors.append(f"COVERAGE_QUARANTINE_OMITTED:{layer}")
    return errors, by_layer
