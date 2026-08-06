from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from p4.common.keys import make_company_key, make_posting_id, normalize
from p4.common.time import ensure_seoul_datetime, period_month


MIN_BODY_LENGTH = 20


def normalize_posting(raw: dict[str, Any]) -> dict[str, Any]:
    source_url = str(raw.get("sourceUrl") or "").strip()
    source_name = str(raw.get("sourceName") or "linkareer")
    source_posting_id = raw.get("sourcePostingId")
    title = normalize(raw.get("titleRaw"))
    company = normalize(raw.get("companyRaw"))
    body = str(raw.get("bodyRaw") or "").strip()
    posted_raw = raw.get("postedAtRaw")
    posted_at = None
    if posted_raw:
        parsed = pd.Timestamp(posted_raw)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("Asia/Seoul")
        posted_at = ensure_seoul_datetime(parsed.to_pydatetime())
    posting_kind = normalize(raw.get("postingKind"))
    required_source_present = bool(source_url and raw.get("rawSha256") and raw.get("postingRawId"))
    eligible = bool(
        posting_kind == "recruit"
        and posted_at is not None
        and len(body) >= MIN_BODY_LENGTH
        and required_source_present
    )
    posting_id = make_posting_id(source_name, source_posting_id, source_url)
    return {
        "postingId": posting_id,
        "postingRawId": raw.get("postingRawId"),
        "canonicalPostingId": posting_id,
        "sourcePostingId": source_posting_id,
        "sourceUrl": source_url,
        "titleText": title,
        "companyName": company,
        "companyKey": make_company_key(company),
        "postedAt": posted_at,
        "periodMonth": period_month(posted_at) if posted_at else None,
        "bodyText": body,
        "postingKind": posting_kind,
        "postingEligibleFlag": eligible,
        "canonicalRecordFlag": True,
        "duplicateGroupId": None,
    }


def normalize_postings(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [normalize_posting(record) for record in frame.to_dict(orient="records")]
    return pd.DataFrame(rows)

