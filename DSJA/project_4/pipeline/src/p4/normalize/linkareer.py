from __future__ import annotations

import json
import re
from typing import Any

from p4.normalize.eligibility import eligibility_flags, resolve_job_types
from p4.parse.linkareer_activity_text import parse_activity_text_html


def _plain_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(block["text"] for block in blocks if not block["headingCandidate"])


def adapt_linkareer_source(index_entry: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    activity_html = detail.get("activityTextHtml") or ""
    blocks = parse_activity_text_html(activity_html) if activity_html else []
    body = _plain_text(blocks)
    sections = {block["sectionAssignment"] for block in blocks if block["text"]}
    structured = resolve_job_types(
        index_entry.get("jobTypesRaw") or index_entry.get("jobTypes") or [],
        detail.get("dutiesJobTypesRaw") or [],
        detail.get("detailTags") or [],
        str(index_entry.get("title") or ""),
        body,
    )
    external_only = bool(detail.get("externalDetailOnlyFlag"))
    flags = eligibility_flags(
        posting_kind="recruit" if index_entry.get("recruitStartAt") or index_entry.get("group") == "recruit" else str(index_entry.get("group") or ""),
        posted_at_available=bool(index_entry.get("createdAt") or index_entry.get("recruitStartAt")),
        job_types_resolved=bool(structured["resolvedJobTypes"]),
        required_or_preferred_text_available=bool(sections.intersection({"required", "preferred"})),
        track_or_boundary_resolved=any(block["boundaryResolvedFlag"] for block in blocks),
        duty_text_available="duty" in sections,
        mappable_task_sentence_available=any(
            block["sectionAssignment"] == "duty" and len(re.sub(r"\s+", "", block["text"])) >= 5
            for block in blocks
        ),
        external_detail_only=external_only,
    )
    return {
        "sourcePostingId": str(index_entry.get("id") or ""),
        "activityTypeId": index_entry.get("activityTypeId", index_entry.get("activityTypeID")),
        "jobTypesRaw": json.dumps(index_entry.get("jobTypesRaw") or index_entry.get("jobTypes") or [], ensure_ascii=False, sort_keys=True),
        "dutiesRawJson": detail.get("dutiesRawJson") or "[]",
        "activityTextHtml": activity_html or None,
        "activityTextAvailableFlag": bool(detail.get("activityTextAvailableFlag")),
        "externalApplyUrl": detail.get("externalApplyUrl"),
        "externalAtsDomain": detail.get("externalAtsDomain"),
        "externalDetailOnlyFlag": external_only,
        "jobTypeConflictFlag": structured["jobTypeConflictFlag"],
        "reviewFlag": structured["reviewFlag"],
        "resolvedJobTypes": structured["resolvedJobTypes"],
        "jobTypeSource": structured["jobTypeSource"],
        **flags,
        "activityTextBlocks": blocks,
    }

