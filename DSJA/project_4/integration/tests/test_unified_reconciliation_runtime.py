from __future__ import annotations

import copy
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_ROOT))

from unified_reconciliation_contract import (  # noqa: E402
    EXECUTION_ORDER,
    STAGE_DEPENDENCIES,
    ncs_binding_errors,
    validate_registry_dependencies,
    validate_topology_and_runtime,
)


def _runtime_manifests() -> dict[str, dict]:
    base = datetime(2026, 8, 7, 1, 0, tzinfo=UTC)
    result = {}
    for order, stage_id in enumerate(EXECUTION_ORDER):
        started = base + timedelta(seconds=order * 2)
        result[stage_id] = {
            "stageId": stage_id,
            "executionOrder": order,
            "dependencyStageIds": list(STAGE_DEPENDENCIES[stage_id]),
            "startedAtUtc": started.isoformat().replace("+00:00", "Z"),
            "completedAtUtc": (started + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            "executionHostOrRunnerId": "TEST_RUNNER",
            "executionCommandSha256": "1" * 64,
            "sourceNotebookSha256": "2" * 64,
            "moduleBlobSha256": "3" * 64,
            "inputManifestSha256": "4" * 64,
            "outputManifestSha256": "5" * 64,
            "timestampSource": "EXECUTION_WRAPPER_CAPTURED",
        }
    return result


def test_canonical_registry_dependencies_are_exact() -> None:
    registry = [
        {"stageId": stage_id, "dependencyStageIds": list(dependencies)}
        for stage_id, dependencies in STAGE_DEPENDENCIES.items()
    ]
    assert validate_registry_dependencies(registry) == []


def test_valid_runtime_topology_and_timestamps_pass() -> None:
    manifests = _runtime_manifests()
    assert validate_topology_and_runtime(manifests) == []
    assert ncs_binding_errors(manifests) == []


def test_producer_order_after_consumer_fails() -> None:
    manifests = _runtime_manifests()
    manifests["A4-00-NCS-SOURCE"]["executionOrder"] = 99
    errors = validate_topology_and_runtime(manifests)
    assert "TOPOLOGICAL_ORDER_VIOLATION:A4-00-NCS-SOURCE->A4-01-CODESET" in errors


def test_producer_completion_after_consumer_start_fails() -> None:
    manifests = _runtime_manifests()
    manifests["A4-04-EXPORT"]["completedAtUtc"] = manifests["A2-09-NCS-MAP"]["completedAtUtc"]
    errors = validate_topology_and_runtime(manifests)
    assert "RUNTIME_ORDER_VIOLATION:A4-04-EXPORT->A2-09-NCS-MAP" in errors


def test_fixed_timestamp_fails_closed() -> None:
    manifests = _runtime_manifests()
    manifests["A2-00-CONTRACT"]["startedAtUtc"] = "2026-08-06T00:00:00+09:00"
    manifests["A2-00-CONTRACT"]["completedAtUtc"] = "2026-08-06T00:00:00+09:00"
    assert "FIXED_TIMESTAMP:A2-00-CONTRACT" in validate_topology_and_runtime(manifests)


def test_missing_execution_metadata_fails_closed() -> None:
    manifests = _runtime_manifests()
    del manifests["A4-05-EVALUATE"]["executionCommandSha256"]
    assert "RUNTIME_FIELD_MISSING:A4-05-EVALUATE:executionCommandSha256" in validate_topology_and_runtime(manifests)


def test_ncs_consumer_requires_declared_producers() -> None:
    manifests = _runtime_manifests()
    broken = copy.deepcopy(manifests)
    broken["A2-08-NCS-LOAD"]["dependencyStageIds"] = ["A2-07-LABEL"]
    assert ncs_binding_errors(broken) == ["NCS_CONSUMER_PRODUCER_MISMATCH:A2-08-NCS-LOAD"]
