from __future__ import annotations

import math

import pandas as pd

from p4.common.keys import make_metric_id


DIMENSIONS = ["periodMonth", "cohortType", "jobCodeLevel", "jobCode"]


def _safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _posting_flags(group: pd.DataFrame, posting_key: str) -> pd.DataFrame:
    def summarize(posting: pd.DataFrame) -> pd.Series:
        types = set(posting["trackType"].dropna())
        entry = bool(types.intersection({"entry", "entryInternMixed", "entryExperiencedMixed", "allMixed"}))
        intern = bool(types.intersection({"intern", "entryInternMixed", "internExperiencedMixed", "allMixed"}))
        experienced = bool(types.intersection({"experienced", "entryExperiencedMixed", "internExperiencedMixed", "allMixed"}))
        unresolved_mixed = "mixedUnresolved" in types
        return pd.Series(
            {
                "entry": entry,
                "intern": intern,
                "experienced": experienced,
                "mixed": unresolved_mixed or sum((entry, intern, experienced)) > 1,
            }
        )

    return group.groupby(posting_key, dropna=False).apply(summarize, include_groups=False)


def _metrics(group: pd.DataFrame, dedup_applied: bool, low_confidence_threshold: float) -> dict[str, object]:
    base_eligible = group.loc[group["postingEligibleFlag"].astype(bool)].copy()
    if dedup_applied:
        base_eligible = base_eligible.loc[base_eligible["canonicalRecordFlag"].astype(bool)]
        posting_key = "canonicalPostingId"
    else:
        posting_key = "postingId"
    rq1_eligible = base_eligible.loc[base_eligible["rq1EligibleFlag"].astype(bool)].copy()
    flags = _posting_flags(rq1_eligible, posting_key) if len(rq1_eligible) else pd.DataFrame(
        columns=["entry", "intern", "experienced", "mixed"]
    )
    total = len(flags)
    entry_count = int(flags["entry"].sum()) if total else 0
    intern_count = int(flags["intern"].sum()) if total else 0
    entry_only = int((flags["entry"] & ~flags["intern"] & ~flags["experienced"] & ~flags["mixed"]).sum()) if total else 0
    intern_only = int((flags["intern"] & ~flags["entry"] & ~flags["experienced"] & ~flags["mixed"]).sum()) if total else 0
    mixed = int(flags["mixed"].sum()) if total else 0
    experienced_only = int((flags["experienced"] & ~flags["entry"] & ~flags["intern"] & ~flags["mixed"]).sum()) if total else 0

    rq2_tracks = base_eligible.loc[base_eligible["rq2EligibleFlag"].astype(bool)]
    ncs_tracks = base_eligible.loc[base_eligible["ncsEligibleFlag"].astype(bool)]
    entry_labels = rq2_tracks.loc[rq2_tracks["careerClass"].isin(["E0", "E1"]), "careerClass"]
    intern_labels = rq2_tracks.loc[rq2_tracks["internAccessClass"].isin(["I0", "I1"])]
    mapped = ncs_tracks["ncsLevel"].notna()
    advanced = ncs_tracks["ncsLevel"].between(5, 8, inclusive="both")
    low_confidence = mapped & (ncs_tracks["ncsMatchScore"] < low_confidence_threshold)

    base_posting_count = base_eligible[posting_key].nunique()
    rq1_posting_count = rq1_eligible[posting_key].nunique()
    external_posting_count = base_eligible.loc[base_eligible["externalDetailOnlyFlag"].astype(bool), posting_key].nunique()
    activity_text_count = base_eligible.loc[base_eligible["activityTextAvailableFlag"].astype(bool), posting_key].nunique()

    return {
        "totalValidPostingCount": total,
        "entryPostingCount": entry_count,
        "internPostingCount": intern_count,
        "entryPostingRate": _safe_rate(entry_count, total),
        "internPostingRate": _safe_rate(intern_count, total),
        "entryOnlyRate": _safe_rate(entry_only, total),
        "internOnlyRate": _safe_rate(intern_only, total),
        "mixedRate": _safe_rate(mixed, total),
        "experiencedOnlyRate": _safe_rate(experienced_only, total),
        "internRelativeIndex": _safe_rate(_safe_rate(intern_count, total) or 0, _safe_rate(entry_count, total) or 0),
        "openEntryShare": _safe_rate(int((entry_labels == "E0").sum()), len(entry_labels)),
        "restrictedEntryShare": _safe_rate(int((entry_labels == "E1").sum()), len(entry_labels)),
        "restrictedInternShare": _safe_rate(int((intern_labels["internAccessClass"] == "I1").sum()), len(intern_labels)),
        "experiencedInternShare": _safe_rate(int(intern_labels["experiencedInternFlag"].fillna(False).sum()), len(intern_labels)),
        "advancedDutyShare": _safe_rate(int(advanced.sum()), int(mapped.sum())),
        "ncsMappingCoverage": _safe_rate(int(mapped.sum()), len(ncs_tracks)),
        "lowConfidenceNcsShare": _safe_rate(int(low_confidence.sum()), int(mapped.sum())),
        "rq1EligibilityRate": _safe_rate(rq1_posting_count, base_posting_count),
        "rq2EligibilityRate": _safe_rate(rq2_tracks["trackId"].nunique(), base_eligible["trackId"].nunique()),
        "ncsEligibilityRate": _safe_rate(ncs_tracks["trackId"].nunique(), base_eligible["trackId"].nunique()),
        "externalAtsOnlyShare": _safe_rate(external_posting_count, base_posting_count),
        "activityTextAvailabilityRate": _safe_rate(activity_text_count, base_posting_count),
    }


def build_time_series_mart(posting_mart: pd.DataFrame, low_confidence_threshold: float = 0.70) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, group in posting_mart.groupby(DIMENSIONS, dropna=False, sort=True):
        dimensions = dict(zip(DIMENSIONS, keys))
        for dedup_applied in (False, True):
            row = {**dimensions, "dedupApplied": dedup_applied}
            row.update(_metrics(group, dedup_applied, low_confidence_threshold))
            row["metricId"] = make_metric_id(
                row["periodMonth"],
                row["cohortType"],
                row["jobCodeLevel"],
                row["jobCode"],
                dedup_applied,
            )
            rows.append(row)
    columns = ["metricId", *DIMENSIONS, "dedupApplied"] + list(
        _metrics(posting_mart.iloc[0:0], False, low_confidence_threshold).keys()
    )
    result = pd.DataFrame(rows, columns=columns)
    if result["metricId"].duplicated().any():
        raise ValueError("timeSeriesMart grain violation: duplicate metricId")
    return result
