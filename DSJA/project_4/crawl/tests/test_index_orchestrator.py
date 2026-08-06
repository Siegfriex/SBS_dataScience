from __future__ import annotations

import json
from pathlib import Path

import pytest

from p4_crawl.index_orchestrator import load_checkpoint, production_index_plan, run_production_index, write_checkpoint
from p4_crawl.policy import PolicyHttpClient, RateLimiter, SourcePolicyBlocked


def client() -> PolicyHttpClient:
    limiter = RateLimiter(
        1.0,
        clock=lambda: 0.0,
        sleeper=lambda _seconds: None,
        random_uniform=lambda _a, _b: 0.0,
    )
    return PolicyHttpClient(lambda _url, **_kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")), limiter=limiter)


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, {"completedPeriods": ["2021-03"]})
    assert load_checkpoint(path) == {"completedPeriods": ["2021-03"]}


def test_checkpoint_corruption_trips_kill_switch(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, {"completedPeriods": ["2021-03"]})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state"]["completedPeriods"].append("2021-04")
    path.write_text(json.dumps(payload), encoding="utf-8")
    http = client()
    with pytest.raises(SourcePolicyBlocked, match="CHECKPOINT_CORRUPTION"):
        load_checkpoint(path, http)


def test_production_index_requires_explicit_approval_before_transport(tmp_path: Path) -> None:
    class APQ:
        http = client()

    with pytest.raises(SourcePolicyBlocked, match="PRODUCTION_APPROVAL_REQUIRED"):
        run_production_index(
            ["2021-03"], APQ(), tmp_path, run_mode="observed-dev", production_approved=False,
        )


def test_production_plan_exposes_all_required_controls() -> None:
    plan = production_index_plan(["2021-03"])
    assert plan["productionApprovalRequired"] is True
    assert {key for key in plan if key.isupper()} == {
        "MAX_CONCURRENCY",
        "REQUESTS_PER_SECOND",
        "MAX_RETRIES",
        "BACKOFF_POLICY",
        "MIN_SUCCESS_RATE",
        "MAX_CONSECUTIVE_403",
        "MAX_CONSECUTIVE_429",
        "MAX_EMPTY_PAGE_STREAK",
        "CHECKPOINT_INTERVAL",
    }
