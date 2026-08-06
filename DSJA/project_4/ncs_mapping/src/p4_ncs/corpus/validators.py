"""Fail-closed bridge and crosswalk validators."""
from __future__ import annotations

import pandas as pd

STATUSES = {"MATCHED", "UNMATCHED", "AMBIGUOUS", "INVALID"}


def validate_duty_unit_bridge(bridge: pd.DataFrame, nodes: pd.DataFrame) -> str:
    if bridge.empty:
        return "NOT_EVALUATED"
    required = {
        "ncsCorpusVersion", "dutyCode", "unitCode", "relationshipType", "sourceEndpoint",
        "sourceSha256", "canonicalizationStatus", "isActive",
    }
    missing = required.difference(bridge.columns)
    if missing:
        raise ValueError(f"bridge missing columns: {', '.join(sorted(missing))}")
    if not set(bridge["canonicalizationStatus"]).issubset(STATUSES):
        raise ValueError("invalid bridge canonicalizationStatus")
    matched = bridge["canonicalizationStatus"].eq("MATCHED")
    unit_codes = set(nodes.loc[nodes["nodeType"].eq("UNIT"), "nodeCode"].astype(str))
    duty_codes = set(nodes.loc[nodes["nodeType"].eq("DUTY"), "nodeCode"].astype(str))
    if not bridge.loc[matched, "unitCode"].astype(str).isin(unit_codes).all():
        raise ValueError("matched bridge references unknown unit code")
    if not bridge.loc[matched, "dutyCode"].astype(str).isin(duty_codes).all():
        raise ValueError("matched bridge references unknown duty code")
    return "PASS"


def validate_crosswalk(crosswalk: pd.DataFrame, nodes: pd.DataFrame) -> str:
    if crosswalk.empty:
        return "NOT_EVALUATED"
    required = {
        "provider", "externalCode", "externalName", "canonicalNodeCode",
        "canonicalizationStatus", "matchBasis", "sourceResponseSha256", "crosswalkVersion",
    }
    missing = required.difference(crosswalk.columns)
    if missing:
        raise ValueError(f"crosswalk missing columns: {', '.join(sorted(missing))}")
    if not set(crosswalk["canonicalizationStatus"]).issubset(STATUSES):
        raise ValueError("invalid crosswalk canonicalizationStatus")
    matched = crosswalk["canonicalizationStatus"].eq("MATCHED")
    canonical_codes = set(nodes["nodeCode"].astype(str))
    if crosswalk.loc[matched, "canonicalNodeCode"].isna().any():
        raise ValueError("matched crosswalk must have canonicalNodeCode")
    if not crosswalk.loc[matched, "canonicalNodeCode"].astype(str).isin(canonical_codes).all():
        raise ValueError("matched crosswalk references unknown canonical code")
    must_be_null = crosswalk["canonicalizationStatus"].isin({"UNMATCHED", "INVALID"})
    if crosswalk.loc[must_be_null, "canonicalNodeCode"].notna().any():
        raise ValueError("unmatched or invalid crosswalk must not carry canonical code")
    return "PASS"
