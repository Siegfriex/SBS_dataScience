from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from pandas.testing import assert_frame_equal

from p4.common.hashing import sha256_file
from p4.common.keys import make_company_key
from p4.label.career import LabelEvidence, label_track
from p4.normalize.semantic_recovery import (
    POSTING_KIND_ENUM,
    SEMANTIC_RECOVERY_VERSION,
    canonical_posting_kind,
    recover_authoritative_posted_at,
)
from p4.normalize.observed_batch import (
    CONTRACT_VERSION,
    CRAWL_RELEASE_ID,
    DATA_PROVENANCE,
    DATA_VERSION,
    PARSE_VERSION,
)


EXPORT_VERSION = "observed-dev-export-20260806.1"
LABEL_VERSION = "observed-dev-label-20260806.1"
DEDUP_VERSION = "observed-dev-dedup-20260806.1"
NCS_MAP_VERSION = "ncs-lexical-observed-v0.1"
RUN_TIMESTAMP = "2026-08-06T00:00:00+09:00"

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[^,;\s]{8,}")


def _mask_pii(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return _PHONE.sub("[PHONE_REDACTED]", _EMAIL.sub("[EMAIL_REDACTED]", value))


def _provenance(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["dataVersion"] = DATA_VERSION
    result["contractVersion"] = CONTRACT_VERSION
    result["crawlReleaseId"] = CRAWL_RELEASE_ID
    result["dataProvenance"] = DATA_PROVENANCE
    result["empiricalAnalysisAllowed"] = False
    result["promotionAllowed"] = False
    return result


def _career_labels(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    tracks = frames["posting_track"]
    sections = frames["posting_section"]
    requirements = frames["requirement_fact"]
    rows: list[dict[str, Any]] = []
    for track in tracks.itertuples(index=False):
        track_sections = sections.loc[sections["trackId"] == track.trackId]
        section_ids = set(track_sections.get("sectionId", pd.Series(dtype="string")).astype(str))
        track_requirements = requirements.loc[requirements["sectionId"].astype(str).isin(section_ids)]
        months = pd.to_numeric(track_requirements.get("minExperienceMonths"), errors="coerce").dropna()
        evidence = LabelEvidence(
            is_intern=track.trackType == "intern",
            nominal_entry=track.trackType == "entry",
            explicit_experienced=track.trackType == "experienced",
            min_experience_months=int(months.max()) if not months.empty else None,
            mandatory_prior_experience=bool(track_requirements.get("priorExperienceFlag", pd.Series(dtype=bool)).fillna(False).any()),
            portfolio_required=bool(track_requirements.get("portfolioFlag", pd.Series(dtype=bool)).fillna(False).any()),
            boundary_resolved=bool(
                not track_sections.empty
                and track_sections.get("boundaryResolvedFlag", pd.Series(dtype=bool)).fillna(False).all()
            ),
        )
        rows.append({"postingId": track.postingId, **label_track(track.trackId, evidence), "labelVersion": LABEL_VERSION})
    return _provenance(pd.DataFrame(rows))


def _requirement_aggregate(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    tracks = frames["posting_track"][["trackId", "postingId"]]
    sections = frames["posting_section"][["sectionId", "trackId"]]
    requirements = frames["requirement_fact"].merge(sections, on="sectionId", how="left").merge(tracks, on="trackId", how="left")
    rows: list[dict[str, Any]] = []
    for track_id in tracks["trackId"]:
        group = requirements.loc[requirements["trackId"] == track_id]
        months = pd.to_numeric(group.get("minExperienceMonths"), errors="coerce").dropna()
        rows.append(
            {
                "trackId": track_id,
                "minCareerMonths": int(months.max()) if not months.empty else None,
                "requiredExperienceFlag": bool(group.get("minExperienceMonths", pd.Series(dtype=float)).notna().any()),
                "requiredPriorExperienceFlag": bool(group.get("priorExperienceFlag", pd.Series(dtype=bool)).fillna(False).any()),
                "requiredPortfolioFlag": bool(group.get("portfolioFlag", pd.Series(dtype=bool)).fillna(False).any()),
                "requiredProjectFlag": False,
                "requiredCertificateFlag": False,
                "certificateClass": None,
                "requiredDegreeLevel": None,
                "requiredToolCount": 0,
            }
        )
    return pd.DataFrame(rows)


def _fallback_posting_semantics(normalized: pd.DataFrame) -> pd.DataFrame:
    """Build fail-closed semantics for unit fixtures, never silent default values."""
    rows: list[dict[str, Any]] = []
    for row in normalized.to_dict(orient="records"):
        raw_job_types = row.get("resolvedJobTypesJson") or row.get("jobTypesRawJson") or "[]"
        try:
            job_types = json.loads(raw_job_types) if isinstance(raw_job_types, str) else raw_job_types
        except json.JSONDecodeError:
            job_types = []
        timestamp = recover_authoritative_posted_at(
            {
                "postedAtRaw": row.get("postedAtRaw"),
                "calendarPostedAt": row.get("calendarPostedAt"),
                "createdAt": row.get("createdAt"),
            }
        )
        company_name = row.get("companyName")
        company_key = make_company_key(str(company_name)) if pd.notna(company_name) and str(company_name).strip() else None
        kind = canonical_posting_kind(job_types=job_types, activity_type_id=row.get("activityTypeId", 5), activity_group="recruit")
        rows.append(
            {
                "sourcePostingId": str(row.get("sourcePostingId") or ""),
                "canonicalPostedAt": timestamp.canonical_posted_at,
                "periodMonth": timestamp.period_month,
                "canonicalPostedAtAuthoritySource": timestamp.source_field,
                "canonicalPostedAtNullReason": None if timestamp.canonical_posted_at else "RAW_AUTHORITY_UNAVAILABLE",
                "canonicalPostedAtValidationStatus": "VALIDATED" if timestamp.canonical_posted_at else "UNRESOLVED",
                "companyKey": company_key,
                "companyKeyAuthoritySource": "posting_normalized.companyName" if company_key else None,
                "companyKeyNullReason": None if company_key else "COMPANY_NAME_UNAVAILABLE",
                "companyKeyValidationStatus": "VALIDATED" if company_key else "UNRESOLVED",
                "postingKind": kind,
                "postingKindAuthoritySource": "resolvedJobTypesJson+activityTypeId",
                "postingKindNullReason": None,
                "postingKindValidationStatus": "VALIDATED",
                "inputArtifactSha256": row.get("inputSha256"),
                "semanticRecoveryVersion": SEMANTIC_RECOVERY_VERSION,
                "dataProvenance": DATA_PROVENANCE,
            }
        )
    return pd.DataFrame(rows)


def _attach_posting_semantics(normalized: pd.DataFrame, frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    semantics = frames.get("posting_semantics")
    semantics = semantics.copy() if semantics is not None else _fallback_posting_semantics(normalized)
    required = {
        "sourcePostingId", "canonicalPostedAt", "periodMonth", "companyKey", "postingKind",
        "canonicalPostedAtNullReason", "companyKeyNullReason", "postingKindValidationStatus",
        "inputArtifactSha256", "semanticRecoveryVersion",
    }
    missing = sorted(required.difference(semantics.columns))
    if missing:
        raise ValueError(f"posting semantics missing required columns: {missing}")
    if semantics["sourcePostingId"].astype(str).duplicated().any():
        raise ValueError("posting semantics sourcePostingId must be unique")
    if (~semantics["postingKind"].isin(POSTING_KIND_ENUM)).any():
        invalid = sorted(set(semantics.loc[~semantics["postingKind"].isin(POSTING_KIND_ENUM), "postingKind"].astype(str)))
        raise ValueError(f"invalid canonical postingKind values: {invalid}")
    semantics["sourcePostingId"] = semantics["sourcePostingId"].astype(str)
    result = normalized.copy()
    result["sourcePostingId"] = result["sourcePostingId"].astype(str)
    semantic_columns = [column for column in semantics.columns if column != "dataProvenance"]
    result = result.merge(semantics[semantic_columns], on="sourcePostingId", how="left", validate="one_to_one")
    if result["postingKind"].isna().any():
        raise ValueError("canonical export cannot consume postings without semantic authority rows")
    input_mismatch = result["inputArtifactSha256"].notna() & result["inputSha256"].ne(result["inputArtifactSha256"])
    if input_mismatch.any():
        raise ValueError("semantic authority input SHA does not match normalized posting input SHA")
    return result


def build_export_frames(
    frames: Mapping[str, pd.DataFrame],
    ncs_candidates: pd.DataFrame | None = None,
    ncs_matches: pd.DataFrame | None = None,
    ncs_mapping_to_mart: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    normalized = _attach_posting_semantics(_provenance(frames["posting_normalized"].copy()), frames)
    for column in ("titleText", "companyName", "bodyText"):
        if column in normalized:
            normalized[column] = normalized[column].map(_mask_pii)

    tracks = _provenance(frames["posting_track"].copy())
    if "posting_dedup" in frames:
        tracks = tracks.merge(
            frames["posting_dedup"][[
                "trackId", "canonicalPostingId", "duplicateGroupId", "repostCount", "canonicalRecordFlag"
            ]],
            on="trackId",
            how="left",
            validate="one_to_one",
        )
    else:
        tracks["canonicalPostingId"] = tracks["postingId"]
        tracks["duplicateGroupId"] = tracks["postingId"].map(lambda value: f"DUP_{value}")
        tracks["repostCount"] = 1
        tracks["canonicalRecordFlag"] = True
    tracks["dedupVersion"] = DEDUP_VERSION

    sections = _provenance(frames["posting_section"].copy())
    if "sectionText" in sections:
        sections["sectionText"] = sections["sectionText"].map(_mask_pii)
    requirements = _provenance(frames["requirement_fact"].copy())
    if "requirementText" in requirements:
        requirements["requirementText"] = requirements["requirementText"].map(_mask_pii)
    labels = frames.get("career_access_label", _career_labels(frames)).copy()
    eligibility = _provenance(frames["eligibility"].copy())
    eligibility_columns = [
        "trackId", "postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag", "eligibilitySource"
    ]
    if "postingEligibleFlag" not in labels:
        labels = labels.merge(eligibility[eligibility_columns], on="trackId", how="left")

    if ncs_candidates is None:
        ncs_candidates = pd.DataFrame(
            columns=[
                "trackId", "sectionId", "rank", "ncsUnitCode", "lexicalScore", "denseScore",
                "mappingMode", "developmentConfidenceCategory", "unmappedReason", "goldValidatedFlag",
            ]
        )
    candidates = _provenance(ncs_candidates.copy())
    if "denseScore" not in candidates:
        candidates["denseScore"] = None
    if "mappingMode" not in candidates:
        candidates["mappingMode"] = "LEXICAL_BASELINE"
    if "goldValidatedFlag" not in candidates:
        candidates["goldValidatedFlag"] = False
    if ncs_matches is None:
        ncs_matches = pd.DataFrame(
            columns=[
                "trackId", "sectionId", "candidateRank", "ncsSubCode", "lexicalScore", "denseScore",
                "mappingMode", "codeSetStatus", "developmentConfidenceCategory", "unmappedReason",
                "goldValidatedFlag", "ncsMapVersion",
            ]
        )
    matches = _provenance(ncs_matches.copy())
    if "denseScore" not in matches:
        matches["denseScore"] = None
    if "mappingMode" not in matches:
        matches["mappingMode"] = "LEXICAL_BASELINE"
    if "codeSetStatus" not in matches:
        matches["codeSetStatus"] = "REVIEW_REQUIRED"
    if "goldValidatedFlag" not in matches:
        matches["goldValidatedFlag"] = False
    mapping_to_mart = _provenance(
        ncs_mapping_to_mart.copy()
        if ncs_mapping_to_mart is not None
        else pd.DataFrame(
            columns=[
                "trackId", "sectionId", "chunkId", "mappingStatus", "ncsUnitCode",
                "ncsCorpusVersion", "officialLevel", "ncsBand", "sourceRole",
                "evidencePointer", "candidatePacketSha256", "mappingRunId",
                "mappingQualityEvaluated", "goldAuthority",
            ]
        )
    )

    req = _requirement_aggregate(frames)
    final = tracks.merge(normalized, on=["postingId", "inputSha256"], how="left", suffixes=("", "_posting"))
    final = final.merge(labels.drop(columns=["postingId"], errors="ignore"), on="trackId", how="left", suffixes=("", "_label"))
    final = final.merge(req, on="trackId", how="left")
    final["sourcePostingId"] = final["sourcePostingId"].astype(str)
    final["jobTitle"] = final["titleText"]
    final["companyNameMasked"] = final["companyName"]
    final["recruitmentScope"] = final["trackType"]
    final["boundaryResolvedFlag"] = final["boundaryResolvedFlag"].fillna(False)
    match_fields = matches[
        ["trackId", "ncsSubCode", "developmentConfidenceCategory", "ncsMapVersion", "unmappedReason"]
    ].rename(columns={"developmentConfidenceCategory": "ncsMatchConfidence"})
    final = final.merge(match_fields, on="trackId", how="left")
    final["ncsLevelWeightedMedian"] = None
    final["ncsBandPrimary"] = None
    attempted = final["ncsMapVersion"].notna()
    final["ncsMappingCoverage"] = pd.Series(pd.NA, index=final.index, dtype="Float64")
    final.loc[attempted, "ncsMappingCoverage"] = final.loc[attempted, "ncsSubCode"].notna().astype(float)
    final["ncsMapVersion"] = NCS_MAP_VERSION
    final["extractorVersion"] = EXPORT_VERSION
    final["highDemandScore"] = None
    final["rawSha256"] = final["inputSha256"]
    final["sourceUrl"] = final["sourceUrl"]
    final["sourcePostingId"] = final["sourcePostingId"]
    final["postingEligibleFlag"] = final["postingEligibleFlag"].fillna(False).astype(bool)

    final_columns = [
        "trackId", "postingId", "canonicalPostingId", "sourcePostingId", "sourceUrl",
        "canonicalPostedAt", "periodMonth", "companyKey", "companyNameMasked", "jobTitle",
        "activityTypeId", "trackType", "recruitmentScope", "postingKind", "postingEligibleFlag",
        "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag", "mixedResolvedFlag", "careerClass",
        "internAccessClass", "boundaryResolvedFlag", "minCareerMonths", "requiredExperienceFlag",
        "requiredPriorExperienceFlag", "requiredPortfolioFlag", "requiredProjectFlag",
        "requiredCertificateFlag", "certificateClass", "requiredDegreeLevel", "requiredToolCount",
        "ncsSubCode", "ncsLevelWeightedMedian", "ncsBandPrimary", "ncsMappingCoverage",
        "ncsMatchConfidence", "duplicateGroupId", "repostCount", "canonicalRecordFlag", "rawSha256",
        "parseVersion", "extractorVersion", "labelVersion", "ncsMapVersion", "dedupVersion",
        "dataVersion", "contractVersion", "crawlReleaseId", "dataProvenance",
        "empiricalAnalysisAllowed", "promotionAllowed", "highDemandScore",
    ]
    final = final.loc[:, final_columns]
    return {
        "posting_normalized": normalized,
        "posting_tracks": tracks,
        "posting_sections": sections,
        "requirement_facts": requirements,
        "career_access_labels": labels,
        "posting_ncs_candidates": candidates,
        "posting_ncs_matches": matches,
        "ncs_mapping_to_mart": mapping_to_mart,
        "preprocessed_posting_tracks": final,
    }


def _semantic(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result:
        def normalize(value: Any) -> str:
            if pd.isna(value):
                return "<NULL>"
            text = str(value)
            return text.casefold() if text.casefold() in {"true", "false"} else text

        result[column] = result[column].map(normalize)
    return result


def export_observed_frames(frames: Mapping[str, pd.DataFrame], output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    for name, frame in frames.items():
        parquet_path = root / f"{name}.parquet"
        csv_path = root / f"{name}.csv"
        frame.to_parquet(parquet_path, index=False)
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        csv_frame = pd.read_csv(csv_path, dtype=object, keep_default_na=True)
        parquet_frame = pd.read_parquet(parquet_path)
        assert_frame_equal(_semantic(parquet_frame), _semantic(csv_frame), check_dtype=False)
        for path in (parquet_path, csv_path):
            artifacts.append({"path": path.name, "rows": len(frame), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    checksums = root / "CHECKSUMS.sha256"
    checksums.write_text("".join(f"{row['sha256']}  {row['path']}\n" for row in artifacts), encoding="utf-8")
    return {"artifacts": artifacts, "checksumsPath": checksums.name}


def validate_export_bundle(frames: Mapping[str, pd.DataFrame], output_root: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    root = Path(output_root)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "observed": json.dumps(observed, ensure_ascii=False, default=str)})

    normalized = frames["posting_normalized"]
    tracks = frames["posting_tracks"]
    sections = frames["posting_sections"]
    requirements = frames["requirement_facts"]
    final = frames["preprocessed_posting_tracks"]
    candidates = frames["posting_ncs_candidates"]
    matches = frames["posting_ncs_matches"]
    mapping_to_mart = frames.get("ncs_mapping_to_mart", pd.DataFrame())
    add("posting_pk", not normalized["postingId"].duplicated().any(), int(normalized["postingId"].duplicated().sum()))
    add("track_pk", not tracks["trackId"].duplicated().any(), int(tracks["trackId"].duplicated().sum()))
    add("section_pk", not sections["sectionId"].duplicated().any(), int(sections["sectionId"].duplicated().sum()))
    add("track_fk", tracks["postingId"].isin(normalized["postingId"]).all(), int((~tracks["postingId"].isin(normalized["postingId"])).sum()))
    add("section_fk", sections["trackId"].isin(tracks["trackId"]).all(), int((~sections["trackId"].isin(tracks["trackId"])).sum()))
    add("requirement_fk", requirements["sectionId"].isin(sections["sectionId"]).all(), int((~requirements["sectionId"].isin(sections["sectionId"])).sum()))
    add("raw_sha_lineage", final["rawSha256"].fillna("").str.fullmatch(r"[0-9a-f]{64}").all(), int(final["rawSha256"].isna().sum()))
    required_non_null = ["trackId", "postingId", "sourcePostingId", "sourceUrl", "postingEligibleFlag", "rawSha256"]
    null_counts = {column: int(final[column].isna().sum()) for column in required_non_null}
    add("required_nulls", not any(null_counts.values()), null_counts)
    add("version_singleton", all(final[column].nunique(dropna=False) == 1 for column in ("contractVersion", "crawlReleaseId", "dataVersion", "parseVersion")), {column: final[column].nunique(dropna=False) for column in ("contractVersion", "crawlReleaseId", "dataVersion", "parseVersion")})
    add("provenance", final["dataProvenance"].eq(DATA_PROVENANCE).all() and not final["empiricalAnalysisAllowed"].any() and not final["promotionAllowed"].any(), DATA_PROVENANCE)
    add("eligibility_name", "postingEligibleFlag" in final and "validPostingFlag" not in final, list(final.columns))
    add("high_demand_null", final["highDemandScore"].isna().all(), int(final["highDemandScore"].notna().sum()))
    invalid_posting_kind = int((~final["postingKind"].isin(POSTING_KIND_ENUM)).sum())
    add("posting_kind_canonical_enum", invalid_posting_kind == 0, invalid_posting_kind)
    expected_period = final["canonicalPostedAt"].map(
        lambda value: recover_authoritative_posted_at({"postedAtRaw": value}).period_month
        if pd.notna(value) else None
    )
    period_mismatch = int(
        sum(
            pd.notna(actual) and str(actual) != str(expected)
            for actual, expected in zip(final["periodMonth"], expected_period)
        )
    )
    add("period_month_deterministic", period_mismatch == 0, period_mismatch)
    company_without_key = int((final["companyNameMasked"].notna() & final["companyKey"].isna()).sum())
    add("company_key_when_company_available", company_without_key == 0, company_without_key)
    semantic_input_mismatch = int(
        (
            normalized["inputArtifactSha256"].notna()
            & normalized["inputSha256"].ne(normalized["inputArtifactSha256"])
        ).sum()
    )
    add("semantic_input_sha_binding", semantic_input_mismatch == 0, semantic_input_mismatch)
    add("enum_track_type", set(tracks["trackType"].dropna()).issubset({"entry", "intern", "experienced", "mixedUnresolved", "unknown"}), sorted(set(tracks["trackType"].dropna())))
    if not matches.empty:
        add("ncs_candidate_rows", len(candidates) == 128, len(candidates))
        add("ncs_match_rows", len(matches) == 28, len(matches))
        add("ncs_unmapped_preserved", int(matches["unmappedReason"].notna().sum()) == 1, int(matches["unmappedReason"].notna().sum()))
        add("ncs_dense_null", candidates["denseScore"].isna().all() and matches["denseScore"].isna().all(), int(candidates["denseScore"].notna().sum() + matches["denseScore"].notna().sum()))
        add("ncs_policy", set(candidates["mappingMode"]) == {"LEXICAL_BASELINE"} and set(matches["codeSetStatus"]) == {"REVIEW_REQUIRED"} and not candidates["goldValidatedFlag"].any() and not matches["goldValidatedFlag"].any(), "LEXICAL_BASELINE/REVIEW_REQUIRED/gold=false")
        add("ncs_track_fk", matches["trackId"].isin(tracks["trackId"]).all(), int((~matches["trackId"].isin(tracks["trackId"])).sum()))
        mapped_final = final.loc[final["trackId"].isin(matches["trackId"])]
        add("ncs_final_materialized", len(mapped_final) == 28 and mapped_final["ncsMatchConfidence"].notna().all() and mapped_final["ncsMapVersion"].eq(NCS_MAP_VERSION).all(), len(mapped_final))
    if not mapping_to_mart.empty:
        structural = mapping_to_mart["mappingStatus"].eq("REVIEW_REQUIRED")
        add("ncs_structural_level_band", int(structural.sum()) == 27 and mapping_to_mart.loc[structural, ["officialLevel", "ncsBand"]].notna().all().all(), int(structural.sum()))
        add("ncs_mapping_quality_boundary", not mapping_to_mart.get("mappingQualityEvaluated", pd.Series(False, index=mapping_to_mart.index)).fillna(True).any(), "NOT_EVALUATED")
        add("ncs_structural_not_promoted_to_mart", final["ncsLevelWeightedMedian"].isna().all() and final["ncsBandPrimary"].isna().all(), int(final["ncsLevelWeightedMedian"].notna().sum()))
    text_columns = {"titleText", "companyName", "bodyText", "sectionText", "requirementText", "jobTitle", "companyNameMasked"}
    text = "\n".join(
        str(value)
        for frame in frames.values()
        for column in frame.columns.intersection(list(text_columns))
        for value in frame[column].dropna()
    )
    add("secret_scan", _SECRET.search(text) is None, "text fields only")
    add("pii_scan", _EMAIL.search(text) is None and _PHONE.search(text) is None, "text fields only")
    absolute_values = [value for frame in frames.values() for value in frame.astype(str).to_numpy().ravel() if str(value).startswith("/")]
    add("absolute_path_scan", not absolute_values, absolute_values[:5])
    semantic_failures: list[str] = []
    for name, frame in frames.items():
        try:
            assert_frame_equal(
                _semantic(pd.read_parquet(root / f"{name}.parquet")),
                _semantic(pd.read_csv(root / f"{name}.csv", dtype=object, keep_default_na=True)),
                check_dtype=False,
            )
        except AssertionError:
            semantic_failures.append(name)
    add("csv_parquet_semantic_equality", not semantic_failures, semantic_failures)
    quality = pd.DataFrame(checks)
    summary = {
        "status": "PASS" if quality["status"].eq("PASS").all() else "FAIL",
        "checks": len(quality),
        "passed": int(quality["status"].eq("PASS").sum()),
        "failed": int(quality["status"].eq("FAIL").sum()),
        "generatedAt": RUN_TIMESTAMP,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
    }
    return quality, summary
