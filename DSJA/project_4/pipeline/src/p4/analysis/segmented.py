from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class AnalysisSpec:
    outcome: str
    intervention_date: str = "2023-01-01"
    hac_max_lags: int = 12


def require_crawl_release_provenance(data_provenance: str) -> None:
    if data_provenance != "crawl_release":
        raise ValueError("empirical analysis requires immutable crawl_release provenance")


def prepare_segmented_design(frame: pd.DataFrame, intervention_date: str = "2023-01-01") -> pd.DataFrame:
    if "periodMonth" not in frame:
        raise ValueError("periodMonth is required")
    result = frame.copy()
    result["periodMonth"] = pd.to_datetime(result["periodMonth"])
    result = result.sort_values("periodMonth").reset_index(drop=True)
    first = result["periodMonth"].min()
    intervention = pd.Timestamp(intervention_date)
    result["Time"] = (
        (result["periodMonth"].dt.year - first.year) * 12
        + result["periodMonth"].dt.month
        - first.month
    ).astype(int)
    intervention_time = (intervention.year - first.year) * 12 + intervention.month - first.month
    result["Post2023"] = (result["periodMonth"] >= intervention).astype(int)
    result["TimeAfter2023"] = (result["Time"] - intervention_time).clip(lower=0)
    result["monthOfYear"] = result["periodMonth"].dt.month.astype(str)
    return result


def _design_matrix(frame: pd.DataFrame, include_job_fixed_effects: bool) -> pd.DataFrame:
    base = frame[["Time", "Post2023", "TimeAfter2023"]].astype(float)
    month = pd.get_dummies(frame["monthOfYear"], prefix="month", drop_first=True, dtype=float)
    pieces = [base, month]
    if include_job_fixed_effects:
        if "jobCode" not in frame:
            raise ValueError("jobCode is required for panel analysis")
        pieces.append(pd.get_dummies(frame["jobCode"], prefix="job", drop_first=True, dtype=float))
    return sm.add_constant(pd.concat(pieces, axis=1), has_constant="add")


def coefficient_table(model) -> pd.DataFrame:
    confidence = model.conf_int()
    return pd.DataFrame(
        {
            "term": model.params.index,
            "estimate": model.params.values,
            "stdError": model.bse.values,
            "pValue": model.pvalues.values,
            "ciLower": confidence.iloc[:, 0].values,
            "ciUpper": confidence.iloc[:, 1].values,
        }
    )


def fit_monthly_hac(frame: pd.DataFrame, spec: AnalysisSpec, data_provenance: str):
    require_crawl_release_provenance(data_provenance)
    prepared = prepare_segmented_design(frame, spec.intervention_date).dropna(subset=[spec.outcome])
    if prepared["periodMonth"].nunique() < 24:
        raise ValueError("monthly segmented regression requires at least 24 observed months")
    design = _design_matrix(prepared, include_job_fixed_effects=False)
    return sm.OLS(prepared[spec.outcome].astype(float), design).fit(
        cov_type="HAC", cov_kwds={"maxlags": spec.hac_max_lags}
    )


def fit_job_panel_clustered(frame: pd.DataFrame, spec: AnalysisSpec, data_provenance: str):
    require_crawl_release_provenance(data_provenance)
    prepared = prepare_segmented_design(frame, spec.intervention_date).dropna(subset=[spec.outcome, "jobCode"])
    if prepared["jobCode"].nunique() < 2:
        raise ValueError("clustered panel regression requires at least two jobCode groups")
    design = _design_matrix(prepared, include_job_fixed_effects=True)
    return sm.OLS(prepared[spec.outcome].astype(float), design).fit(
        cov_type="cluster", cov_kwds={"groups": prepared["jobCode"]}
    )

