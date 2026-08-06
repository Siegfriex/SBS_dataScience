"""Frozen temporal split policy and cross-split leakage audit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd


@dataclass(frozen=True)
class TemporalSplit:
    split: str
    period_month: str


def assign_temporal_split(period_month: str) -> TemporalSplit:
    """Assign the v4 split without inferring or imputing dates."""
    value = str(period_month)
    try:
        parsed = pd.Period(value, freq="M")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid periodMonth: {period_month!r}") from exc
    canonical = str(parsed)
    if "2020-01" <= canonical <= "2024-12":
        return TemporalSplit("DEVELOPMENT", canonical)
    if "2025-01" <= canonical <= "2025-12":
        return TemporalSplit("VALIDATION", canonical)
    if "2026-01" <= canonical <= "2026-07":
        return TemporalSplit("AUDIT", canonical)
    return TemporalSplit("OUT_OF_WINDOW", canonical)


def _nonempty(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def audit_temporal_leakage(
    rows: pd.DataFrame,
    *,
    period_col: str = "periodMonth",
    grouping_columns: tuple[str, ...] = ("duplicateGroupId", "postingId", "companyKey"),
) -> dict[str, Any]:
    """Detect identifiers that occur in multiple temporal splits.

    Empty input and input without observed period values are explicitly not evaluated.
    """
    if rows.empty or period_col not in rows.columns or not _nonempty(rows[period_col]):
        return {
            "status": "NOT_EVALUATED",
            "reason": "NO_OBSERVED_PERIOD_MONTH",
            "rowCount": int(len(rows)),
            "splitCounts": {},
            "violations": [],
        }

    work = rows.copy()
    work["_temporalSplit"] = work[period_col].map(lambda value: assign_temporal_split(value).split)
    violations: list[dict[str, Any]] = []
    for column in grouping_columns:
        if column not in work.columns:
            continue
        observed = work.loc[work[column].notna(), [column, "_temporalSplit"]].copy()
        observed[column] = observed[column].astype(str).str.strip()
        observed = observed.loc[observed[column] != ""]
        for group_id, group in observed.groupby(column, sort=True):
            splits = sorted(set(group["_temporalSplit"]))
            if len(splits) > 1:
                violations.append({"groupingColumn": column, "groupId": group_id, "splits": splits})

    split_counts = {str(key): int(value) for key, value in work["_temporalSplit"].value_counts().sort_index().items()}
    out_of_window = split_counts.get("OUT_OF_WINDOW", 0)
    if violations:
        status, reason = "FAIL", "CROSS_SPLIT_IDENTIFIER_LEAKAGE"
    elif out_of_window:
        status, reason = "PASS_WITH_FINDINGS", "OUT_OF_WINDOW_ROWS_PRESENT"
    else:
        status, reason = "PASS", None
    return {
        "status": status,
        "reason": reason,
        "rowCount": int(len(work)),
        "splitCounts": split_counts,
        "violations": violations,
    }
