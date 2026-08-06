"""Production-only monthly APQ orchestration with resumable signed checkpoints."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .coverage import collect_month
from .policy import SourcePolicyBlocked, SourcePolicyConfig
from .storage import atomic_write_json, canonical_json, sha256_bytes


def production_index_plan(periods: Iterable[str], policy: SourcePolicyConfig | None = None) -> dict:
    """Return the serializable production control plan without opening transport."""

    policy = policy or SourcePolicyConfig()
    return {
        "runMode": "production",
        "productionApprovalRequired": True,
        "periods": list(periods),
        "MAX_CONCURRENCY": policy.max_concurrency,
        "REQUESTS_PER_SECOND": policy.requests_per_second,
        "MAX_RETRIES": policy.max_retries,
        "BACKOFF_POLICY": policy.backoff_policy,
        "MIN_SUCCESS_RATE": policy.min_success_rate,
        "MAX_CONSECUTIVE_403": policy.max_consecutive_403,
        "MAX_CONSECUTIVE_429": policy.max_consecutive_429,
        "MAX_EMPTY_PAGE_STREAK": policy.max_empty_page_streak,
        "CHECKPOINT_INTERVAL": policy.checkpoint_interval,
    }


def checkpoint_envelope(state: dict) -> dict:
    return {
        "state": state,
        "stateSha256": sha256_bytes(canonical_json(state).encode("utf-8")),
    }


def write_checkpoint(path: Path, state: dict) -> None:
    atomic_write_json(path, checkpoint_envelope(state))


def load_checkpoint(path: Path, http=None) -> dict:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        state = envelope["state"]
        expected = sha256_bytes(canonical_json(state).encode("utf-8"))
        if envelope.get("stateSha256") != expected:
            raise ValueError("state SHA-256 mismatch")
        return state
    except Exception as exc:
        if http is not None:
            http.health.checkpoint_corruption(f"{type(exc).__name__}: {exc}")
            http.kill_switch.check()
        raise SourcePolicyBlocked(f"SOURCE_POLICY_BLOCKED: CHECKPOINT_CORRUPTION: {type(exc).__name__}") from exc


def run_production_index(
    periods: Iterable[str],
    apq,
    output_root: Path,
    *,
    run_mode: str,
    production_approved: bool,
    policy: SourcePolicyConfig | None = None,
) -> list[dict]:
    """Collect month-grain production index state only after explicit approval."""

    if run_mode != "production" or not production_approved:
        raise SourcePolicyBlocked("SOURCE_POLICY_PRODUCTION_APPROVAL_REQUIRED")
    policy = policy or apq.http.policy
    checkpoint_path = output_root / "index_checkpoint.json"
    state = load_checkpoint(checkpoint_path, apq.http) if checkpoint_path.exists() else {
        "completedPeriods": [],
        "policy": asdict(policy),
    }
    completed = set(state["completedPeriods"])
    rows: list[dict] = []
    for sequence, period in enumerate(periods, start=1):
        if period in completed:
            continue
        apq.http.kill_switch.check()
        row = collect_month(period, apq, output_root / "coverage")
        rows.append(row)
        completed.add(period)
        state["completedPeriods"] = sorted(completed)
        state["lastPeriod"] = period
        if sequence % policy.checkpoint_interval == 0:
            write_checkpoint(checkpoint_path, state)
    write_checkpoint(checkpoint_path, state)
    return rows
