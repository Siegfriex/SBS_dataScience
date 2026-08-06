from __future__ import annotations

from copy import deepcopy
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
    elif isinstance(value, list):
        for item in value:
            yield from _candidate_lists(item)


def _looks_like_entry(value: Any) -> bool:
    return isinstance(value, dict) and "id" in value and "title" in value


def parse_apq_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = list(_candidate_lists(payload))
    if not candidates:
        root = payload.get("data", {}).get("CalendarScreen_ActivityCalendarEntries")
        if isinstance(root, dict):
            for key in ("entries", "items", "nodes", "results"):
                if isinstance(root.get(key), list):
                    candidates.append(root[key])
    entries = next((items for items in candidates if all(_looks_like_entry(item) for item in items)), [])
    parsed: list[dict[str, Any]] = []
    for source in entries:
        row = {field: deepcopy(source.get(field)) for field in APQ_ENTRY_FIELDS if field != "manager"}
        row["activityTypeId"] = source.get("activityTypeID")
        row["jobTypesRaw"] = deepcopy(source.get("jobTypes") or [])
        row["managerMasked"] = mask_manager(source.get("manager"))
        parsed.append(row)
    return parsed

