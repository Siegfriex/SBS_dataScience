from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


SEOUL = ZoneInfo("Asia/Seoul")


def ensure_seoul_datetime(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-naive datetime is prohibited")
    return parsed.astimezone(SEOUL)


def period_month(value: date | datetime | str) -> date:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if "T" in value or " " in value:
            value = ensure_seoul_datetime(parsed).date()
        else:
            value = parsed.date()
    elif isinstance(value, datetime):
        value = ensure_seoul_datetime(value).date()
    return date(value.year, value.month, 1)


def quarter_number(value: date | datetime | str) -> int:
    month = period_month(value).month
    return ((month - 1) // 3) + 1


def quarter_label(value: date | datetime | str) -> str:
    month = period_month(value)
    return f"{month.year}-Q{quarter_number(month)}"

