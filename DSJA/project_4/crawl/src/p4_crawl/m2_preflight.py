"""Offline-only M2 production crawl preflight controls.

This module does not contain an HTTP transport. It freezes the production
parameters, validates approval evidence, builds the 79-month plan, and tests
fail-closed health/checkpoint behavior before a user can authorize collection.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from .config import TARGET_MONTHS
from .policy import KillSwitch, SourcePolicyBlocked
from .query_registry import QueryRegistry
from .storage import canonical_json


REQUIRED_APPROVAL_FIELDS = (
    "productionApprovalId",
    "approvedBy",
    "approvedAt",
    "approvedPeriod",
    "approvedSource",
    "externalAtsTransportAllowed",
    "linkareerHostedAssetAllowed",
    "rateLimitPolicyVersion",
    "killSwitchPolicyVersion",
)


@dataclass(frozen=True)
class M2PolicyConfig:
    max_concurrency: int = 2
    requests_per_second: float = 1.0
    max_retries: int = 3
    backoff_policy: str = "exponential-jitter"
    min_success_rate: float = 0.80
    success_window: int = 20
    minimum_success_samples: int = 5
    max_consecutive_403: int = 1
    max_consecutive_429: int = 3
    max_empty_page_streak: int = 2
    checkpoint_interval: int = 1
    policy_version: str = "p4-linkareer-production-rate-v1"
    kill_switch_version: str = "p4-linkareer-kill-switch-v1"

    def __post_init__(self) -> None:
        if not 1 <= self.max_concurrency <= 2:
            raise ValueError("MAX_CONCURRENCY must be in [1, 2]")
        if not 0 < self.requests_per_second <= 1:
            raise ValueError("REQUESTS_PER_SECOND must be in (0, 1]")
        if self.max_retries < 0:
            raise ValueError("MAX_RETRIES must be non-negative")
        if self.backoff_policy != "exponential-jitter":
            raise ValueError("unsupported BACKOFF_POLICY")
        if not 0 < self.min_success_rate <= 1:
            raise ValueError("MIN_SUCCESS_RATE must be in (0, 1]")
        if min(self.max_consecutive_403, self.max_consecutive_429, self.max_empty_page_streak) < 1:
            raise ValueError("kill-switch thresholds must be positive")

    def as_frozen_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key.upper(): value for key, value in payload.items()}


class ProductionHealthMonitor:
    """Deterministic kill-switch state used by transport and negative tests."""

    def __init__(self, config: M2PolicyConfig | None = None) -> None:
        self.config = config or M2PolicyConfig()
        self.kill_switch = KillSwitch()
        self.outcomes: deque[bool] = deque(maxlen=self.config.success_window)
        self.consecutive_403 = 0
        self.consecutive_429 = 0
        self.empty_page_streak = 0

    def observe_response(self, status_code: int, content_type: str = "application/json") -> None:
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: UNEXPECTED_CONTENT_TYPE")
            raise SourcePolicyBlocked(self.kill_switch.reason)
        self.consecutive_403 = self.consecutive_403 + 1 if status_code == 403 else 0
        self.consecutive_429 = self.consecutive_429 + 1 if status_code == 429 else 0
        self.outcomes.append(200 <= status_code < 400)
        if self.consecutive_403 >= self.config.max_consecutive_403:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MAX_CONSECUTIVE_403")
        elif self.consecutive_429 >= self.config.max_consecutive_429:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MAX_CONSECUTIVE_429")
        elif len(self.outcomes) >= self.config.minimum_success_samples:
            if sum(self.outcomes) / len(self.outcomes) < self.config.min_success_rate:
                self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MIN_SUCCESS_RATE")
        self.kill_switch.check()

    def observe_page(self, *, empty: bool, exhausted: bool = False) -> None:
        self.empty_page_streak = self.empty_page_streak + 1 if empty and not exhausted else 0
        if self.empty_page_streak >= self.config.max_empty_page_streak:
            self.kill_switch.trip("SOURCE_POLICY_BLOCKED: MAX_EMPTY_PAGE_STREAK")
        self.kill_switch.check()

    def schema_drift(self, reason: str) -> None:
        self.kill_switch.trip(f"SOURCE_POLICY_BLOCKED: SCHEMA_DRIFT: {reason}")
        self.kill_switch.check()


def validate_approval(payload: Mapping[str, Any] | None, policy: M2PolicyConfig | None = None) -> list[str]:
    policy = policy or M2PolicyConfig()
    if payload is None:
        return ["PRODUCTION_APPROVAL_MISSING"]
    errors = [f"missing:{field}" for field in REQUIRED_APPROVAL_FIELDS if field not in payload]
    if payload.get("approvedPeriod") != "2020-01~2026-07":
        errors.append("approvedPeriod:mismatch")
    if payload.get("approvedSource") != "Linkareer":
        errors.append("approvedSource:mismatch")
    if payload.get("externalAtsTransportAllowed") is not False:
        errors.append("externalAtsTransportAllowed:must-be-false")
    if payload.get("linkareerHostedAssetAllowed") is not True:
        errors.append("linkareerHostedAssetAllowed:must-be-true")
    if payload.get("rateLimitPolicyVersion") != policy.policy_version:
        errors.append("rateLimitPolicyVersion:mismatch")
    if payload.get("killSwitchPolicyVersion") != policy.kill_switch_version:
        errors.append("killSwitchPolicyVersion:mismatch")
    return sorted(set(errors))


def require_approval(payload: Mapping[str, Any] | None, policy: M2PolicyConfig | None = None) -> None:
    errors = validate_approval(payload, policy)
    if errors:
        raise SourcePolicyBlocked("SOURCE_POLICY_PRODUCTION_APPROVAL_REQUIRED: " + ",".join(errors))


def build_month_plan(baseline_csv: Path) -> pd.DataFrame:
    baseline = pd.read_csv(baseline_csv, encoding="utf-8-sig", dtype={"periodMonth": str})
    baseline = baseline[baseline["periodMonth"].isin(TARGET_MONTHS)].copy()
    if baseline["periodMonth"].duplicated().any():
        raise ValueError("duplicate target month in baseline coverage")
    by_month = baseline.set_index("periodMonth").to_dict("index")
    rows = []
    for sequence, period in enumerate(TARGET_MONTHS, start=1):
        year, month = map(int, period.split("-"))
        base = by_month.get(period, {})
        complete = str(base.get("coverageStatus", "")) == "complete" and bool(base.get("paginationCompleteFlag"))
        request_count = base.get("requestCount", 0)
        request_count = 0 if pd.isna(request_count) else int(request_count)
        rows.append({
            "planOrder": sequence,
            "periodMonth": period,
            "startDateUtc": f"{period}-01T00:00:00Z",
            "endDateUtc": f"{period}-{calendar.monthrange(year, month)[1]:02d}T23:59:59Z",
            "activityTypeID": 5,
            "baselineCoverageStatus": base.get("coverageStatus", "missing"),
            "baselineCoverageReason": base.get("coverageReason", "missing"),
            "baselinePaginationComplete": complete,
            "baselineRequestCount": request_count,
            "plannedAction": "VERIFY_EXISTING_BYTES" if complete else "COLLECT_AND_EXHAUST_BUCKETS",
            "terminalStatusRequired": True,
        })
    frame = pd.DataFrame(rows)
    if len(frame) != 79 or frame.iloc[0]["periodMonth"] != "2020-01" or frame.iloc[-1]["periodMonth"] != "2026-07":
        raise AssertionError("M2 target month contract violated")
    return frame


def validate_query_registry(path: Path) -> dict[str, Any]:
    registry = QueryRegistry.load(path)
    required = {"CalendarScreen_ActivityCalendarEntries", "CalendarScreen_Activities"}
    names = set(registry.names())
    missing = sorted(required - names)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    unresolved = [
        row["operationName"]
        for row in payload.get("queries", [])
        if "unresolved" in str(row.get("note", "")).lower()
    ]
    return {
        "queryCount": len(names),
        "requiredMissing": missing,
        "unresolvedSemantics": unresolved,
        "registrySha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "PASS" if not missing and not unresolved else "FAIL",
    }


def checkpoint_envelope(state: Mapping[str, Any]) -> dict[str, Any]:
    canonical = canonical_json(dict(state)).encode("utf-8")
    return {"state": dict(state), "stateSha256": hashlib.sha256(canonical).hexdigest()}


def load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        state = envelope["state"]
        expected = hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
        if envelope.get("stateSha256") != expected:
            raise ValueError("state SHA-256 mismatch")
        return state
    except Exception as exc:
        raise SourcePolicyBlocked(f"SOURCE_POLICY_BLOCKED: CHECKPOINT_CORRUPTION: {type(exc).__name__}") from exc


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
