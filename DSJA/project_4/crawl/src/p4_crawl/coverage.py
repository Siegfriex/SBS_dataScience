"""Monthly APQ pagination and restartable coverage checkpoints."""

from __future__ import annotations

import calendar
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .apq import APQClient
from .storage import atomic_write_json, canonical_json, sha256_bytes, write_parquet_atomic

ENTRIES_OPERATION = "CalendarScreen_ActivityCalendarEntries"
TOTAL_OPERATION = "CalendarScreen_Activities"


def month_bounds_ms(period: str) -> tuple[int, int]:
    year, month = map(int, period.split("-"))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, calendar.monthrange(year, month)[1], 23, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def collect_month(period: str, apq: APQClient, coverage_root: Path, *, page_cap: int = 1000) -> dict:
    """Exhaust every day/side bucket and persist one resumable checkpoint."""

    from_ms, to_ms = month_bounds_ms(period)
    bucket_ids: dict[tuple[str, str], set[str]] = {}
    bucket_totals: dict[tuple[str, str], int] = {}
    discoveries: dict[tuple[str, str], dict] = {}
    fingerprints: Counter[str] = Counter()
    stopped_reason = None
    request_count = 0
    effective_cap = page_cap

    for page in range(1, page_cap + 1):
        variables = {
            "filterBy": {"activityTypeIDs": ["5"], "q": ""},
            "scrapFilterBy": {"q": ""},
            "from": from_ms,
            "to": to_ms,
            "pagination": {"page": 1, "pageSize": 32},
            "includeStart": True,
            "includeEnd": True,
            "includeScrapStart": False,
            "includeScrapEnd": False,
            "nodePagination": {"page": page, "pageSize": 6},
        }
        result = apq.fetch(ENTRIES_OPERATION, variables, period=period)
        request_count += 1
        nodes = result.payload["data"]["activityCalendarEntries"]["nodes"]
        parts = []
        for day in nodes:
            bucket_date = datetime.fromtimestamp(int(day["date"]) / 1000, tz=timezone.utc).date().isoformat()
            for side in ("start", "end"):
                connection = day.get(side) or {"nodes": [], "totalCount": 0}
                key = (bucket_date, side)
                bucket_totals[key] = int(connection.get("totalCount") or 0)
                bucket_ids.setdefault(key, set())
                page_ids = []
                for node in connection.get("nodes") or []:
                    source_id = str(node["id"])
                    page_ids.append(source_id)
                    bucket_ids[key].add(source_id)
                    discoveries.setdefault(
                        (source_id, side),
                        {
                            "sourcePostingId": source_id,
                            "activityTypeId": int(node.get("activityTypeID") or 5),
                            "discoveryMonth": period,
                            "discoverySide": side,
                            "startBucketDate": bucket_date if side == "start" else None,
                            "endBucketDate": bucket_date if side == "end" else None,
                            "createdAt": node.get("createdAt"),
                            "recruitStartAt": node.get("recruitStartAt"),
                            "recruitCloseAt": node.get("recruitCloseAt"),
                            "discoveryRoute": "linkareer_graphql_apq_calendar",
                            "queryHash": result.query_hash,
                        },
                    )
                parts.append((bucket_date, side, tuple(page_ids)))
        fingerprint = sha256_bytes(canonical_json(parts).encode("utf-8"))
        fingerprints[fingerprint] += 1
        if page == 1:
            max_bucket = max(bucket_totals.values(), default=0)
            effective_cap = min(page_cap, max(20, math.ceil(max_bucket / 6) + 10))
        if all(len(bucket_ids.get(key, set())) >= total for key, total in bucket_totals.items()):
            break
        if not nodes:
            stopped_reason = "emptyPageBeforeExhaustion"
            break
        if fingerprints[fingerprint] >= 2:
            stopped_reason = "repeatedPageBeforeExhaustion"
            break
        if page >= effective_cap:
            stopped_reason = "pageCapReached"
            break

    distinct_ids = {value for values in bucket_ids.values() for value in values}
    total_variables = {
        "filterBy": {"activityTypeIDs": ["5"]},
        "rangeBy": {
            "recruitStartAt": {"from": from_ms, "to": to_ms},
            "recruitCloseAt": {"from": from_ms, "to": to_ms},
        },
    }
    expected_distinct = None
    aggregate_error = None
    try:
        total_result = apq.fetch(TOTAL_OPERATION, total_variables, period=period)
        request_count += 1
        expected_distinct = int(total_result.payload["data"]["activities"]["totalCount"])
    except Exception as exc:  # checkpoint the partial month instead of losing it
        aggregate_error = f"{type(exc).__name__}: {exc}"
    exhausted = all(len(bucket_ids.get(key, set())) >= total for key, total in bucket_totals.items())
    count_matches = expected_distinct is not None and len(distinct_ids) == expected_distinct
    if exhausted and count_matches:
        status, reason = "complete", "complete"
    elif distinct_ids:
        status = "partial"
        reason = "aggregateCountUnavailable" if expected_distinct is None else "aggregateCountMismatch" if not count_matches else stopped_reason or "paginationIncomplete"
    else:
        status, reason = "insufficient", stopped_reason or "noRecordsVerified"

    discovery_path = coverage_root / period[:4] / f"{period}.discovery.parquet"
    discovery = pd.DataFrame(discoveries.values())
    if not discovery.empty:
        discovery = discovery.sort_values(["sourcePostingId", "discoverySide"])
        write_parquet_atomic(discovery, discovery_path)
    checkpoint = {
        "periodMonth": period,
        "sourceName": "linkareer",
        "activityTypeID": 5,
        "returnedDistinctCount": len(distinct_ids),
        "expectedTotalCount": sum(bucket_totals.values()),
        "expectedDistinctCount": expected_distinct,
        "paginationCompleteFlag": exhausted,
        "monthlyTotalCountVerified": count_matches,
        "requestCount": request_count,
        "coverageStatus": status,
        "coverageReason": reason,
        "stoppedReason": stopped_reason,
        "aggregateError": aggregate_error,
        "discoveryPath": str(discovery_path) if discovery_path.exists() else None,
    }
    atomic_write_json(coverage_root / period[:4] / f"{period}.json", checkpoint)
    return checkpoint


def merge_checkpoints(baseline: pd.DataFrame, coverage_root: Path) -> pd.DataFrame:
    merged = baseline.set_index("periodMonth").copy()
    import json

    for path in sorted(coverage_root.rglob("????-??.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        for column, value in row.items():
            if column in merged.columns:
                merged.loc[row["periodMonth"], column] = value
    return merged.reset_index()
