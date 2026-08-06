from __future__ import annotations

from typing import Any, Iterable

from p4.common.keys import normalize


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
    job_types_resolved: bool,
    required_or_preferred_text_available: bool,
    track_or_boundary_resolved: bool,
    duty_text_available: bool,
    mappable_task_sentence_available: bool,
    external_detail_only: bool,
) -> dict[str, Any]:
    posting_eligible = normalize(posting_kind) == "recruit" and posted_at_available
    rq1 = posting_eligible and job_types_resolved
    rq2 = bool(
        posting_eligible
        and required_or_preferred_text_available
        and track_or_boundary_resolved
        and not external_detail_only
    )
    ncs = bool(
        posting_eligible
        and duty_text_available
        and mappable_task_sentence_available
        and not external_detail_only
    )
    reason = None
    if external_detail_only:
        reason = "externalAtsBodyUnavailable"
    elif posting_eligible and not required_or_preferred_text_available:
        reason = "requirementTextUnavailable"
    elif posting_eligible and not track_or_boundary_resolved:
        reason = "trackOrBoundaryUnresolved"
    return {
        "postingEligibleFlag": posting_eligible,
        "rq1EligibleFlag": rq1,
        "rq2EligibleFlag": rq2,
        "ncsEligibleFlag": ncs,
        "rq2ExclusionReason": reason,
    }

