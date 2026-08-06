from __future__ import annotations

import pandas as pd


POSTING_MART_COLUMNS = [
    "trackId",
    "contractVersion",
    "crawlReleaseId",
    "dataVersion",
    "parseVersion",
    "labelVersion",
    "ncsMapVersion",
    "dedupVersion",
    "postingId",
    "canonicalPostingId",
    "periodMonth",
    "cohortType",
    "jobCodeLevel",
    "jobCode",
    "postingEligibleFlag",
    "rq1EligibleFlag",
    "rq2EligibleFlag",
    "ncsEligibleFlag",
    "canonicalRecordFlag",
    "activityTextAvailableFlag",
    "externalApplyFlag",
    "externalDetailOnlyFlag",
    "jobTypeConflictFlag",
    "rq2ExclusionReason",
    "rq2ExclusionReasonsJson",
    "trackType",
    "careerClass",
    "internAccessClass",
    "restrictedInternFlag",
    "experiencedInternFlag",
    "ncsLevel",
    "ncsBand",
    "ncsMatchScore",
    "highDemandScore",
]


def build_posting_analysis_mart(
    postings: pd.DataFrame,
    tracks: pd.DataFrame,
    labels: pd.DataFrame,
    matches: pd.DataFrame | None = None,
    ncs_units: pd.DataFrame | None = None,
    cohort_type: str = "coreAiIt",
    lineage: dict[str, str] | None = None,
) -> pd.DataFrame:
    required_lineage = {
        "contractVersion",
        "crawlReleaseId",
        "dataVersion",
        "parseVersion",
        "labelVersion",
        "ncsMapVersion",
        "dedupVersion",
    }
    if lineage is None or any(not lineage.get(field) for field in required_lineage):
        raise ValueError(f"posting mart requires lineage fields: {sorted(required_lineage)}")
    if tracks["trackId"].duplicated().any():
        raise ValueError("postingTrack grain violation: duplicate trackId")
    merged = tracks.merge(
        postings[
            [
                "postingId",
                "canonicalPostingId",
                "periodMonth",
                "postingEligibleFlag",
                "rq1EligibleFlag",
                "rq2EligibleFlag",
                "ncsEligibleFlag",
                "canonicalRecordFlag",
                "activityTextAvailableFlag",
                "externalApplyFlag",
                "externalDetailOnlyFlag",
                "jobTypeConflictFlag",
                "rq2ExclusionReason",
                "rq2ExclusionReasonsJson",
            ]
        ],
        on="postingId",
        how="left",
        validate="many_to_one",
    ).merge(labels, on="trackId", how="left", validate="one_to_one")

    if matches is not None and len(matches):
        selected = matches.loc[matches["selectedFlag"]].copy()
        if selected["sectionId"].duplicated().any():
            raise ValueError("more than one selected NCS match per section")
        if "trackId" not in selected.columns:
            raise ValueError("selected matches must carry trackId for mart construction")
        selected = selected.sort_values(["trackId", "matchRank"]).drop_duplicates("trackId")
        merged = merged.merge(
            selected[["trackId", "ncsUnitCode", "matchScore"]],
            on="trackId",
            how="left",
            validate="one_to_one",
        )
        if ncs_units is not None and len(ncs_units):
            merged = merged.merge(
                ncs_units[["ncsUnitCode", "ncsLevel", "ncsBand"]],
                on="ncsUnitCode",
                how="left",
                validate="many_to_one",
            )
        else:
            merged["ncsLevel"] = pd.NA
            merged["ncsBand"] = pd.NA
        merged = merged.rename(columns={"matchScore": "ncsMatchScore"})
    else:
        merged["ncsLevel"] = pd.NA
        merged["ncsBand"] = pd.NA
        merged["ncsMatchScore"] = pd.NA

    merged["cohortType"] = cohort_type
    for field in required_lineage:
        merged[field] = lineage[field]
    merged["jobCodeLevel"] = merged["jobCodeLevel"].fillna("unknown")
    merged["jobCode"] = merged["jobCode"].fillna("unknown")
    merged["highDemandScore"] = pd.NA
    if merged["trackId"].duplicated().any():
        raise ValueError("postingAnalysisMart grain violation: duplicate trackId")
    return merged[POSTING_MART_COLUMNS].sort_values("trackId").reset_index(drop=True)


def validate_posting_analysis_mart(frame: pd.DataFrame) -> dict[str, object]:
    missing = [column for column in POSTING_MART_COLUMNS if column not in frame.columns]
    duplicate_count = int(frame["trackId"].duplicated().sum()) if "trackId" in frame else None
    high_demand_non_null = int(frame["highDemandScore"].notna().sum()) if "highDemandScore" in frame else None
    passed = not missing and duplicate_count == 0 and high_demand_non_null == 0
    return {
        "passed": passed,
        "missingColumns": missing,
        "primaryKeyDuplicates": duplicate_count,
        "highDemandNonNullCount": high_demand_non_null,
    }
