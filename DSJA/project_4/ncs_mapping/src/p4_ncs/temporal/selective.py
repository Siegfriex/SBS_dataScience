"""Selective prediction and risk-coverage summaries."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def selective_decision(
    top1_code: str,
    p_top1: float,
    p_top2: float,
    *,
    probability_threshold: float,
    margin_threshold: float,
) -> dict[str, Any]:
    values = (p_top1, p_top2, probability_threshold, margin_threshold)
    if not all(0.0 <= float(value) <= 1.0 for value in values):
        raise ValueError("probabilities and thresholds must be in [0, 1]")
    if p_top2 > p_top1:
        raise ValueError("p_top1 must not be less than p_top2")
    margin = float(p_top1 - p_top2)
    accepted = p_top1 >= probability_threshold and margin >= margin_threshold
    return {
        "decision": "SELECT_CANDIDATE" if accepted else "ABSTAIN",
        "selectedCode": top1_code if accepted else None,
        "pTop1": float(p_top1),
        "margin": margin,
        "accepted": accepted,
    }


def risk_coverage_curve(
    labels: Sequence[int], probabilities: Sequence[float], thresholds: Sequence[float]
) -> list[dict[str, Any]]:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be equally sized and non-empty")
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if not set(y.tolist()).issubset({0, 1}) or not ((p >= 0.0) & (p <= 1.0)).all():
        raise ValueError("invalid binary labels or probabilities")
    rows: list[dict[str, Any]] = []
    for threshold in sorted(set(float(value) for value in thresholds)):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("thresholds must be in [0, 1]")
        accepted = p >= threshold
        accepted_count = int(accepted.sum())
        risk = None if accepted_count == 0 else float(np.mean(y[accepted] == 0))
        rows.append(
            {
                "threshold": threshold,
                "coverage": accepted_count / len(y),
                "risk": risk,
                "acceptedCount": accepted_count,
                "totalCount": int(len(y)),
            }
        )
    return rows
