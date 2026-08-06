from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Iterable


APQ_ENTRY_FIELDS = (
    "id",
    "group",
    "title",
    "activityTypeID",
    "activityStartAt",
    "activityEndAt",
    "organizationName",
    "jobTypes",
    "recruitStartAt",
    "recruitCloseAt",
    "createdAt",
    "manager",
)


def mask_manager(value: Any) -> Any:
    """Preserve manager structure without retaining personal values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): mask_manager(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [mask_manager(item) for item in value]
    return "[MASKED]"


def _candidate_lists(value: Any) -> Iterable[list[Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "CalendarScreen_ActivityCalendarEntries" and isinstance(item, list):
                yield item
            yield from _candidate_lists(item)


def _entry_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if _looks_like_entry(value):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _entry_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _entry_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _candidate_lists(item)


def _looks_like_entry(value: Any) -> bool:
    return isinstance(value, dict) and "id" in value and "title" in value


def parse_apq_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = list(_entry_dicts(payload))
    parsed: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in entries:
        source_id = str(source.get("id"))
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        row = {field: deepcopy(source.get(field)) for field in APQ_ENTRY_FIELDS if field != "manager"}
        row["activityTypeId"] = source.get("activityTypeID")
        job_types = deepcopy(source.get("jobTypes") or [])
        row["jobTypesRawJson"] = json.dumps(job_types, ensure_ascii=False, sort_keys=True)
        row["managerMasked"] = mask_manager(source.get("manager"))
        parsed.append(row)
    return parsed
