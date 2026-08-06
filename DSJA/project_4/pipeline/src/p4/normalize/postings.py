from __future__ import annotations

from datetime import datetime
from typing import Any
import json

import pandas as pd

from p4.common.keys import make_company_key, make_posting_id, normalize
from p4.common.time import ensure_seoul_datetime, period_month
from p4.normalize.eligibility import eligibility_flags, resolve_job_types


MIN_BODY_LENGTH = 20


def normalize_posting(raw: dict[str, Any]) -> dict[str, Any]:
    source_url = str(raw.get("sourceUrl") or "").strip()
    source_name = str(raw.get("sourceName") or "linkareer")
    source_posting_id = raw.get("sourcePostingId")
    title = normalize(raw.get("titleRaw"))
    company = normalize(raw.get("companyRaw"))
    body = str(raw.get("bodyRaw") or "").strip()
    posted_raw = raw.get("postedAtRaw")
    posted_at = None
    if posted_raw:
        parsed = pd.Timestamp(posted_raw)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("Asia/Seoul")
        posted_at = ensure_seoul_datetime(parsed.to_pydatetime())
    posting_kind = normalize(raw.get("postingKind"))
    raw_posting_id = raw.get("rawPostingId") or raw.get("postingRawId")
    required_source_present = bool(source_url and raw.get("rawSha256") and raw_posting_id)
    job_types_raw_json = raw.get("jobTypesRawJson") or "[]"
    try:
        job_types = json.loads(job_types_raw_json) if isinstance(job_types_raw_json, str) else job_types_raw_json
    except json.JSONDecodeError:
        job_types = []
    job_type_resolution = resolve_job_types(
        job_types or [],
        raw.get("dutiesJobTypesRaw") or [],
        raw.get("detailTags") or [],
        title,
        body,
    )
    external_apply = bool(raw.get("externalApplyFlag", raw.get("externalApplyUrl")))
    external_detail_only = bool(raw.get("externalDetailOnlyFlag"))
    activity_text_available = bool(raw.get("activityTextAvailableFlag", body))
    boundary_resolved = any(token in body for token in ("자격요건", "필수요건", "우대사항", "우대요건"))
    requirement_text = any(token in body for token in ("자격요건", "필수요건", "지원자격", "우대사항", "우대요건"))
    duty_text = any(token in body for token in ("담당업무", "주요업무", "직무내용", "수행업무"))
    eligibility = eligibility_flags(
        posting_kind=posting_kind,
        posted_at_available=posted_at is not None,
        source_integrity_available=required_source_present,
        job_types_resolved=bool(job_type_resolution["resolvedJobTypes"]),
        activity_text_available=activity_text_available,
        required_or_preferred_text_available=requirement_text,
        boundary_resolved=boundary_resolved,
        track_resolved=bool(job_type_resolution["resolvedJobTypes"]),
        text_minimum_met=len(body) >= MIN_BODY_LENGTH,
        duty_text_available=duty_text,
        mappable_task_sentence_available=duty_text and len(body) >= MIN_BODY_LENGTH,
        external_apply=external_apply,
        external_detail_only=external_detail_only,
    )
    eligibility["postingEligibleFlag"] = bool(
        eligibility["postingEligibleFlag"] and len(body) >= MIN_BODY_LENGTH and required_source_present
    )
    if not eligibility["postingEligibleFlag"]:
        eligibility["rq1EligibleFlag"] = False
        eligibility["rq2EligibleFlag"] = False
        eligibility["ncsEligibleFlag"] = False
    posting_id = make_posting_id(source_name, source_posting_id, source_url)
    return {
        "postingId": posting_id,
        "rawPostingId": raw_posting_id,
        "canonicalPostingId": posting_id,
        "sourcePostingId": source_posting_id,
        "sourceUrl": source_url,
        "titleText": title,
        "companyName": company,
        "companyKey": make_company_key(company),
        "postedAt": posted_at,
        "periodMonth": period_month(posted_at) if posted_at else None,
        "bodyText": body,
        "postingKind": posting_kind,
        "activityTypeId": raw.get("activityTypeId", raw.get("activityTypeID")),
        "jobTypesRawJson": job_types_raw_json,
        "dutiesRawJson": raw.get("dutiesRawJson"),
        "activityTextHtml": raw.get("activityTextHtml"),
        "activityTextAvailableFlag": activity_text_available,
        "externalApplyUrl": raw.get("externalApplyUrl"),
        "externalAtsDomain": raw.get("externalAtsDomain"),
        "externalApplyFlag": external_apply,
        "externalDetailOnlyFlag": external_detail_only,
        "jobTypeConflictFlag": bool(raw.get("jobTypeConflictFlag", job_type_resolution["jobTypeConflictFlag"])),
        "reviewFlag": bool(raw.get("reviewFlag", job_type_resolution["reviewFlag"])),
        "resolvedJobTypes": job_type_resolution["resolvedJobTypes"],
        "jobTypeSource": job_type_resolution["jobTypeSource"],
        **eligibility,
        "canonicalRecordFlag": True,
        "duplicateGroupId": None,
    }


def normalize_postings(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [normalize_posting(record) for record in frame.to_dict(orient="records")]
    return pd.DataFrame(rows)
