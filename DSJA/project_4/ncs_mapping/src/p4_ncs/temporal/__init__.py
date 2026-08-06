"""Temporal split, calibration, and selective-prediction controls."""

from .calibration import PlattCalibrationResult, expected_calibration_error, fit_platt_scaling
from .selective import risk_coverage_curve, selective_decision
from .split import TemporalSplit, assign_temporal_split, audit_temporal_leakage

__all__ = [
    "PlattCalibrationResult",
    "TemporalSplit",
    "assign_temporal_split",
    "audit_temporal_leakage",
    "expected_calibration_error",
    "fit_platt_scaling",
    "risk_coverage_curve",
    "selective_decision",
]
