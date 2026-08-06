"""Asset eligibility and manifest preparation."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .manifests import append_jsonl_once, stable_row_id


def is_linkareer_hosted(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (host == "linkareer.com" or host.endswith(".linkareer.com"))


def build_asset_frontier(posting_records: pd.DataFrame, completed_urls: set[str] | None = None) -> pd.DataFrame:
    completed_urls = completed_urls or set()
    rows: dict[str, dict] = {}
    for _, posting in posting_records.iterrows():
        for candidate in json.loads(posting.get("assetCandidatesJson") or "[]"):
            url = candidate.get("assetUrl")
            period_month = posting.get("periodMonth") or posting.get("discoveryMonth")
            if not isinstance(period_month, str) or len(period_month) != 7:
                recruit_start = posting.get("recruitStartAt")
                period_month = str(recruit_start)[:7] if recruit_start is not None and len(str(recruit_start)) >= 7 else None
            if url and is_linkareer_hosted(url) and url not in completed_urls:
                rows.setdefault(
                    url,
                    {
                        "sourcePostingId": str(posting["sourcePostingId"]),
                        "assetUrl": url,
                        "assetType": candidate.get("assetType"),
                        "sourceField": candidate.get("sourceField"),
                        "periodMonth": period_month,
                        "status": "PENDING",
                        "externalAtsAsset": False,
                    },
                )
    return pd.DataFrame(rows.values())


def collect_pending_assets(frontier: pd.DataFrame, http, manifest_path: Path, *, max_items: int = 0) -> list[dict]:
    rows = []
    candidates = frontier[frontier["status"].isin(["PENDING", "RETRY"])].copy()
    if max_items > 0:
        candidates = candidates.head(max_items)
    for _, candidate in candidates.iterrows():
        period_month = candidate.get("periodMonth")
        if not isinstance(period_month, str) or len(period_month) != 7:
            raise ValueError(f"missing periodMonth for asset {candidate['assetUrl']}")
        response = http.get(
            candidate["assetUrl"],
            _p4_context={"entityType": "asset", "period": period_month},
        )
        lineage = getattr(response, "p4_manifest")
        status = "FETCHED" if response.status_code == 200 else "DEAD" if response.status_code in {404, 410} else "RETRY"
        row = {
            **candidate.to_dict(),
            "status": status,
            "httpStatus": response.status_code,
            "assetSha256": lineage["contentSha256"],
            "rawPath": lineage["rawPath"],
            "bytes": lineage["bytes"],
            "fetchedAt": lineage["fetchedAt"],
        }
        row["rowId"] = stable_row_id(row, ("assetUrl", "assetSha256"))
        append_jsonl_once(manifest_path, row)
        rows.append(row)
    return rows
