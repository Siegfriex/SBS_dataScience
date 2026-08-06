"""Fail-closed control plane for bounded Linkareer canary crawls.

This module deliberately contains no network transport.  A caller may obtain a
transport only after validating a time-bounded approval, scope and request
budget through these controls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .storage import atomic_write_json, canonical_json


APPROVAL_FIELDS = (
    "canaryApprovalId",
    "approvedBy",
    "approvedAtUtc",
    "expiresAtUtc",
    "approvedSource",
    "approvedCanaryScope",
    "approvedMaxRequests",
    "approvedMaxDetailRequests",
    "approvedMaxAssetRequests",
    "linkareerHostedAssetAllowed",
    "externalAtsTransportAllowed",
    "rateLimitPolicyVersion",
    "killSwitchPolicyVersion",
    "queryRegistrySha256",
    "sourcePolicyAuditSha256",
)
TERMINAL_DETAIL_STATUSES = frozenset({
    "FETCHED_VALID",
    "FETCHED_EMPTY_VALID",
    "NOT_FOUND",
    "EXPIRED",
    "POLICY_BLOCKED",
    "RETRY_EXHAUSTED",
    "PARSER_QUARANTINED",
})
SENSITIVE_PARAMETER_NAMES = frozenset({
    "authorization", "cookie", "set-cookie", "apikey", "api_key",
    "servicekey", "service_key", "token", "access_token", "refresh_token",
})


class CanaryStatus(StrEnum):
    PLANNED = "CANARY_PLANNED"
    APPROVAL_VALIDATED = "CANARY_APPROVAL_VALIDATED"
    FIXTURE_REGRESSION = "CANARY_FIXTURE_REGRESSION"
    INDEX_RUNNING = "CANARY_INDEX_RUNNING"
    DETAIL_RUNNING = "CANARY_DETAIL_RUNNING"
    ASSET_RUNNING = "CANARY_ASSET_RUNNING"
    VALIDATION = "CANARY_VALIDATION"
    DEBUG_REPORT = "CANARY_DEBUG_REPORT"
    READY = "CANARY_READY_FOR_NEXT_SCOPE"
    BLOCKED_POLICY = "CANARY_BLOCKED_BY_POLICY"
    STOPPED_KILL_SWITCH = "CANARY_STOPPED_BY_KILL_SWITCH"
    STOPPED_SCOPE = "CANARY_STOPPED_BY_SCOPE_LIMIT"
    QUARANTINED = "CANARY_QUARANTINED"
    FAILED = "CANARY_FAILED"


class CanaryBlocked(RuntimeError):
    status = CanaryStatus.FAILED


class CanaryPolicyBlocked(CanaryBlocked):
    status = CanaryStatus.BLOCKED_POLICY


class CanaryScopeBlocked(CanaryBlocked):
    status = CanaryStatus.STOPPED_SCOPE


class CanaryKillSwitchTripped(CanaryBlocked):
    status = CanaryStatus.STOPPED_KILL_SWITCH


class RequestResponseConflict(CanaryBlocked):
    status = CanaryStatus.QUARANTINED


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must include timezone")
    return parsed.astimezone(UTC)


def validate_canary_approval(
    payload: Mapping[str, Any] | None,
    *,
    query_registry_sha256: str,
    source_policy_audit_sha256: str,
    now: datetime | None = None,
) -> list[str]:
    if payload is None:
        return ["CANARY_APPROVAL_MISSING"]
    errors = [f"missing:{name}" for name in APPROVAL_FIELDS if name not in payload]
    if errors:
        return sorted(errors)
    if payload.get("approvedSource") != "LINKAREER":
        errors.append("approvedSource:must-be-LINKAREER")
    if payload.get("externalAtsTransportAllowed") is not False:
        errors.append("externalAtsTransportAllowed:must-be-false")
    if payload.get("linkareerHostedAssetAllowed") is not True:
        errors.append("linkareerHostedAssetAllowed:must-be-true")
    for name in ("approvedMaxRequests", "approvedMaxDetailRequests", "approvedMaxAssetRequests"):
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{name}:non-negative-integer-required")
    if isinstance(payload.get("approvedMaxRequests"), int):
        if int(payload.get("approvedMaxDetailRequests", 0)) + int(payload.get("approvedMaxAssetRequests", 0)) > int(payload["approvedMaxRequests"]):
            errors.append("typedRequestBudgets:exceed-total")
    scope = payload.get("approvedCanaryScope")
    if not isinstance(scope, Mapping) or not scope.get("periodMonths"):
        errors.append("approvedCanaryScope:periodMonths-required")
    if payload.get("queryRegistrySha256") != query_registry_sha256:
        errors.append("queryRegistrySha256:mismatch")
    if payload.get("sourcePolicyAuditSha256") != source_policy_audit_sha256:
        errors.append("sourcePolicyAuditSha256:mismatch")
    try:
        approved_at = parse_utc(str(payload["approvedAtUtc"]))
        expires_at = parse_utc(str(payload["expiresAtUtc"]))
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if approved_at > current:
            errors.append("approvedAtUtc:future")
        if expires_at <= current:
            errors.append("expiresAtUtc:expired")
        if expires_at <= approved_at:
            errors.append("approvalWindow:invalid")
    except (KeyError, TypeError, ValueError):
        errors.append("approvalTimestamp:invalid")
    return sorted(set(errors))


def require_canary_approval(payload: Mapping[str, Any] | None, **kwargs: Any) -> None:
    errors = validate_canary_approval(payload, **kwargs)
    if errors:
        raise CanaryPolicyBlocked("CANARY_BLOCKED_BY_POLICY: " + ",".join(errors))


def _redact_and_normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value, key=str):
            normalized_key = str(key)
            if normalized_key.lower() in SENSITIVE_PARAMETER_NAMES:
                raise CanaryKillSwitchTripped(f"SECRET_LOGGING_DETECTION:{normalized_key}")
            normalized[normalized_key] = _redact_and_normalize(value[key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_redact_and_normalize(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError(f"unsupported request parameter type: {type(value).__name__}")


def request_key(
    logical_request_type: str,
    parameters: Mapping[str, Any],
    *,
    period_month: str = "",
    posting_id: str = "",
    asset_id: str = "",
) -> str:
    payload = {
        "logicalRequestType": str(logical_request_type),
        "normalizedRedactedParameters": _redact_and_normalize(parameters),
        "periodMonth": str(period_month),
        "postingId": str(posting_id),
        "assetId": str(asset_id),
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def request_fingerprint(parameters: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(_redact_and_normalize(parameters)).encode("utf-8"))


@dataclass
class CanaryScopeGuard:
    approval: Mapping[str, Any]
    total_requests: int = 0
    detail_requests: int = 0
    asset_requests: int = 0

    def authorize(
        self,
        request_type: str,
        *,
        period_month: str = "",
        query_operation: str = "",
        url: str = "",
        now: datetime | None = None,
    ) -> None:
        scope = self.approval["approvedCanaryScope"]
        if parse_utc(str(self.approval["expiresAtUtc"])) <= (now or datetime.now(UTC)).astimezone(UTC):
            raise CanaryKillSwitchTripped("CANARY_STOPPED_BY_KILL_SWITCH:APPROVAL_EXPIRED")
        if period_month and period_month not in set(scope.get("periodMonths", [])):
            raise CanaryPolicyBlocked(f"PERIOD_OUTSIDE_APPROVED_CANARY_SCOPE:{period_month}")
        if query_operation and query_operation not in set(scope.get("queryOperations", [])):
            raise CanaryPolicyBlocked(f"QUERY_OUTSIDE_APPROVED_CANARY_SCOPE:{query_operation}")
        if url:
            host = (urlsplit(url).hostname or "").lower()
            if host != "linkareer.com" and not host.endswith(".linkareer.com"):
                raise CanaryPolicyBlocked(f"EXTERNAL_ATS_BLOCKED_BEFORE_TRANSPORT:{host or 'invalid-host'}")
        next_total = self.total_requests + 1
        if next_total > int(self.approval["approvedMaxRequests"]):
            raise CanaryScopeBlocked("STOPPED_BY_SCOPE_LIMIT:approvedMaxRequests")
        if request_type == "detail" and self.detail_requests + 1 > int(self.approval["approvedMaxDetailRequests"]):
            raise CanaryScopeBlocked("STOPPED_BY_SCOPE_LIMIT:approvedMaxDetailRequests")
        if request_type == "asset" and self.asset_requests + 1 > int(self.approval["approvedMaxAssetRequests"]):
            raise CanaryScopeBlocked("STOPPED_BY_SCOPE_LIMIT:approvedMaxAssetRequests")
        self.total_requests = next_total
        if request_type == "detail":
            self.detail_requests += 1
        elif request_type == "asset":
            self.asset_requests += 1


@dataclass
class RequestLedger:
    terminal: dict[str, dict[str, Any]] = field(default_factory=dict)
    duplicate_count: int = 0
    conflict_count: int = 0

    def record_terminal(self, key: str, response_sha256: str, terminal_status: str) -> str:
        previous = self.terminal.get(key)
        if previous:
            if previous["responseSha256"] == response_sha256:
                self.duplicate_count += 1
                return "DUPLICATE_NO_RESTORE"
            self.conflict_count += 1
            raise RequestResponseConflict(f"REQUEST_RESPONSE_CONFLICT:{key}")
        self.terminal[key] = {
            "responseSha256": response_sha256,
            "terminalStatus": terminal_status,
        }
        return "RECORDED"

    def require_retry_allowed(self, key: str, *, approval_allows_terminal_retry: bool = False) -> None:
        if key in self.terminal and not approval_allows_terminal_retry:
            raise CanaryPolicyBlocked(f"TERMINAL_REQUEST_RETRY_BLOCKED:{key}")


@dataclass
class CanaryKillSwitch:
    max_consecutive_403: int = 1
    max_consecutive_429: int = 3
    max_empty_page_streak: int = 2
    min_success_rate: float = 0.8
    minimum_success_samples: int = 5
    events: list[dict[str, Any]] = field(default_factory=list)
    consecutive_403: int = 0
    consecutive_429: int = 0
    empty_page_streak: int = 0
    cursor_history: set[str] = field(default_factory=set)
    outcomes: list[bool] = field(default_factory=list)

    def trip(self, reason: str) -> None:
        self.events.append({"reason": reason, "terminalStatus": CanaryStatus.STOPPED_KILL_SWITCH})
        raise CanaryKillSwitchTripped(f"CANARY_STOPPED_BY_KILL_SWITCH:{reason}")

    def response(self, status_code: int, content_type: str = "application/json") -> None:
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            self.trip("UNEXPECTED_CONTENT_TYPE")
        self.consecutive_403 = self.consecutive_403 + 1 if status_code == 403 else 0
        self.consecutive_429 = self.consecutive_429 + 1 if status_code == 429 else 0
        self.outcomes.append(200 <= status_code < 400)
        if self.consecutive_403 >= self.max_consecutive_403:
            self.trip("MAX_CONSECUTIVE_403")
        if self.consecutive_429 >= self.max_consecutive_429:
            self.trip("MAX_CONSECUTIVE_429")
        recent = self.outcomes[-20:]
        if len(recent) >= self.minimum_success_samples and sum(recent) / len(recent) < self.min_success_rate:
            self.trip("MIN_SUCCESS_RATE")

    def page(self, *, cursor: str, empty: bool, exhausted: bool = False) -> None:
        if cursor and cursor in self.cursor_history:
            self.trip("CURSOR_LOOP")
        if cursor:
            self.cursor_history.add(cursor)
        self.empty_page_streak = self.empty_page_streak + 1 if empty and not exhausted else 0
        if self.empty_page_streak >= self.max_empty_page_streak:
            self.trip("MAX_EMPTY_PAGE_STREAK")

    def schema_drift(self, reason: str) -> None:
        self.trip(f"SCHEMA_DRIFT:{reason}")


TRANSITIONS: dict[CanaryStatus, frozenset[CanaryStatus]] = {
    CanaryStatus.PLANNED: frozenset({CanaryStatus.APPROVAL_VALIDATED, CanaryStatus.FIXTURE_REGRESSION, CanaryStatus.BLOCKED_POLICY}),
    CanaryStatus.APPROVAL_VALIDATED: frozenset({CanaryStatus.FIXTURE_REGRESSION}),
    CanaryStatus.FIXTURE_REGRESSION: frozenset({CanaryStatus.INDEX_RUNNING, CanaryStatus.DEBUG_REPORT, CanaryStatus.BLOCKED_POLICY}),
    CanaryStatus.INDEX_RUNNING: frozenset({CanaryStatus.DETAIL_RUNNING, CanaryStatus.VALIDATION}),
    CanaryStatus.DETAIL_RUNNING: frozenset({CanaryStatus.ASSET_RUNNING, CanaryStatus.VALIDATION}),
    CanaryStatus.ASSET_RUNNING: frozenset({CanaryStatus.VALIDATION}),
    CanaryStatus.VALIDATION: frozenset({CanaryStatus.DEBUG_REPORT}),
    CanaryStatus.DEBUG_REPORT: frozenset({CanaryStatus.READY, CanaryStatus.BLOCKED_POLICY}),
}


@dataclass
class CanaryStateMachine:
    state: CanaryStatus = CanaryStatus.PLANNED
    history: list[str] = field(default_factory=lambda: [CanaryStatus.PLANNED])

    def transition(self, target: CanaryStatus) -> None:
        failure_states = {
            CanaryStatus.BLOCKED_POLICY,
            CanaryStatus.STOPPED_KILL_SWITCH,
            CanaryStatus.STOPPED_SCOPE,
            CanaryStatus.QUARANTINED,
            CanaryStatus.FAILED,
        }
        if target not in failure_states and target not in TRANSITIONS.get(self.state, frozenset()):
            raise ValueError(f"invalid canary transition: {self.state}->{target}")
        self.state = target
        self.history.append(target)


def checkpoint_envelope(state: Mapping[str, Any], previous_checkpoint_sha256: str = "") -> dict[str, Any]:
    payload = {
        "state": dict(state),
        "previousCheckpointSha256": previous_checkpoint_sha256,
    }
    payload["checkpointSha256"] = sha256_bytes(canonical_json(payload).encode("utf-8"))
    return payload


def validate_checkpoint(envelope: Mapping[str, Any], *, expected_previous_sha256: str = "") -> dict[str, Any]:
    unsigned = {
        "state": envelope.get("state"),
        "previousCheckpointSha256": envelope.get("previousCheckpointSha256", ""),
    }
    observed = sha256_bytes(canonical_json(unsigned).encode("utf-8"))
    if envelope.get("checkpointSha256") != observed:
        raise CanaryKillSwitchTripped("CANARY_STOPPED_BY_KILL_SWITCH:CHECKPOINT_CORRUPTION")
    if unsigned["previousCheckpointSha256"] != expected_previous_sha256:
        raise CanaryKillSwitchTripped("CANARY_STOPPED_BY_KILL_SWITCH:CHECKPOINT_CHAIN_BROKEN")
    return dict(unsigned["state"] or {})


def write_checkpoint(path: Path, state: Mapping[str, Any], previous_checkpoint_sha256: str = "") -> dict[str, Any]:
    envelope = checkpoint_envelope(state, previous_checkpoint_sha256)
    atomic_write_json(path, envelope)
    return envelope
