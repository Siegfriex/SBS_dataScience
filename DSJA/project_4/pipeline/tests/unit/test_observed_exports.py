from pathlib import Path

import pandas as pd

from p4.export.observed import build_export_frames, export_observed_frames, validate_export_bundle


def _frames() -> dict[str, pd.DataFrame]:
    sha = "a" * 64
    return {
        "posting_normalized": pd.DataFrame(
            [
                {
                    "postingId": "PST_1",
                    "rawPostingId": "RAW_1",
                    "sourcePostingId": "1",
                    "sourceUrl": "https://linkareer.com/activity/1",
                    "titleText": "데이터 인턴",
                    "companyName": "관측 기업",
                    "bodyText": "문의 test@example.com / SQL 분석",
                    "activityTypeId": 5,
                    "jobTypesRawJson": '["INTERN"]',
                    "resolvedJobTypesJson": '["intern"]',
                    "activityTextAvailableFlag": True,
                    "externalApplyFlag": False,
                    "externalDetailOnlyFlag": False,
                    "jobTypeConflictFlag": False,
                    "postingEligibleFlag": True,
                    "rq1EligibleFlag": True,
                    "rq2EligibleFlag": True,
                    "ncsEligibleFlag": True,
                    "eligibilitySource": "AGENT2_SSR_PARSE",
                    "inputSha256": sha,
                    "parseVersion": "observed-dev-parse-20260806.1",
                }
            ]
        ),
        "posting_track": pd.DataFrame(
            [{"trackId": "TRK_1", "postingId": "PST_1", "trackType": "intern", "trackOrdinal": 0, "mixedResolvedFlag": True, "jobCode": None, "inputSha256": sha}]
        ),
        "posting_section": pd.DataFrame(
            [{"sectionId": "SEC_1", "trackId": "TRK_1", "sectionType": "required", "sectionOrdinal": 0, "sectionText": "SQL 경험", "boundaryResolvedFlag": True, "sourceMode": "SSR_ACTIVITY_TEXT", "sectionConfidence": 1.0}]
        ),
        "requirement_fact": pd.DataFrame(
            [{"requirementId": "REQ_1", "sectionId": "SEC_1", "requirementType": "experience", "requirementText": "SQL 경험", "mandatoryFlag": True, "minExperienceMonths": 0, "priorExperienceFlag": False, "portfolioFlag": False}]
        ),
        "eligibility": pd.DataFrame(
            [{"trackId": "TRK_1", "postingId": "PST_1", "postingEligibleFlag": True, "rq1EligibleFlag": True, "rq2EligibleFlag": True, "ncsEligibleFlag": True, "eligibilitySource": "AGENT2_SSR_PARSE"}]
        ),
        "raw_posting": pd.DataFrame(),
        "ocr_queue": pd.DataFrame(),
    }


def test_observed_export_uses_canonical_eligibility_and_passes_semantic_qa(tmp_path: Path):
    frames = build_export_frames(_frames())
    final = frames["preprocessed_posting_tracks"]
    assert "postingEligibleFlag" in final
    assert "validPostingFlag" not in final
    assert final["highDemandScore"].isna().all()
    assert "test@example.com" not in frames["posting_normalized"].to_json(force_ascii=False)
    export_observed_frames(frames, tmp_path)
    quality, summary = validate_export_bundle(frames, tmp_path)
    assert summary["status"] == "PASS", quality.loc[quality["status"] == "FAIL"].to_dict(orient="records")
    assert (tmp_path / "preprocessed_posting_tracks.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_observed_export_materializes_agent4_lexical_match_fields():
    common = {
        "trackId": "TRK_1",
        "sectionId": "SEC_1",
        "inputSha256": "a" * 64,
        "parseVersion": "observed-dev-parse-20260806.1",
        "ncsMapVersion": "ncs-lexical-observed-v0.1",
        "mappingMode": "LEXICAL_BASELINE",
        "codeSetStatus": "REVIEW_REQUIRED",
        "goldValidatedFlag": False,
        "denseScore": None,
        "candidateRank": 1,
        "ncsSubCode": "20010101",
        "lexicalScore": 0.5,
        "developmentConfidenceCategory": "HIGH_DEVELOPMENT",
        "unmappedReason": None,
    }
    candidates = pd.DataFrame([common])
    matches = pd.DataFrame([{**common, "selectedCandidateRank": 1}])
    exported = build_export_frames(_frames(), candidates, matches)
    final = exported["preprocessed_posting_tracks"].iloc[0]
    assert final["ncsSubCode"] == "20010101"
    assert final["ncsMappingCoverage"] == 1.0
    assert final["ncsMatchConfidence"] == "HIGH_DEVELOPMENT"
    assert final["ncsMapVersion"] == "ncs-lexical-observed-v0.1"
    assert len(exported["posting_ncs_matches"]) == 1
