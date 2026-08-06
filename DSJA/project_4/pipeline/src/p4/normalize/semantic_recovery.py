from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from p4.common.time import period_month


SEMANTIC_RECOVERY_VERSION = "p4-semantic-recovery-v4.0.0"

POSTING_KIND_ENUM = {
    "recruitIntern",
    "recruitNewGrad",
    "recruitExperienced",
    "recruitUnknown",
    "contest",
    "extracurricular",
    "education",
    "club",
    "volunteer",
    "other",
}

REQUIREMENT_TYPE_ENUM = {
    "careerMonths",
    "priorExperience",
    "portfolio",
    "project",
    "certificate",
    "degree",
    "major",
    "skill",
    "tool",
    "language",
    "duty",
    "other",
}

OBLIGATION_ENUM = {"required", "preferred", "unknown"}

# A calendar-list timestamp is preferred when Agent 1 supplies one. SSR createdAt
# is the only accepted fallback. recruitStartAt and fetchedAt are deliberately not
# posting-time substitutes.
AUTHORITATIVE_POSTED_AT_FIELDS = (
    "postedAtRaw",
    "calendarPostedAt",
    "createdAt",
)


@dataclass(frozen=True)
class TimestampRecovery:
    canonical_posted_at: str | None
    period_month: str | None
    source_field: str | None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _parse_timestamp(value: Any) -> pd.Timestamp:
    if isinstance(value, bool):
        raise ValueError("boolean is not a timestamp")
    if isinstance(value, (int, float)):
        magnitude = abs(float(value))
        unit = "ms" if magnitude >= 100_000_000_000 else "s"
        parsed = pd.to_datetime(value, unit=unit, utc=True)
    else:
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("Asia/Seoul")
    return parsed.tz_convert("Asia/Seoul")


def recover_authoritative_posted_at(record: Mapping[str, Any]) -> TimestampRecovery:
    for field in AUTHORITATIVE_POSTED_AT_FIELDS:
        value = record.get(field)
        if _missing(value):
            continue
        parsed = _parse_timestamp(value)
        return TimestampRecovery(
            canonical_posted_at=parsed.isoformat(),
            period_month=period_month(parsed.to_pydatetime()).isoformat(),
            source_field=field,
        )
    return TimestampRecovery(None, None, None)


def _job_types(value: Any) -> set[str]:
    if _missing(value):
        return set()
    if isinstance(value, str):
        raw = value.replace(",", "|").split("|")
    elif isinstance(value, Iterable):
        raw = list(value)
    else:
        raw = [value]
    aliases = {
        "new": "entry",
        "entry": "entry",
        "new_grad": "entry",
        "newgrad": "entry",
        "intern": "intern",
        "experienced": "experienced",
        "career": "experienced",
    }
    return {aliases[token.strip().casefold()] for token in raw if token and token.strip().casefold() in aliases}


def canonical_posting_kind(
    *,
    job_types: Any = None,
    activity_type_id: Any = None,
    activity_group: Any = None,
) -> str:
    group = str(activity_group or "").strip().casefold()
    non_recruit = {
        "contest": "contest",
        "extracurricular": "extracurricular",
        "education": "education",
        "club": "club",
        "volunteer": "volunteer",
    }
    if group in non_recruit:
        return non_recruit[group]
    if activity_type_id not in (None, "", 5, "5") and group not in {"recruit", "recruitment"}:
        return "other"

    resolved = _job_types(job_types)
    if resolved == {"intern"}:
        return "recruitIntern"
    if resolved == {"entry"}:
        return "recruitNewGrad"
    if resolved == {"experienced"}:
        return "recruitExperienced"
    return "recruitUnknown"


def _read_raw_payload(path: Path) -> bytes:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            return stream.read()
    return path.read_bytes()


def build_raw_lineage_index(
    raw_manifest_rows: Iterable[Mapping[str, Any]],
    crawl_root: str | Path,
) -> dict[str, dict[str, Any]]:
    root = Path(crawl_root)
    result: dict[str, dict[str, Any]] = {}
    for row in raw_manifest_rows:
        source_id = str(row.get("sourcePostingId") or "")
        if not source_id:
            continue
        relative_path = row.get("rawPath")
        path = root / str(relative_path) if relative_path else None
        exists = bool(path and path.is_file())
        expected_sha = str(row.get("rawSha256") or row.get("contentSha256") or "")
        actual_sha: str | None = None
        sha_match = False
        if exists and path is not None:
            actual_sha = hashlib.sha256(_read_raw_payload(path)).hexdigest()
            sha_match = bool(expected_sha and actual_sha == expected_sha)
        result[source_id] = {
            "rawManifestFlag": True,
            "rawFileExistsFlag": exists,
            "rawSha256Expected": expected_sha or None,
            "rawSha256Actual": actual_sha,
            "rawSha256MatchFlag": sha_match,
            "rawPath": str(relative_path) if relative_path else None,
        }
    return result


def recover_posting_semantics(
    manifest_record: Mapping[str, Any],
    *,
    authority_record: Mapping[str, Any] | None = None,
    raw_lineage_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    authority = authority_record or {}
    raw = raw_lineage_record or {}
    timestamp = recover_authoritative_posted_at(authority)
    declared = bool(manifest_record.get("hasDetailRawHtml", False))
    manifest_flag = bool(raw.get("rawManifestFlag", False))
    exists = bool(raw.get("rawFileExistsFlag", False))
    mismatch = declared != exists
    kind = canonical_posting_kind(
        job_types=authority.get("jobTypes") or manifest_record.get("jobTypes"),
        activity_type_id=authority.get("activityTypeID", authority.get("activityTypeId")),
        activity_group=authority.get("group"),
    )
    return {
        "sourcePostingId": str(manifest_record.get("sourcePostingId") or ""),
        "canonicalPostedAt": timestamp.canonical_posted_at,
        "periodMonth": timestamp.period_month,
        "canonicalPostedAtSourceField": timestamp.source_field,
        "postingKind": kind,
        "rawDeclaredFlag": declared,
        "rawManifestFlag": manifest_flag,
        "rawFileExistsFlag": exists,
        "rawSha256MatchFlag": bool(raw.get("rawSha256MatchFlag", False)),
        "rawExistenceMismatchFlag": mismatch,
        "rawSha256Expected": raw.get("rawSha256Expected"),
        "rawSha256Actual": raw.get("rawSha256Actual"),
        "rawPath": raw.get("rawPath"),
        "semanticRecoveryVersion": SEMANTIC_RECOVERY_VERSION,
        "semanticRecoveryProvenance": "OBSERVED_DETERMINISTIC_NO_IMPUTATION",
    }


def semantic_quality_audit(
    posting_semantics: pd.DataFrame,
    requirement_facts: pd.DataFrame | None = None,
    *,
    expected_rows: int | None = None,
    timestamp_threshold: float = 0.98,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    postings = posting_semantics.copy()
    requirements = requirement_facts if requirement_facts is not None else pd.DataFrame()
    row_count = len(postings)
    expected = row_count if expected_rows is None else expected_rows
    timestamp_count = int(postings.get("canonicalPostedAt", pd.Series(dtype=object)).notna().sum())
    timestamp_coverage = timestamp_count / expected if expected else None
    period_expected = postings.get("canonicalPostedAt", pd.Series(dtype=object)).map(
        lambda value: recover_authoritative_posted_at({"postedAtRaw": value}).period_month if not _missing(value) else None
    )
    period_actual = postings.get("periodMonth", pd.Series(dtype=object))
    period_mismatch = int(
        sum(
            not _missing(expected_value) and str(expected_value) != str(actual_value)
            for expected_value, actual_value in zip(period_expected, period_actual)
        )
    )
    invalid_posting_kind = int((~postings.get("postingKind", pd.Series(dtype=object)).isin(POSTING_KIND_ENUM)).sum())
    raw_mismatch = int(postings.get("rawExistenceMismatchFlag", pd.Series(dtype=bool)).fillna(True).sum())
    raw_sha_mismatch = int(
        (
            postings.get("rawFileExistsFlag", pd.Series(dtype=bool)).fillna(False)
            & ~postings.get("rawSha256MatchFlag", pd.Series(dtype=bool)).fillna(False)
        ).sum()
    )
    invalid_requirement_type = 0
    invalid_obligation = 0
    if len(requirements):
        invalid_requirement_type = int((~requirements["requirementType"].isin(REQUIREMENT_TYPE_ENUM)).sum())
        invalid_obligation = int((~requirements["obligation"].isin(OBLIGATION_ENUM)).sum())

    checks = [
        {
            "gateId": "TIME_SEMANTICS_READY",
            "ruleId": "canonical_posted_at_coverage",
            "status": "PASS" if timestamp_coverage is not None and timestamp_coverage >= timestamp_threshold else "BLOCKED",
            "observedValue": timestamp_coverage,
            "threshold": f">={timestamp_threshold}",
        },
        {
            "gateId": "TIME_SEMANTICS_READY",
            "ruleId": "period_month_mismatch",
            "status": "PASS" if period_mismatch == 0 else "FAIL",
            "observedValue": period_mismatch,
            "threshold": "0",
        },
        {
            "gateId": "CANONICAL_ENUM_READY",
            "ruleId": "invalid_posting_kind",
            "status": "PASS" if invalid_posting_kind == 0 else "FAIL",
            "observedValue": invalid_posting_kind,
            "threshold": "0",
        },
        {
            "gateId": "CANONICAL_ENUM_READY",
            "ruleId": "invalid_requirement_type",
            "status": "PASS" if invalid_requirement_type == 0 else "FAIL",
            "observedValue": invalid_requirement_type,
            "threshold": "0",
        },
        {
            "gateId": "CANONICAL_ENUM_READY",
            "ruleId": "invalid_obligation",
            "status": "PASS" if invalid_obligation == 0 else "FAIL",
            "observedValue": invalid_obligation,
            "threshold": "0",
        },
        {
            "gateId": "RAW_LINEAGE_READY",
            "ruleId": "raw_existence_mismatch",
            "status": "PASS" if raw_mismatch == 0 else "BLOCKED",
            "observedValue": raw_mismatch,
            "threshold": "0",
        },
        {
            "gateId": "RAW_LINEAGE_READY",
            "ruleId": "raw_sha_mismatch",
            "status": "PASS" if raw_sha_mismatch == 0 else "FAIL",
            "observedValue": raw_sha_mismatch,
            "threshold": "0",
        },
    ]
    quality = pd.DataFrame(checks)
    statuses = set(quality["status"])
    overall = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "PASS"
    summary = {
        "status": overall,
        "postingRows": row_count,
        "expectedPostingRows": expected,
        "canonicalPostedAtCount": timestamp_count,
        "canonicalPostedAtCoverage": timestamp_coverage,
        "periodMonthMismatchCount": period_mismatch,
        "invalidPostingKindCount": invalid_posting_kind,
        "invalidRequirementTypeCount": invalid_requirement_type,
        "invalidObligationCount": invalid_obligation,
        "rawExistenceMismatchCount": raw_mismatch,
        "rawShaMismatchCount": raw_sha_mismatch,
        "semanticRecoveryVersion": SEMANTIC_RECOVERY_VERSION,
        "imputationApplied": False,
    }
    return quality, summary


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
