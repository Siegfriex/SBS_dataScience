from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from p4_ncs.temporal import (
    assign_temporal_split,
    audit_temporal_leakage,
    expected_calibration_error,
    fit_platt_scaling,
    risk_coverage_curve,
    selective_decision,
)

PROJECT = Path(__file__).resolve().parents[2]
SCHEMA = PROJECT / "shared/contracts/semantic_ncs_reference/v4.0/schemas/calibration_model.schema.json"


def test_frozen_temporal_windows() -> None:
    assert assign_temporal_split("2020-01").split == "DEVELOPMENT"
    assert assign_temporal_split("2024-12").split == "DEVELOPMENT"
    assert assign_temporal_split("2025-06").split == "VALIDATION"
    assert assign_temporal_split("2026-07").split == "AUDIT"
    assert assign_temporal_split("2019-12").split == "OUT_OF_WINDOW"


def test_temporal_leakage_fails_closed() -> None:
    rows = pd.DataFrame(
        {"periodMonth": ["2024-12", "2025-01"], "postingId": ["P1", "P1"], "companyKey": ["C1", "C2"]}
    )
    result = audit_temporal_leakage(rows)
    assert result["status"] == "FAIL"
    assert result["violations"] == [{"groupingColumn": "postingId", "groupId": "P1", "splits": ["DEVELOPMENT", "VALIDATION"]}]


def test_temporal_audit_not_evaluated_without_dates() -> None:
    result = audit_temporal_leakage(pd.DataFrame({"postingId": ["P1"]}))
    assert result["status"] == "NOT_EVALUATED"
    assert result["reason"] == "NO_OBSERVED_PERIOD_MONTH"


def test_platt_fit_is_validation_only_and_schema_valid() -> None:
    scores = [-2.0, -1.0, -0.25, 0.25, 1.0, 2.0]
    labels = [0, 0, 0, 1, 1, 1]
    periods = ["2025-01", "2025-02", "2025-03", "2025-09", "2025-10", "2025-12"]
    result = fit_platt_scaling(
        scores,
        labels,
        periods,
        input_model_version="synthetic-v1",
        reference_release_sha256="a" * 64,
    )
    assert result.status == "PASS"
    assert result.probabilities == tuple(sorted(result.probabilities))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(result.model_record, schema)


def test_calibration_rejects_audit_for_tuning() -> None:
    with pytest.raises(ValueError, match="VALIDATION"):
        fit_platt_scaling([0.0, 1.0], [0, 1], ["2025-01", "2026-01"], input_model_version="m", reference_release_sha256="b" * 64)


def test_calibration_is_not_evaluated_for_empty_or_one_class() -> None:
    empty = fit_platt_scaling([], [], [], input_model_version="m", reference_release_sha256="c" * 64)
    one_class = fit_platt_scaling([0.1, 0.2], [1, 1], ["2025-01", "2025-02"], input_model_version="m", reference_release_sha256="c" * 64)
    assert empty.status == "NOT_EVALUATED"
    assert one_class.reason == "VALIDATION_LABELS_HAVE_ONE_CLASS"


def test_selective_prediction_uses_probability_and_margin() -> None:
    accepted = selective_decision("02010101", 0.85, 0.60, probability_threshold=0.7, margin_threshold=0.15)
    low_margin = selective_decision("02010101", 0.85, 0.80, probability_threshold=0.7, margin_threshold=0.15)
    assert accepted["decision"] == "SELECT_CANDIDATE"
    assert low_margin["decision"] == "ABSTAIN"
    assert low_margin["selectedCode"] is None


def test_metrics_and_risk_coverage_are_bounded() -> None:
    ece = expected_calibration_error([0, 0, 1, 1], [0.1, 0.3, 0.7, 0.9], bins=2)
    curve = risk_coverage_curve([0, 1, 1, 0], [0.2, 0.9, 0.8, 0.6], [0.0, 0.7, 1.0])
    assert 0.0 <= ece <= 1.0
    assert [row["coverage"] for row in curve] == [1.0, 0.5, 0.0]
    assert curve[-1]["risk"] is None
