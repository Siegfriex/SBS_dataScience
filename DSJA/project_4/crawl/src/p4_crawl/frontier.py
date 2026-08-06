"""Persistent discovery/detail/asset frontier construction."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .storage import write_csv_atomic, write_parquet_atomic


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recover_fetching(frame: pd.DataFrame) -> pd.DataFrame:
    recovered = frame.copy()
    mask = recovered["status"].eq("FETCHING") if "status" in recovered else pd.Series(False, index=recovered.index)
    recovered.loc[mask, "status"] = "RETRY"
    recovered.loc[mask, "lastError"] = "recovered interrupted FETCHING state"
    recovered.loc[mask, "updatedAt"] = utc_now()
    return recovered


def build_detail_frontier(
    posting_ids: set[str],
    raw_by_posting_id: dict[str, dict],
    *,
    discovery_month: dict[str, str] | None = None,
    previous: pd.DataFrame | None = None,
    content_observed_at: str | None = None,
) -> pd.DataFrame:
    discovery_month = discovery_month or {}
    old = {}
    if previous is not None and not previous.empty:
        previous = recover_fetching(previous)
        old = {str(row["sourcePostingId"]): row.to_dict() for _, row in previous.iterrows()}
    rows = []
    for source_id in sorted(map(str, posting_ids), key=lambda value: int(value)):
        if source_id in old:
            rows.append(old[source_id])
            continue
        raw = raw_by_posting_id.get(source_id)
        rows.append(
            {
                "sourcePostingId": source_id,
                "discoveryMonth": discovery_month.get(source_id),
                "status": "FETCHED" if raw else "PENDING",
                "attempts": 0,
                "httpStatus": raw.get("httpStatus") if raw else None,
                "rawSha256": raw.get("contentSha256") if raw else None,
                "rawPath": raw.get("rawPath") if raw else None,
                "bytes": raw.get("bytes") if raw else None,
                "lastError": None,
                "updatedAt": (raw.get("fetchedAt") if raw else None) or content_observed_at or "",
            }
        )
    return pd.DataFrame(rows)


def persist_frontier(frame: pd.DataFrame, parquet_path: Path) -> None:
    write_parquet_atomic(frame, parquet_path)
    write_csv_atomic(frame, parquet_path.with_suffix(".csv"))
