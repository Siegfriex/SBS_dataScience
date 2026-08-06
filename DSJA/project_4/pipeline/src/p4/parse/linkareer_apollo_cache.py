from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse


def find_apollo_cache(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = set(value)
        if "ROOT_QUERY" in keys or any(str(key).startswith("Activity:") for key in keys):
            return value
        for child in value.values():
            try:
                return find_apollo_cache(child)
            except ValueError:
                continue
    elif isinstance(value, list):
        for child in value:
            try:
                return find_apollo_cache(child)
            except ValueError:
                continue
    raise ValueError("Apollo normalized cache not found")


def _resolve(cache: dict[str, Any], value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"__ref"}:
        return _resolve(cache, cache.get(str(value["__ref"]), {}))
    if isinstance(value, dict):
        return {key: _resolve(cache, item) for key, item in value.items() if key != "manager"}
    if isinstance(value, list):
        return [_resolve(cache, item) for item in value]
    return deepcopy(value)


def _activity_key(cache: dict[str, Any], activity_id: str) -> str:
    exact = [f"Activity:{activity_id}", f'Activity:{{"id":"{activity_id}"}}']
    for key in exact:
        if key in cache:
            return key
    for key, value in cache.items():
        if str(key).startswith("Activity:") and isinstance(value, dict) and str(value.get("id")) == str(activity_id):
            return str(key)
    raise ValueError(f"activity {activity_id} not found in Apollo cache")


def extract_activity(cache: dict[str, Any], activity_id: str) -> dict[str, Any]:
    activity = _resolve(cache, cache[_activity_key(cache, activity_id)])
    duties = activity.get("duties") or []
    activity_text = activity.get("activityText") or activity.get("ActivityText")
    if isinstance(activity_text, list):
        texts = [item.get("text") for item in activity_text if isinstance(item, dict) and item.get("text")]
        activity_text_html = "\n".join(texts) if texts else None
    elif isinstance(activity_text, dict):
        activity_text_html = activity_text.get("text")
    else:
        activity_text_html = None
    external_url = (
        activity.get("externalApplyUrl")
        or activity.get("homepageUrl")
        or activity.get("applyUrl")
        or activity.get("recruitmentUrl")
    )
    domain = urlparse(external_url).hostname if external_url else None
    return {
        "activity": activity,
        "dutiesRawJson": json.dumps(duties, ensure_ascii=False, sort_keys=True),
        "dutiesJobTypesRaw": [duty.get("jobType") for duty in duties if isinstance(duty, dict)],
        "activityTextHtml": activity_text_html,
        "activityTextAvailableFlag": bool(activity_text_html and activity_text_html.strip()),
        "externalApplyUrl": external_url,
        "externalAtsDomain": domain,
        "externalApplyFlag": bool(external_url),
        "externalDetailOnlyFlag": bool(external_url and not activity_text_html),
    }
