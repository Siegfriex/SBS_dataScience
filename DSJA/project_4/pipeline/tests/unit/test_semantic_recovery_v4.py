from __future__ import annotations

import gzip
import hashlib

import pandas as pd

from p4.normalize.semantic_recovery import (
    build_raw_lineage_index,
    canonical_posting_kind,
    recover_authoritative_posted_at,
    recover_posting_semantics,
    semantic_quality_audit,
)
from p4.parse.requirements import extract_requirements


def test_authoritative_timestamp_precedence_and_no_start_date_imputation():
    recovered = recover_authoritative_posted_at(
        {"postedAtRaw": "2025-02-03T10:00:00+09:00", "createdAt": 1614652225000}
    )
    assert recovered.source_field == "postedAtRaw"
    assert recovered.period_month == "2025-02-01"
    missing = recover_authoritative_posted_at({"recruitStartAt": 1614565920000, "fetchedAt": "2025-01-01"})
    assert missing.canonical_posted_at is None
    assert missing.period_month is None


def test_posting_kind_is_canonical_and_mixed_is_not_force_allocated():
    assert canonical_posting_kind(job_types="INTERN", activity_type_id=5) == "recruitIntern"
    assert canonical_posting_kind(job_types="NEW", activity_type_id=5) == "recruitNewGrad"
    assert canonical_posting_kind(job_types="EXPERIENCED", activity_type_id=5) == "recruitExperienced"
    assert canonical_posting_kind(job_types="NEW|EXPERIENCED", activity_type_id=5) == "recruitUnknown"
    assert canonical_posting_kind(job_types="NEW", activity_type_id=3) == "other"


def test_raw_lineage_preserves_declared_exists_sha_and_mismatch(tmp_path):
    payload = b"observed raw payload"
    path = tmp_path / "detail.html.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(payload)
    digest = hashlib.sha256(payload).hexdigest()
    raw = build_raw_lineage_index(
        [{"sourcePostingId": "1", "rawPath": path.name, "rawSha256": digest}], tmp_path
    )["1"]
    row = recover_posting_semantics(
        {"sourcePostingId": "1", "hasDetailRawHtml": False, "jobTypes": "NEW"},
        authority_record={"createdAt": 1614652225000, "activityTypeID": 5},
        raw_lineage_record=raw,
    )
    assert row["rawDeclaredFlag"] is False
    assert row["rawFileExistsFlag"] is True
    assert row["rawSha256MatchFlag"] is True
    assert row["rawExistenceMismatchFlag"] is True


def test_requirement_extraction_emits_atomic_type_obligation_and_facts():
    rows = extract_requirements(
        {
            "sectionId": "SEC_1",
            "sectionType": "required",
            "boundaryResolvedFlag": True,
            "sectionText": "- 관련 경력 2년 이상\n- 학사 이상\n- 포트폴리오 및 프로젝트 경험\n- 정보처리기사 자격증",
        }
    )
    types = {row["requirementType"] for row in rows}
    assert {"careerMonths", "priorExperience", "degree", "portfolio", "project", "certificate"} <= types
    assert {row["obligation"] for row in rows} == {"required"}
    assert next(row for row in rows if row["requirementType"] == "careerMonths")["minCareerMonths"] == 24
    assert next(row for row in rows if row["requirementType"] == "degree")["requiredDegreeLevel"] == "bachelor"


def test_semantic_quality_is_fail_closed_without_imputation():
    postings = pd.DataFrame(
        [
            {
                "canonicalPostedAt": "2025-01-02T00:00:00+09:00",
                "periodMonth": "2025-01-01",
                "postingKind": "recruitIntern",
                "rawExistenceMismatchFlag": False,
                "rawFileExistsFlag": True,
                "rawSha256MatchFlag": True,
            },
            {
                "canonicalPostedAt": None,
                "periodMonth": None,
                "postingKind": "recruitUnknown",
                "rawExistenceMismatchFlag": True,
                "rawFileExistsFlag": True,
                "rawSha256MatchFlag": True,
            },
        ]
    )
    requirements = pd.DataFrame([{"requirementType": "degree", "obligation": "required"}])
    quality, summary = semantic_quality_audit(postings, requirements, expected_rows=2)
    assert summary["status"] == "BLOCKED"
    assert summary["canonicalPostedAtCoverage"] == 0.5
    assert summary["rawExistenceMismatchCount"] == 1
    assert summary["imputationApplied"] is False
    assert set(quality.loc[quality["status"] == "BLOCKED", "gateId"]) == {
        "TIME_SEMANTICS_READY",
        "RAW_LINEAGE_READY",
    }
