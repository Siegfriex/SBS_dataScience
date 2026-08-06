"""Deterministic offline Platt scaling for the frozen validation window."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .split import assign_temporal_split


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def expected_calibration_error(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> float:
    y = np.asarray(labels, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if len(y) == 0 or len(y) != len(p):
        raise ValueError("labels and probabilities must be equally sized and non-empty")
    if bins < 1:
        raise ValueError("bins must be positive")
    total = len(y)
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (p >= lower) & ((p < upper) if index < bins - 1 else (p <= upper))
        if mask.any():
            ece += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return ece


@dataclass(frozen=True)
class PlattCalibrationResult:
    status: str
    reason: str | None
    coefficient: float | None
    intercept: float | None
    probabilities: tuple[float, ...]
    model_record: dict[str, Any] | None

    def predict(self, scores: Sequence[float]) -> tuple[float, ...]:
        if self.status != "PASS" or self.coefficient is None or self.intercept is None:
            raise RuntimeError("calibration model is not fitted")
        values = _sigmoid(self.coefficient * np.asarray(scores, dtype=float) + self.intercept)
        return tuple(float(value) for value in values)


def _not_evaluated(reason: str) -> PlattCalibrationResult:
    return PlattCalibrationResult("NOT_EVALUATED", reason, None, None, (), None)


def fit_platt_scaling(
    scores: Sequence[float],
    labels: Sequence[int],
    period_months: Sequence[str],
    *,
    input_model_version: str,
    reference_release_sha256: str,
    probability_threshold: float = 0.7,
    margin_threshold: float = 0.15,
    calibration_version: str = "v4.0",
    max_iter: int = 200,
) -> PlattCalibrationResult:
    """Fit a two-parameter logistic calibrator using only 2025 validation data."""
    if not (len(scores) == len(labels) == len(period_months)):
        raise ValueError("scores, labels, and period_months must have equal length")
    if not scores:
        return _not_evaluated("NO_VALIDATION_OBSERVATIONS")
    splits = [assign_temporal_split(month).split for month in period_months]
    if any(split != "VALIDATION" for split in splits):
        raise ValueError("calibration fit is restricted to the 2025 VALIDATION split")
    y = np.asarray(labels, dtype=float)
    x = np.asarray(scores, dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("scores and labels must be finite")
    if not set(y.tolist()).issubset({0.0, 1.0}):
        raise ValueError("labels must be binary")
    if len(set(y.tolist())) < 2:
        return _not_evaluated("VALIDATION_LABELS_HAVE_ONE_CLASS")
    if not (0.0 <= probability_threshold <= 1.0 and 0.0 <= margin_threshold <= 1.0):
        raise ValueError("selective-prediction thresholds must be in [0, 1]")

    # Newton updates for the unregularized binomial likelihood. The small ridge
    # stabilizes degenerate score ranges without changing the declared method.
    design = np.column_stack([x, np.ones(len(x))])
    params = np.zeros(2, dtype=float)
    ridge = 1e-8
    for _ in range(max_iter):
        probabilities = _sigmoid(design @ params)
        weights = np.maximum(probabilities * (1.0 - probabilities), 1e-9)
        gradient = design.T @ (probabilities - y) + ridge * params
        hessian = design.T @ (design * weights[:, None]) + ridge * np.eye(2)
        step = np.linalg.solve(hessian, gradient)
        params -= step
        if float(np.max(np.abs(step))) < 1e-10:
            break

    probabilities = _sigmoid(design @ params)
    coefficient, intercept = (float(params[0]), float(params[1]))
    brier = float(np.mean((probabilities - y) ** 2))
    ece = expected_calibration_error(y.astype(int), probabilities)
    parameter_payload = {"coefficient": coefficient, "intercept": intercept}
    artifact_bytes = json.dumps(parameter_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    period_start, period_end = min(period_months), max(period_months)
    model_id = hashlib.sha256(
        json.dumps({"version": calibration_version, "input": input_model_version, "sha": artifact_sha}, sort_keys=True).encode()
    ).hexdigest()[:20]
    record = {
        "calibrationModelId": f"CAL_{model_id}",
        "calibrationVersion": calibration_version,
        "method": "PLATT_SCALING",
        "inputModelVersion": input_model_version,
        "fitSplit": "VALIDATION",
        "fitPeriodStart": period_start,
        "fitPeriodEnd": period_end,
        "probabilityThreshold": probability_threshold,
        "marginThreshold": margin_threshold,
        "parametersJson": parameter_payload,
        "brierScore": brier,
        "ece": ece,
        "riskCoverageArtifactSha256": None,
        "referenceReleaseSha256": reference_release_sha256,
        "modelArtifactSha256": artifact_sha,
        "status": "PASS",
    }
    return PlattCalibrationResult(
        "PASS", None, coefficient, intercept, tuple(float(value) for value in probabilities), record
    )
