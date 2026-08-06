from __future__ import annotations

import json
from typing import Any, Iterable

from p4.common.keys import normalize


RQ2_EXCLUSION_REASONS = {
    "activityTextMissing",
    "externalAtsBodyUnavailable",
    "boundaryUnresolved",
    "trackUnresolved",
    "textTooShort",
    "nonRecruitPosting",
    "other",
}

JOB_TYPE_TERMS = {
    "entry": ("신입", "경력무관"),
    "intern": ("인턴",),
    "experienced": ("경력", "경력직"),
}


def _job_type_values(values: Iterable[Any]) -> set[str]:
    found: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            text = " ".join(str(value.get(key) or "") for key in ("name", "label", "title", "value"))
        else:
            text = str(value or "")
        normalized = normalize(text)
        for job_type, terms in JOB_TYPE_TERMS.items():
            if any(term in normalized for term in terms):
                if job_type == "experienced" and "경력무관" in normalized:
                    continue
                found.add(job_type)
    return found


def resolve_job_types(
    job_types: Iterable[Any],
    duty_job_types: Iterable[Any],
    detail_tags: Iterable[Any],
    title: str,
    body: str,
) -> dict[str, Any]:
    structured = _job_type_values([*job_types, *duty_job_types])
    tag_types = _job_type_values(detail_tags)
    text_types = _job_type_values([title, body])
    resolved = structured or tag_types or text_types
    fallback = tag_types or text_types
    conflict = bool(structured and fallback and structured != fallback)
    return {
        "resolvedJobTypes": sorted(resolved),
        "jobTypeSource": "structured" if structured else "detailTag" if tag_types else "textRule" if text_types else "unknown",
        "jobTypeConflictFlag": conflict,
        "reviewFlag": conflict,
        "structuredJobTypes": sorted(structured),
        "textJobTypes": sorted(text_types),
    }


def eligibility_flags(
    *,
    posting_kind: str,
    posted_at_available: bool,
    source_integrity_available: bool = True,
    job_types_resolved: bool,
    activity_text_available: bool,
    required_or_preferred_text_available: bool,
    boundary_resolved: bool,
    track_resolved: bool,
    text_minimum_met: bool,
    duty_text_available: bool,
    mappable_task_sentence_available: bool,
    external_apply: bool,
    external_detail_only: bool,
) -> dict[str, Any]:
    del external_apply  # external application alone is not an exclusion condition.
    is_recruit = normalize(posting_kind) == "recruit"
    posting_eligible = is_recruit and posted_at_available and source_integrity_available
    rq1 = posting_eligible and job_types_resolved
    rq2 = bool(
        posting_eligible
        and activity_text_available
        and required_or_preferred_text_available
        and boundary_resolved
        and track_resolved
        and text_minimum_met
        and not external_detail_only
    )
    ncs = bool(
        posting_eligible
        and activity_text_available
        and duty_text_available
        and mappable_task_sentence_available
        and not external_detail_only
    )

    reasons: list[str] = []
    if not is_recruit:
        reasons.append("nonRecruitPosting")
    if posting_eligible:
        if external_detail_only:
            reasons.append("externalAtsBodyUnavailable")
        if not activity_text_available:
            reasons.append("activityTextMissing")
        if not boundary_resolved:
            reasons.append("boundaryUnresolved")
        if not track_resolved:
            reasons.append("trackUnresolved")
        if not text_minimum_met:
            reasons.append("textTooShort")
    reasons = list(dict.fromkeys(reason for reason in reasons if reason in RQ2_EXCLUSION_REASONS))
    return {
        "postingEligibleFlag": posting_eligible,
        "rq1EligibleFlag": rq1,
        "rq2EligibleFlag": rq2,
        "ncsEligibleFlag": ncs,
        "rq2ExclusionReason": reasons[0] if reasons else None,
        "rq2ExclusionReasonsJson": json.dumps(reasons, ensure_ascii=False),
    }
