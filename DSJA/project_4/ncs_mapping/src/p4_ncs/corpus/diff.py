"""Deterministic row-level corpus release diff."""
from __future__ import annotations

from typing import Any

import pandas as pd

from p4_ncs.api.redaction import canonical_json_sha256

_CHANGE_FIELDS = {
    "officialName": "NAME_CHANGED",
    "definitionText": "DEFINITION_CHANGED",
    "officialLevel": "LEVEL_CHANGED",
    "parentNodeCode": "PARENT_CHANGED",
    "ksaSha256": "KSA_CHANGED",
}


def _value(value: Any) -> Any:
    return None if pd.isna(value) else value


def diff_corpus_nodes(
    old_nodes: pd.DataFrame,
    new_nodes: pd.DataFrame,
    *,
    from_version: str,
    to_version: str,
) -> pd.DataFrame:
    key = ["nodeType", "nodeCode"]
    old = old_nodes.copy().set_index(key, drop=False)
    new = new_nodes.copy().set_index(key, drop=False)
    rows: list[dict[str, Any]] = []

    def add(change_type: str, node_type: str, node_code: str, before: Any, after: Any) -> None:
        rows.append({
            "fromCorpusVersion": from_version,
            "toCorpusVersion": to_version,
            "changeType": change_type,
            "nodeType": node_type,
            "nodeCode": node_code,
            "oldHash": canonical_json_sha256(before) if before is not None else None,
            "newHash": canonical_json_sha256(after) if after is not None else None,
        })

    for node_type, node_code in sorted(set(old.index).difference(new.index)):
        add("REMOVED", node_type, node_code, old.loc[(node_type, node_code)].to_dict(), None)
    for node_type, node_code in sorted(set(new.index).difference(old.index)):
        add("ADDED", node_type, node_code, None, new.loc[(node_type, node_code)].to_dict())
    for node_type, node_code in sorted(set(old.index).intersection(new.index)):
        before = old.loc[(node_type, node_code)]
        after = new.loc[(node_type, node_code)]
        for field, change_type in _CHANGE_FIELDS.items():
            if field not in before.index and field not in after.index:
                continue
            a = _value(before.get(field))
            b = _value(after.get(field))
            if a != b:
                add(change_type, node_type, node_code, {field: a}, {field: b})
    columns = ["fromCorpusVersion", "toCorpusVersion", "changeType", "nodeType", "nodeCode", "oldHash", "newHash"]
    return pd.DataFrame(rows, columns=columns).sort_values(["nodeType", "nodeCode", "changeType"], kind="stable").reset_index(drop=True)
