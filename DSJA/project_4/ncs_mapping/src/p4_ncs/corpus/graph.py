"""Build a prefix graph without inventing missing official hierarchy names."""
from __future__ import annotations

from typing import Any

import pandas as pd

NODE_COLUMNS = [
    "ncsCorpusVersion", "nodeCode", "nodeType", "parentNodeCode", "officialName",
    "nameSource", "definitionText", "officialLevel", "validFrom", "validTo",
    "sourceEndpoint", "sourceSha256",
]
EDGE_COLUMNS = [
    "ncsCorpusVersion", "fromNodeCode", "toNodeCode", "edgeType",
    "sourceEndpoint", "sourceSha256", "isActive",
]
SOURCE_ENDPOINT = "LOCAL_OFFICIAL_NCS_UNIT_RELEASE"


def _require_source(units: pd.DataFrame) -> str:
    required = {
        "ncsUnitCode", "ncsUnitName", "ncsLevel", "ncsBand", "majorCode", "middleCode",
        "minorCode", "subCode", "rawSha256",
    }
    missing = required.difference(units.columns)
    if missing:
        raise ValueError(f"NCS source missing columns: {', '.join(sorted(missing))}")
    shas = units["rawSha256"].dropna().astype(str).unique().tolist()
    if len(shas) != 1 or len(shas[0]) != 64:
        raise ValueError("NCS source must have one 64-character rawSha256")
    if units["ncsUnitCode"].duplicated().any():
        raise ValueError("duplicate ncsUnitCode")
    levels = pd.to_numeric(units["ncsLevel"], errors="coerce")
    if levels.isna().any() or not levels.between(1, 8).all():
        raise ValueError("official ncsLevel must be complete and within 1..8")
    return shas[0]


def _codes(units: pd.DataFrame) -> pd.DataFrame:
    code = pd.DataFrame(index=units.index)
    code["LARGE"] = units["majorCode"].astype("string")
    code["MIDDLE"] = code["LARGE"] + units["middleCode"].astype("string")
    code["SMALL"] = code["MIDDLE"] + units["minorCode"].astype("string")
    code["SUBCATEGORY"] = code["SMALL"] + units["subCode"].astype("string")
    return code


def build_prefix_graph(units: pd.DataFrame, ncs_corpus_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_sha = _require_source(units)
    code = _codes(units)
    parent_type = {"LARGE": None, "MIDDLE": "LARGE", "SMALL": "MIDDLE", "SUBCATEGORY": "SMALL"}
    rows: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node_type in ("LARGE", "MIDDLE", "SMALL", "SUBCATEGORY"):
        pairs = pd.DataFrame({"nodeCode": code[node_type]})
        parent = parent_type[node_type]
        pairs["parentNodeCode"] = code[parent] if parent else pd.NA
        pairs = pairs.drop_duplicates().sort_values("nodeCode", kind="stable")
        for row in pairs.itertuples(index=False):
            parent_code = None if pd.isna(row.parentNodeCode) else str(row.parentNodeCode)
            rows.append({
                "ncsCorpusVersion": ncs_corpus_version,
                "nodeCode": str(row.nodeCode),
                "nodeType": node_type,
                "parentNodeCode": parent_code,
                "officialName": None,
                "nameSource": "MISSING",
                "definitionText": None,
                "officialLevel": None,
                "validFrom": None,
                "validTo": None,
                "sourceEndpoint": SOURCE_ENDPOINT,
                "sourceSha256": source_sha,
            })
            if parent_code:
                edges.append({
                    "ncsCorpusVersion": ncs_corpus_version,
                    "fromNodeCode": parent_code,
                    "toNodeCode": str(row.nodeCode),
                    "edgeType": "PARENT_OF",
                    "sourceEndpoint": SOURCE_ENDPOINT,
                    "sourceSha256": source_sha,
                    "isActive": True,
                })
    unit_rows = units.assign(parentNodeCode=code["SUBCATEGORY"]).sort_values("ncsUnitCode", kind="stable")
    for row in unit_rows.itertuples(index=False):
        rows.append({
            "ncsCorpusVersion": ncs_corpus_version,
            "nodeCode": str(row.ncsUnitCode),
            "nodeType": "UNIT",
            "parentNodeCode": str(row.parentNodeCode),
            "officialName": str(row.ncsUnitName),
            "nameSource": "OFFICIAL",
            "definitionText": None,
            "officialLevel": int(row.ncsLevel),
            "validFrom": None,
            "validTo": None,
            "sourceEndpoint": SOURCE_ENDPOINT,
            "sourceSha256": source_sha,
        })
        edges.append({
            "ncsCorpusVersion": ncs_corpus_version,
            "fromNodeCode": str(row.parentNodeCode),
            "toNodeCode": str(row.ncsUnitCode),
            "edgeType": "PARENT_OF",
            "sourceEndpoint": SOURCE_ENDPOINT,
            "sourceSha256": source_sha,
            "isActive": True,
        })
    nodes = pd.DataFrame(rows, columns=NODE_COLUMNS).sort_values(["nodeType", "nodeCode"], kind="stable").reset_index(drop=True)
    edge_frame = pd.DataFrame(edges, columns=EDGE_COLUMNS).sort_values(["fromNodeCode", "toNodeCode"], kind="stable").reset_index(drop=True)
    validate_prefix_graph(nodes, edge_frame)
    return nodes, edge_frame


def build_ability_units(units: pd.DataFrame, ncs_corpus_version: str) -> pd.DataFrame:
    _require_source(units)
    code = _codes(units)
    return pd.DataFrame({
        "ncsCorpusVersion": ncs_corpus_version,
        "ncsUnitCode": units["ncsUnitCode"].astype(str),
        "ncsUnitName": units["ncsUnitName"].astype(str),
        "ncsUnitDefinition": pd.array([pd.NA] * len(units), dtype="string"),
        "ncsLevel": pd.to_numeric(units["ncsLevel"]).astype("int64"),
        "ncsBand": units["ncsBand"].astype(str),
        "subcategoryCode": code["SUBCATEGORY"].astype(str),
        "dutyCodesJson": [[] for _ in range(len(units))],
        "sourceSha256": units["rawSha256"].astype(str),
    }).sort_values("ncsUnitCode", kind="stable").reset_index(drop=True)


def validate_prefix_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    if nodes.empty:
        raise ValueError("NCS graph cannot be empty")
    if nodes.duplicated(["ncsCorpusVersion", "nodeCode", "nodeType"]).any():
        raise ValueError("duplicate NCS node primary key")
    if edges.duplicated(["ncsCorpusVersion", "fromNodeCode", "toNodeCode", "edgeType"]).any():
        raise ValueError("duplicate NCS edge")
    keys = set(zip(nodes["ncsCorpusVersion"].astype(str), nodes["nodeCode"].astype(str)))
    for side in ("fromNodeCode", "toNodeCode"):
        edge_keys = set(zip(edges["ncsCorpusVersion"].astype(str), edges[side].astype(str)))
        missing = edge_keys.difference(keys)
        if missing:
            raise ValueError(f"orphan NCS edge {side}: {sorted(missing)[:3]}")
    hierarchy = nodes["nodeType"].ne("UNIT")
    if nodes.loc[hierarchy, "officialName"].notna().any() or not nodes.loc[hierarchy, "nameSource"].eq("MISSING").all():
        raise ValueError("prefix hierarchy names must remain explicitly MISSING")
    unit = nodes["nodeType"].eq("UNIT")
    levels = pd.to_numeric(nodes.loc[unit, "officialLevel"], errors="coerce")
    if levels.isna().any() or not levels.between(1, 8).all():
        raise ValueError("unit officialLevel must be complete and within 1..8")
