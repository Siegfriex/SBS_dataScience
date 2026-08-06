import pandas as pd
import pytest

from p4.marts.posting import build_posting_analysis_mart, validate_posting_analysis_mart
from p4.marts.time_series import build_time_series_mart


def lineage():
    return {
        "contractVersion": "UNCONTRACTED",
        "crawlReleaseId": "NONE",
        "dataVersion": "fixture-v2",
        "parseVersion": "parse-v2",
        "labelVersion": "label-v2",
        "ncsMapVersion": "ncs-v2",
        "dedupVersion": "dedup-v2",
    }


def fixture_frames():
    base = {
        "periodMonth": pd.Timestamp("2026-01-01").date(),
        "postingEligibleFlag": True,
        "rq1EligibleFlag": True,
        "rq2EligibleFlag": True,
        "ncsEligibleFlag": True,
        "activityTextAvailableFlag": True,
        "externalDetailOnlyFlag": False,
        "jobTypeConflictFlag": False,
        "rq2ExclusionReason": None,
        "rq2ExclusionReasonsJson": "[]",
    }
    postings = pd.DataFrame(
        [
            {**base, "postingId": "P1", "canonicalPostingId": "P1", "canonicalRecordFlag": True, "externalApplyFlag": True},
            {**base, "postingId": "P2", "canonicalPostingId": "P1", "canonicalRecordFlag": False, "externalApplyFlag": True},
            {**base, "postingId": "P3", "canonicalPostingId": "P3", "canonicalRecordFlag": True, "externalApplyFlag": False},
        ]
    )
    tracks = pd.DataFrame(
        [
            {"trackId": "T1", "postingId": "P1", "trackType": "intern", "jobCodeLevel": "ncsSub", "jobCode": "2001"},
            {"trackId": "T2", "postingId": "P2", "trackType": "intern", "jobCodeLevel": "ncsSub", "jobCode": "2001"},
            {"trackId": "T3", "postingId": "P3", "trackType": "entry", "jobCodeLevel": "ncsSub", "jobCode": "2001"},
        ]
    )
    labels = pd.DataFrame(
        [
            {"trackId": "T1", "careerClass": "U", "internAccessClass": "I1", "restrictedInternFlag": True, "experiencedInternFlag": True, "boundaryResolvedFlag": True},
            {"trackId": "T2", "careerClass": "U", "internAccessClass": "I0", "restrictedInternFlag": False, "experiencedInternFlag": False, "boundaryResolvedFlag": True},
            {"trackId": "T3", "careerClass": "E0", "internAccessClass": None, "restrictedInternFlag": None, "experiencedInternFlag": None, "boundaryResolvedFlag": True},
        ]
    )
    matches = pd.DataFrame(
        [
            {"trackId": "T1", "sectionId": "S1", "ncsUnitCode": "U1", "matchScore": 0.8, "matchRank": 1, "selectedFlag": True},
            {"trackId": "T3", "sectionId": "S3", "ncsUnitCode": "U1", "matchScore": 0.6, "matchRank": 1, "selectedFlag": True},
        ]
    )
    units = pd.DataFrame([{"ncsUnitCode": "U1", "ncsLevel": 5, "ncsBand": "level5to6"}])
    return postings, tracks, labels, matches, units


def test_posting_mart_grain_reserved_score_and_lineage():
    mart = build_posting_analysis_mart(*fixture_frames(), lineage=lineage())
    check = validate_posting_analysis_mart(mart)
    assert check["passed"] is True
    assert len(mart) == 3
    assert mart["highDemandScore"].isna().all()
    assert set(mart["contractVersion"]) == {"UNCONTRACTED"}
    assert set(mart["crawlReleaseId"]) == {"NONE"}


def test_posting_mart_requires_complete_lineage():
    with pytest.raises(ValueError, match="lineage fields"):
        build_posting_analysis_mart(*fixture_frames())


def test_time_series_dedup_branches_from_same_eligible_base():
    mart = build_posting_analysis_mart(*fixture_frames(), lineage=lineage())
    result = build_time_series_mart(mart).set_index("dedupApplied")
    assert result.loc[False, "totalValidPostingCount"] == 3
    assert result.loc[True, "totalValidPostingCount"] == 2


def test_experienced_intern_denominator_and_coverage_metrics():
    mart = build_posting_analysis_mart(*fixture_frames(), lineage=lineage())
    result = build_time_series_mart(mart).set_index("dedupApplied")
    assert result.loc[False, "experiencedInternShare"] == 0.5
    assert result.loc[False, "restrictedInternShare"] == 0.5
    assert result.loc[False, "ncsMappingCoverage"] == 2 / 3
    assert result.loc[False, "rq1EligibilityRate"] == 1.0
    assert result.loc[False, "rq2EligibilityRate"] == 1.0
    assert result.loc[False, "activityTextAvailabilityRate"] == 1.0
    assert result.loc[False, "externalApplyShare"] == 2 / 3
    assert result.loc[False, "externalDetailOnlyShare"] == 0.0
    assert result.loc[False, "jobTypeConflictRate"] == 0.0

