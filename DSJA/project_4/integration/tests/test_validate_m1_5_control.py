from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml


INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTEGRATION_ROOT.parent
sys.path.insert(0, str(INTEGRATION_ROOT))

from validate_m1_5_control import (  # noqa: E402
    ControlValidationError,
    evaluate_gate_status,
    validate_control_root,
    validate_dependency_graph,
    validate_stage_registry,
)


def _stage_payload() -> dict:
    return yaml.safe_load((INTEGRATION_ROOT / "SEMANTIC_STAGE_REGISTRY.yaml").read_text(encoding="utf-8"))


def test_repository_control_plane_passes() -> None:
    result = validate_control_root(PROJECT_ROOT)
    assert result["status"] == "PASS"
    assert result["results"]["schemas"]["schemaCount"] == 12
    assert result["results"]["stageRegistry"]["stageCount"] == 6
    assert result["results"]["stageRegistry"]["gateCount"] == 26
    assert result["results"]["gateMatrix"]["gateRowCount"] == 26


def test_status_vocabulary_is_exact_and_fail_closed() -> None:
    payload = _stage_payload()
    payload["statusVocabulary"].append("READY")
    with pytest.raises(ControlValidationError, match="status vocabulary"):
        validate_stage_registry(payload)


def test_unknown_dependency_is_validation_failure() -> None:
    payload = _stage_payload()
    payload["stages"][-1]["dependencies"].append("M1.5-X")
    with pytest.raises(ControlValidationError, match="unknown dependency"):
        validate_stage_registry(payload)


def test_dependency_cycle_is_validation_failure() -> None:
    payload = _stage_payload()
    payload["stages"][0]["dependencies"] = ["M1.5-D"]
    with pytest.raises(ControlValidationError, match="dependency cycle"):
        validate_stage_registry(payload)


def test_dependency_graph_must_match_registry() -> None:
    stage_payload = _stage_payload()
    graph = yaml.safe_load((INTEGRATION_ROOT / "STAGE_DEPENDENCY_GRAPH.yaml").read_text(encoding="utf-8"))
    broken = copy.deepcopy(graph)
    broken["edges"].pop()
    with pytest.raises(ControlValidationError, match="edges do not match"):
        validate_dependency_graph(broken, stage_payload)


def test_empty_evidence_is_not_evaluated() -> None:
    assert evaluate_gate_status("PASS", 0, {}, ()) == "NOT_EVALUATED"


def test_unmet_dependency_is_blocked() -> None:
    assert evaluate_gate_status("PASS", 1, {"M1.5-0": "PARTIAL"}, ("M1.5-0",)) == "BLOCKED"


def test_unknown_or_invalid_dependency_is_fail() -> None:
    assert evaluate_gate_status("PASS", 1, {}, ("M1.5-0",)) == "FAIL"
    assert evaluate_gate_status("PASS", 1, {"M1.5-0": "READY"}, ("M1.5-0",)) == "FAIL"


def test_validation_error_has_highest_precedence() -> None:
    assert evaluate_gate_status("PASS", 0, {"M1.5-0": "BLOCKED"}, ("M1.5-0",), ("schema drift",)) == "FAIL"


def test_passing_dependency_and_evidence_preserve_allowed_status() -> None:
    assert evaluate_gate_status("PASS_WITH_FINDINGS", 1, {"M1.5-0": "PASS"}, ("M1.5-0",)) == "PASS_WITH_FINDINGS"
