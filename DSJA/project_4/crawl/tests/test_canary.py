from __future__ import annotations

import ast
import copy
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from p4_crawl.canary import (
    TERMINAL_DETAIL_STATUSES,
    CanaryKillSwitch,
    CanaryKillSwitchTripped,
    CanaryPolicyBlocked,
    CanaryScopeBlocked,
    CanaryScopeGuard,
    CanaryStateMachine,
    CanaryStatus,
    RequestLedger,
    RequestResponseConflict,
    checkpoint_envelope,
    request_fingerprint,
    request_key,
    require_canary_approval,
    validate_canary_approval,
    validate_checkpoint,
)
from p4_crawl.raw_authority import (
    AVAILABLE,
    COMPRESSED_SHA_MISMATCH,
    RAW_ROOT_UNMOUNTED,
    build_raw_object_manifest,
    validate_manifest_against_mount,
)


CRAWL_ROOT = Path(__file__).resolve().parents[1]
QUERY_SHA = hashlib.sha256((CRAWL_ROOT / "configs/queryRegistry.yaml").read_bytes()).hexdigest()
POLICY_SHA = "a" * 64
NOW = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)


def approval(**overrides) -> dict:
    payload = {
        "canaryApprovalId": "CANARY-APPROVAL-TEST",
        "approvedBy": "test-owner",
        "approvedAtUtc": "2026-08-06T23:00:00Z",
        "expiresAtUtc": "2026-08-07T01:00:00Z",
        "approvedSource": "LINKAREER",
        "approvedCanaryScope": {
            "periodMonths": ["2026-07"],
            "queryOperations": ["CalendarScreen_ActivityCalendarEntries"],
            "postingIds": ["42"],
        },
        "approvedMaxRequests": 3,
        "approvedMaxDetailRequests": 1,
        "approvedMaxAssetRequests": 1,
        "linkareerHostedAssetAllowed": True,
        "externalAtsTransportAllowed": False,
        "rateLimitPolicyVersion": "p4-linkareer-production-rate-v1",
        "killSwitchPolicyVersion": "p4-linkareer-kill-switch-v1",
        "queryRegistrySha256": QUERY_SHA,
        "sourcePolicyAuditSha256": POLICY_SHA,
    }
    payload.update(overrides)
    return payload


def test_missing_or_expired_approval_blocks_before_transport() -> None:
    with pytest.raises(CanaryPolicyBlocked, match="CANARY_APPROVAL_MISSING"):
        require_canary_approval(None, query_registry_sha256=QUERY_SHA, source_policy_audit_sha256=POLICY_SHA, now=NOW)
    expired = approval(expiresAtUtc="2026-08-06T23:30:00Z")
    assert "expiresAtUtc:expired" in validate_canary_approval(
        expired, query_registry_sha256=QUERY_SHA, source_policy_audit_sha256=POLICY_SHA, now=NOW
    )


def test_approval_hash_and_external_ats_policy_are_bound() -> None:
    assert validate_canary_approval(
        approval(), query_registry_sha256=QUERY_SHA, source_policy_audit_sha256=POLICY_SHA, now=NOW
    ) == []
    wrong = approval(queryRegistrySha256="0" * 64, externalAtsTransportAllowed=True)
    errors = validate_canary_approval(
        wrong, query_registry_sha256=QUERY_SHA, source_policy_audit_sha256=POLICY_SHA, now=NOW
    )
    assert "queryRegistrySha256:mismatch" in errors
    assert "externalAtsTransportAllowed:must-be-false" in errors


def test_approval_schema_rejects_out_of_contract_scope() -> None:
    schema = json.loads((CRAWL_ROOT / "control/CANARY_APPROVAL.schema.json").read_text())
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(approval())
    invalid = approval(approvedSource="OTHER")
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(invalid)


def test_scope_and_request_budgets_stop_before_transport() -> None:
    guard = CanaryScopeGuard(approval())
    guard.authorize("index", period_month="2026-07", url="https://api.linkareer.com/graphql", now=NOW)
    guard.authorize("detail", period_month="2026-07", url="https://linkareer.com/activity/42", now=NOW)
    guard.authorize("asset", period_month="2026-07", url="https://cdn.linkareer.com/a.png", now=NOW)
    with pytest.raises(CanaryScopeBlocked, match="approvedMaxRequests"):
        guard.authorize("index", period_month="2026-07", url="https://api.linkareer.com/graphql", now=NOW)


def test_period_and_external_ats_are_policy_blocked_before_transport() -> None:
    guard = CanaryScopeGuard(approval())
    with pytest.raises(CanaryPolicyBlocked, match="PERIOD_OUTSIDE"):
        guard.authorize("index", period_month="2026-06", url="https://api.linkareer.com/graphql", now=NOW)
    with pytest.raises(CanaryPolicyBlocked, match="EXTERNAL_ATS_BLOCKED_BEFORE_TRANSPORT"):
        guard.authorize("asset", period_month="2026-07", url="https://jobs.example.invalid/a.png", now=NOW)
    assert guard.total_requests == 0


def test_approval_expiration_during_run_trips_kill_switch() -> None:
    guard = CanaryScopeGuard(approval())
    with pytest.raises(CanaryKillSwitchTripped, match="APPROVAL_EXPIRED"):
        guard.authorize(
            "index",
            period_month="2026-07",
            query_operation="CalendarScreen_ActivityCalendarEntries",
            url="https://api.linkareer.com/graphql",
            now=datetime(2026, 8, 7, 2, 0, tzinfo=UTC),
        )
    assert guard.total_requests == 0


def test_query_operation_outside_scope_is_blocked() -> None:
    guard = CanaryScopeGuard(approval())
    with pytest.raises(CanaryPolicyBlocked, match="QUERY_OUTSIDE"):
        guard.authorize(
            "index",
            period_month="2026-07",
            query_operation="UnapprovedOperation",
            url="https://api.linkareer.com/graphql",
            now=NOW,
        )


def test_request_key_is_deterministic_and_secret_parameters_trip() -> None:
    left = request_key("index", {"page": 1, "filter": {"activityTypeID": 5}}, period_month="2026-07")
    right = request_key("index", {"filter": {"activityTypeID": 5}, "page": 1}, period_month="2026-07")
    assert left == right
    assert request_fingerprint({"page": 1}) == request_fingerprint({"page": 1})
    with pytest.raises(CanaryKillSwitchTripped, match="SECRET_LOGGING_DETECTION"):
        request_key("index", {"Authorization": "Bearer forbidden"}, period_month="2026-07")


def test_request_ledger_deduplicates_and_quarantines_conflict() -> None:
    ledger = RequestLedger()
    key = "1" * 64
    assert ledger.record_terminal(key, "a" * 64, "FETCHED_VALID") == "RECORDED"
    assert ledger.record_terminal(key, "a" * 64, "FETCHED_VALID") == "DUPLICATE_NO_RESTORE"
    assert ledger.duplicate_count == 1
    with pytest.raises(RequestResponseConflict, match="REQUEST_RESPONSE_CONFLICT"):
        ledger.record_terminal(key, "b" * 64, "FETCHED_VALID")
    assert ledger.conflict_count == 1


def test_terminal_request_retry_is_blocked_without_explicit_approval() -> None:
    ledger = RequestLedger()
    key = "2" * 64
    ledger.record_terminal(key, "a" * 64, "NOT_FOUND")
    with pytest.raises(CanaryPolicyBlocked, match="TERMINAL_REQUEST_RETRY_BLOCKED"):
        ledger.require_retry_allowed(key)
    ledger.require_retry_allowed(key, approval_allows_terminal_retry=True)


def test_kill_switch_403_429_content_schema_and_success_rate() -> None:
    with pytest.raises(CanaryKillSwitchTripped, match="MAX_CONSECUTIVE_403"):
        CanaryKillSwitch().response(403)
    monitor = CanaryKillSwitch(minimum_success_samples=20)
    monitor.response(429)
    monitor.response(429)
    with pytest.raises(CanaryKillSwitchTripped, match="MAX_CONSECUTIVE_429"):
        monitor.response(429)
    with pytest.raises(CanaryKillSwitchTripped, match="UNEXPECTED_CONTENT_TYPE"):
        CanaryKillSwitch().response(200, "text/html")
    with pytest.raises(CanaryKillSwitchTripped, match="SCHEMA_DRIFT"):
        CanaryKillSwitch().schema_drift("missing nodes")
    monitor = CanaryKillSwitch(minimum_success_samples=5)
    for code in (200, 500, 500, 500):
        monitor.response(code)
    with pytest.raises(CanaryKillSwitchTripped, match="MIN_SUCCESS_RATE"):
        monitor.response(500)


def test_pagination_cursor_loop_and_empty_streak_stop() -> None:
    monitor = CanaryKillSwitch()
    monitor.page(cursor="cursor-1", empty=False)
    with pytest.raises(CanaryKillSwitchTripped, match="CURSOR_LOOP"):
        monitor.page(cursor="cursor-1", empty=False)
    monitor = CanaryKillSwitch()
    monitor.page(cursor="cursor-1", empty=True)
    with pytest.raises(CanaryKillSwitchTripped, match="MAX_EMPTY_PAGE_STREAK"):
        monitor.page(cursor="cursor-2", empty=True)


def test_checkpoint_chain_and_corruption_fail_closed() -> None:
    first = checkpoint_envelope({"page": 1})
    assert validate_checkpoint(first) == {"page": 1}
    second = checkpoint_envelope({"page": 2}, first["checkpointSha256"])
    assert validate_checkpoint(second, expected_previous_sha256=first["checkpointSha256"]) == {"page": 2}
    broken = copy.deepcopy(second)
    broken["state"]["page"] = 3
    with pytest.raises(CanaryKillSwitchTripped, match="CHECKPOINT_CORRUPTION"):
        validate_checkpoint(broken, expected_previous_sha256=first["checkpointSha256"])


def test_fixture_raw_mount_unmounted_and_wrong_sha(tmp_path: Path) -> None:
    content = b"<html>fixture</html>"
    locator = "objects/detail-42.html.gz"
    object_path = tmp_path / locator
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(gzip.compress(content, mtime=0))
    source = [{
        "sourcePostingId": "42",
        "rawPath": locator,
        "rawSha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "fetchedAt": "2026-08-07T00:00:00Z",
        "sourceUrl": "https://linkareer.com/activity/42",
    }]
    manifest, audit = build_raw_object_manifest(
        source, tmp_path, storage_root_id="P4_CANARY_FIXTURE", mount_policy_version="p4-raw-mount-v1"
    )
    assert audit[0]["availabilityStatus"] == AVAILABLE
    unmounted = validate_manifest_against_mount(manifest, tmp_path / "unmounted")
    assert unmounted[0]["availabilityStatus"] == RAW_ROOT_UNMOUNTED
    tampered = copy.deepcopy(manifest)
    tampered[0]["compressedSha256"] = "0" * 64
    wrong = validate_manifest_against_mount(tampered, tmp_path)
    assert wrong[0]["availabilityStatus"] == COMPRESSED_SHA_MISMATCH
    assert wrong[0]["bindingStatus"] == "QUARANTINED"


def test_state_machine_blocks_network_path_without_approval() -> None:
    machine = CanaryStateMachine()
    machine.transition(CanaryStatus.FIXTURE_REGRESSION)
    machine.transition(CanaryStatus.DEBUG_REPORT)
    machine.transition(CanaryStatus.BLOCKED_POLICY)
    assert machine.state == CanaryStatus.BLOCKED_POLICY
    assert CanaryStatus.INDEX_RUNNING not in machine.history


def test_detail_terminal_enum_is_closed() -> None:
    assert TERMINAL_DETAIL_STATUSES == {
        "FETCHED_VALID", "FETCHED_EMPTY_VALID", "NOT_FOUND", "EXPIRED",
        "POLICY_BLOCKED", "RETRY_EXHAUSTED", "PARSER_QUARANTINED",
    }


def test_canary_control_and_fixture_runner_have_no_network_transport_import() -> None:
    forbidden = {"requests", "httpx", "aiohttp", "urllib.request", "curl_cffi", "playwright", "selenium"}
    for path in (
        CRAWL_ROOT / "src/p4_crawl/canary.py",
        CRAWL_ROOT / "scripts/run_canary_fixture.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not imports.intersection(forbidden)
