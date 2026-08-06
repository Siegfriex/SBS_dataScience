"""Linkareer SSR/Apollo parsing and restartable detail collection."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .storage import canonical_json, sha256_bytes
from .frontier import persist_frontier
from .storage import write_parquet_atomic


def resolve_ref(cache: dict, value):
    return cache.get(value["__ref"]) if isinstance(value, dict) and "__ref" in value else value


def refs_to_objects(cache: dict, values) -> list[dict]:
    return [obj for value in (values or []) if isinstance((obj := resolve_ref(cache, value)), dict)]


def activity_for_id(cache: dict, source_id: str) -> dict | None:
    direct = cache.get(f"Activity:{source_id}")
    if isinstance(direct, dict) and "detailText" in direct:
        return direct
    matches = [
        value
        for value in cache.values()
        if isinstance(value, dict) and value.get("__typename") == "Activity" and str(value.get("id")) == source_id
    ]
    matches.sort(key=lambda value: "detailText" in value, reverse=True)
    return matches[0] if matches else None


def extract_detail_record(source_id: str, body: bytes, lineage: dict) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(body, "html.parser")
    tag = soup.select_one("script#__NEXT_DATA__")
    if tag is None:
        raise ValueError("missing __NEXT_DATA__")
    next_data = json.loads(tag.string or tag.get_text())
    cache = next_data["props"]["pageProps"]["__APOLLO_STATE__"]
    activity = activity_for_id(cache, source_id)
    if activity is None:
        raise ValueError("matching Activity entity not found")
    detail_obj = resolve_ref(cache, activity.get("detailText")) or {}
    activity_text = detail_obj.get("text") or ""
    objects = refs_to_objects(cache, activity.get("files"))
    for key in ("thumbnailImage", "logoImage"):
        value = resolve_ref(cache, activity.get(key))
        if isinstance(value, dict):
            objects.append(value)
    candidates = []
    seen_urls: set[str] = set()
    for value in objects:
        url = value.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        type_object = resolve_ref(cache, value.get("type")) or {}
        candidates.append({"assetUrl": url, "assetType": type_object.get("name") or "file", "sourceField": "files"})
    for image in BeautifulSoup(activity_text, "html.parser").find_all("img"):
        url = urljoin("https://linkareer.com/", image.get("src") or "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            candidates.append({"assetUrl": url, "assetType": "embeddedActivityTextImage", "sourceField": "ActivityText.text"})
    record = {
        "sourcePostingId": source_id,
        "sourceName": "linkareer",
        "sourceUrl": lineage.get("requestUrl") or f"https://linkareer.com/activity/{source_id}",
        "httpStatus": lineage["httpStatus"],
        "rawPath": lineage["rawPath"],
        "rawSha256": lineage.get("contentSha256") or lineage.get("rawSha256"),
        "rawBytes": lineage.get("bytes"),
        "fetchedAt": lineage.get("fetchedAt"),
        "activityTypeId": activity.get("activityTypeID"),
        "title": activity.get("title"),
        "organizationName": activity.get("organizationName"),
        "createdAt": activity.get("createdAt"),
        "recruitStartAt": activity.get("recruitStartAt"),
        "recruitCloseAt": activity.get("recruitCloseAt"),
        "jobTypesJson": canonical_json(activity.get("jobTypes") or []),
        "dutiesJson": canonical_json([resolve_ref(cache, value) or value for value in activity.get("duties") or []]),
        "externalApplyUrl": activity.get("applyDetail") or activity.get("homepageURL"),
        "activityTextSha256": sha256_bytes(activity_text.encode("utf-8")),
        "activityTextLength": len(activity_text),
        "activityTextAvailable": bool(activity_text),
        "assetCandidateCount": len(candidates),
        "assetCandidatesJson": canonical_json(candidates),
        "managerPiiPersisted": False,
        "highDemandScore": None,
    }
    return record, candidates


def collect_pending_details(frontier, http, state_root: Path, *, max_items: int = 0):
    """Consume PENDING/RETRY rows and checkpoint after every request."""

    import pandas as pd

    frame = frontier.copy()
    records_path = state_root / "posting_manifest.parquet"
    old = pd.read_parquet(records_path) if records_path.exists() else pd.DataFrame()
    records = {str(row["sourcePostingId"]): row.to_dict() for _, row in old.iterrows()} if not old.empty else {}
    indexes = frame.index[frame["status"].isin(["PENDING", "RETRY"])].tolist()
    if max_items > 0:
        indexes = indexes[:max_items]
    for index in indexes:
        source_id = str(frame.at[index, "sourcePostingId"])
        period = frame.at[index, "discoveryMonth"]
        if not isinstance(period, str) or len(period) != 7:
            period = "2021-03"
        frame.at[index, "status"] = "FETCHING"
        frame.at[index, "attempts"] = int(frame.at[index, "attempts"] or 0) + 1
        persist_frontier(frame, state_root / "detail_frontier.parquet")
        try:
            response = http.get(
                f"https://linkareer.com/activity/{source_id}",
                _p4_context={"entityType": "detail", "period": period},
            )
            lineage = getattr(response, "p4_manifest")
            frame.at[index, "httpStatus"] = response.status_code
            frame.at[index, "rawSha256"] = lineage["contentSha256"]
            frame.at[index, "rawPath"] = lineage["rawPath"]
            frame.at[index, "bytes"] = lineage["bytes"]
            if response.status_code == 200:
                record, _ = extract_detail_record(source_id, response.content, lineage)
                records[source_id] = record
                frame.at[index, "status"] = "FETCHED"
                frame.at[index, "lastError"] = None
            elif response.status_code in {404, 410}:
                frame.at[index, "status"] = "DEAD"
                frame.at[index, "lastError"] = f"terminal HTTP {response.status_code}"
            else:
                frame.at[index, "status"] = "RETRY"
                frame.at[index, "lastError"] = f"HTTP {response.status_code}"
        except Exception as exc:
            frame.at[index, "status"] = "RETRY"
            frame.at[index, "lastError"] = f"{type(exc).__name__}: {exc}"[:500]
            persist_frontier(frame, state_root / "detail_frontier.parquet")
            raise
        persist_frontier(frame, state_root / "detail_frontier.parquet")
        if records:
            write_parquet_atomic(pd.DataFrame(records.values()).sort_values("sourcePostingId"), records_path)
    return frame
