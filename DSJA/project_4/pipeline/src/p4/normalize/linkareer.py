from __future__ import annotations

import json
import re
from typing import Any

from p4.normalize.eligibility import eligibility_flags, resolve_job_types
from p4.parse.linkareer_activity_text import parse_activity_text_html


def _plain_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(block["text"] for block in blocks if not block["headingCandidate"])


def _json_array(value: Any) -> list[Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return value if isinstance(value, list) else []


def adapt_linkareer_source(index_entry: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    activity_html = detail.get("activityTextHtml") or ""
    blocks = parse_activity_text_html(activity_html) if activity_html else []
    body = _plain_text(blocks)
    sections = {block["sectionAssignment"] for block in blocks if block["text"]}
    job_types_raw_json = index_entry.get("jobTypesRawJson") or json.dumps(
        index_entry.get("jobTypes") or [], ensure_ascii=False, sort_keys=True
    )
    structured = resolve_job_types(
        _json_array(job_types_raw_json),
        detail.get("dutiesJobTypesRaw") or [],
        detail.get("detailTags") or [],
        str(index_entry.get("title") or ""),
        body,
    )
    external_url = detail.get("externalApplyUrl")
    external_apply = bool(detail.get("externalApplyFlag", external_url))
    external_only = bool(detail.get("externalDetailOnlyFlag"))
    activity_available = bool(detail.get("activityTextAvailableFlag") and activity_html.strip())
    flags = eligibility_flags(
        posting_kind=(
            "recruit"
            if str(index_entry.get("activityTypeId", index_entry.get("activityTypeID"))) == "5"
            or str(index_entry.get("group") or "").casefold() == "recruit"
            else str(index_entry.get("group") or "activity")
        ),
        posted_at_available=bool(index_entry.get("createdAt") or index_entry.get("recruitStartAt")),
        source_integrity_available=bool(index_entry.get("id") and index_entry.get("organizationName")),
        job_types_resolved=bool(structured["resolvedJobTypes"]),
        activity_text_available=activity_available,
        required_or_preferred_text_available=bool(sections.intersection({"required", "preferred"})),
        boundary_resolved=any(block["boundaryResolvedFlag"] for block in blocks),
        track_resolved=bool(structured["resolvedJobTypes"]),
        text_minimum_met=len(re.sub(r"\s+", "", body)) >= 5,
        duty_text_available="duty" in sections,
        mappable_task_sentence_available=any(
            block["sectionAssignment"] == "duty" and len(re.sub(r"\s+", "", block["text"])) >= 5
            for block in blocks
        ),
        external_apply=external_apply,
        external_detail_only=external_only,
    )
    return {
        "sourcePostingId": str(index_entry.get("id") or ""),
        "activityTypeId": index_entry.get("activityTypeId", index_entry.get("activityTypeID")),
        "jobTypesRawJson": job_types_raw_json,
        "dutiesRawJson": detail.get("dutiesRawJson") or "[]",
        "activityTextHtml": activity_html or None,
        "activityTextAvailableFlag": activity_available,
        "externalApplyUrl": external_url,
        "externalAtsDomain": detail.get("externalAtsDomain"),
        "externalApplyFlag": external_apply,
        "externalDetailOnlyFlag": external_only,
        "jobTypeConflictFlag": structured["jobTypeConflictFlag"],
        "reviewFlag": structured["reviewFlag"],
        "resolvedJobTypes": structured["resolvedJobTypes"],
        "jobTypeSource": structured["jobTypeSource"],
        **flags,
        "activityTextBlocks": blocks,
        "embeddedImageUrls": detail.get("embeddedImageUrls") or [],
        "ocrRoutingRequiredFlag": bool(detail.get("ocrRoutingRequiredFlag")),
        "ocrQueue": detail.get("ocrQueue") or [],
    }
