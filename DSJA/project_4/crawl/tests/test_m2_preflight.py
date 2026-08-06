from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from p4_crawl.m2_preflight import (
    M2PolicyConfig,
    ProductionHealthMonitor,
    build_month_plan,
    checkpoint_envelope,
    load_checkpoint,
    require_approval,
    validate_approval,
    validate_query_registry,
)
from p4_crawl.policy import SourcePolicyBlocked


CRAWL_ROOT = Path(__file__).resolve().parents[1]


def valid_approval() -> dict:
    return {
        "productionApprovalId": "USER-SIGNED-ID",
        "approvedBy": "user",
        "approvedAt": "2026-08-06T00:00:00Z",
        "approvedPeriod": "2020-01~2026-07",
        "approvedSource": "Linkareer",
        "externalAtsTransportAllowed": False,
        "linkareerHostedAssetAllowed": True,
        "rateLimitPolicyVersion": "p4-linkareer-production-rate-v1",
        "killSwitchPolicyVersion": "p4-linkareer-kill-switch-v1",
    }


def test_month_plan_is_exactly_79_months() -> None:
    frame = build_month_plan(CRAWL_ROOT / "releases/CRAWL_20260806_03/monthly_coverage.csv")
    assert len(frame) == 79
    assert frame.iloc[0]["periodMonth"] == "2020-01"
    assert frame.iloc[-1]["periodMonth"] == "2026-07"
    assert set(frame["activityTypeID"]) == {5}


def test_missing_approval_blocks_before_transport() -> None:
    with pytest.raises(SourcePolicyBlocked, match="PRODUCTION_APPROVAL_REQUIRED"):
        require_approval(None)


def test_approval_contract_accepts_only_expected_scope() -> None:
    assert validate_approval(valid_approval()) == []
    wrong = valid_approval()
    wrong["externalAtsTransportAllowed"] = True
    assert "externalAtsTransportAllowed:must-be-false" in validate_approval(wrong)


def test_policy_freeze_rejects_excess_concurrency() -> None:
    with pytest.raises(ValueError, match="MAX_CONCURRENCY"):
        M2PolicyConfig(max_concurrency=3)


def test_403_trips_immediately() -> None:
    monitor = ProductionHealthMonitor()
    with pytest.raises(SourcePolicyBlocked, match="MAX_CONSECUTIVE_403"):
        monitor.observe_response(403)


def test_429_threshold_trips() -> None:
    monitor = ProductionHealthMonitor(M2PolicyConfig(minimum_success_samples=20))
    monitor.observe_response(429)
    monitor.observe_response(429)
    with pytest.raises(SourcePolicyBlocked, match="MAX_CONSECUTIVE_429"):
        monitor.observe_response(429)


def test_success_rate_threshold_trips() -> None:
    monitor = ProductionHealthMonitor(M2PolicyConfig(minimum_success_samples=5))
    for code in (200, 500, 500, 500):
        monitor.observe_response(code)
    with pytest.raises(SourcePolicyBlocked, match="MIN_SUCCESS_RATE"):
        monitor.observe_response(500)


def test_unexpected_content_type_trips() -> None:
    monitor = ProductionHealthMonitor()
    with pytest.raises(SourcePolicyBlocked, match="UNEXPECTED_CONTENT_TYPE"):
        monitor.observe_response(200, "text/html")


def test_empty_page_streak_trips() -> None:
    monitor = ProductionHealthMonitor()
    monitor.observe_page(empty=True)
    with pytest.raises(SourcePolicyBlocked, match="MAX_EMPTY_PAGE_STREAK"):
        monitor.observe_page(empty=True)


def test_schema_drift_trips() -> None:
    monitor = ProductionHealthMonitor()
    with pytest.raises(SourcePolicyBlocked, match="SCHEMA_DRIFT"):
        monitor.schema_drift("missing nodes")


def test_checkpoint_round_trip_and_corruption(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    envelope = checkpoint_envelope({"completedPeriods": ["2020-01"]})
    path.write_text(json.dumps(envelope), encoding="utf-8")
    assert load_checkpoint(path) == {"completedPeriods": ["2020-01"]}
    envelope["state"]["completedPeriods"].append("2020-02")
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(SourcePolicyBlocked, match="CHECKPOINT_CORRUPTION"):
        load_checkpoint(path)


def test_query_registry_is_frozen_without_unresolved_semantics() -> None:
    result = validate_query_registry(CRAWL_ROOT / "configs/queryRegistry.yaml")
    assert result["status"] == "PASS"
    assert result["queryCount"] == 2


def test_production_approval_schema_accepts_only_frozen_scope() -> None:
    schema = json.loads((CRAWL_ROOT / "control/PRODUCTION_APPROVAL.schema.json").read_text())
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(valid_approval())
    invalid = valid_approval()
    invalid["approvedPeriod"] = "2019-01~2026-07"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(invalid)


def test_preflight_modules_have_no_network_transport_import() -> None:
    forbidden = {"requests", "httpx", "curl_cffi", "urllib.request", "aiohttp"}
    for path in (CRAWL_ROOT / "src/p4_crawl/m2_preflight.py", CRAWL_ROOT / "scripts/build_m2_preflight.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not imports.intersection(forbidden)
