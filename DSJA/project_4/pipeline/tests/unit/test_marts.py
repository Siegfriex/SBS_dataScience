import pandas as pd

from p4.marts.posting import build_posting_analysis_mart, validate_posting_analysis_mart
from p4.marts.time_series import build_time_series_mart


def fixture_frames():
    postings = pd.DataFrame(
        [
            {"postingId": "P1", "canonicalPostingId": "P1", "periodMonth": pd.Timestamp("2026-01-01").date(), "postingEligibleFlag": True, "rq1EligibleFlag": True, "rq2EligibleFlag": True, "ncsEligibleFlag": True, "canonicalRecordFlag": True, "activityTextAvailableFlag": True, "externalDetailOnlyFlag": False, "jobTypeConflictFlag": False, "rq2ExclusionReason": None},
            {"postingId": "P2", "canonicalPostingId": "P1", "periodMonth": pd.Timestamp("2026-01-01").date(), "postingEligibleFlag": True, "rq1EligibleFlag": True, "rq2EligibleFlag": True, "ncsEligibleFlag": True, "canonicalRecordFlag": False, "activityTextAvailableFlag": True, "externalDetailOnlyFlag": False, "jobTypeConflictFlag": False, "rq2ExclusionReason": None},
            {"postingId": "P3", "canonicalPostingId": "P3", "periodMonth": pd.Timestamp("2026-01-01").date(), "postingEligibleFlag": True, "rq1EligibleFlag": True, "rq2EligibleFlag": True, "ncsEligibleFlag": True, "canonicalRecordFlag": True, "activityTextAvailableFlag": True, "externalDetailOnlyFlag": False, "jobTypeConflictFlag": False, "rq2ExclusionReason": None},
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


def test_posting_mart_grain_and_reserved_score():
    mart = build_posting_analysis_mart(*fixture_frames())
    check = validate_posting_analysis_mart(mart)
    assert check["passed"] is True
    assert len(mart) == 3
    assert mart["highDemandScore"].isna().all()


def test_time_series_dedup_branches_from_same_eligible_base():
    mart = build_posting_analysis_mart(*fixture_frames())
    result = build_time_series_mart(mart).set_index("dedupApplied")
    assert result.loc[False, "totalValidPostingCount"] == 3
    assert result.loc[True, "totalValidPostingCount"] == 2


def test_experienced_intern_denominator_is_all_resolved_interns_not_ncs_mapped():
    mart = build_posting_analysis_mart(*fixture_frames())
    result = build_time_series_mart(mart).set_index("dedupApplied")
    assert result.loc[False, "experiencedInternShare"] == 0.5
    assert result.loc[False, "restrictedInternShare"] == 0.5
    assert result.loc[False, "ncsMappingCoverage"] == 2 / 3
    assert result.loc[False, "rq1EligibilityRate"] == 1.0
    assert result.loc[False, "rq2EligibilityRate"] == 1.0
    assert result.loc[False, "activityTextAvailabilityRate"] == 1.0
