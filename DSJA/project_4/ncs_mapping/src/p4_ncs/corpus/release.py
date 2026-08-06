"""Compact immutable candidate-release manifest generation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from p4_ncs.api.redaction import canonical_json_sha256
from p4_ncs.corpus.graph import build_ability_units, build_prefix_graph
from p4_ncs.quality.stage_artifacts import sha256_file


def _frame_sha(frame: pd.DataFrame, columns: list[str]) -> str:
    subset = frame.loc[:, columns].copy().astype(object)
    records = subset.where(pd.notna(subset), None).to_dict(orient="records")
    return canonical_json_sha256(records)


def build_candidate_release_manifest(
    units: pd.DataFrame,
    *,
    ncs_corpus_version: str,
    normalized_path: str | Path | None = None,
) -> dict[str, Any]:
    nodes, edges = build_prefix_graph(units, ncs_corpus_version)
    ability = build_ability_units(units, ncs_corpus_version)
    counts = nodes["nodeType"].value_counts().to_dict()
    source_sha = str(units["rawSha256"].iloc[0])
    return {
        "manifestVersion": "ncs-corpus-candidate-manifest-v4.0",
        "ncsCorpusVersion": ncs_corpus_version,
        "status": "CANDIDATE",
        "sourceClass": "OFFICIAL_LOCAL_RELEASE",
        "sourceDataset": str(units["sourceDataset"].iloc[0]),
        "sourceVersion": str(units["sourceVersion"].iloc[0]),
        "sourceSha256": source_sha,
        "normalizedArtifactSha256": sha256_file(Path(normalized_path)) if normalized_path else None,
        "rowCounts": {
            "ncsAbilityUnit": len(ability),
            "ncsNode": len(nodes),
            "ncsEdge": len(edges),
            "ncsDutyUnitBridge": 0,
            "ncsExternalCodeCrosswalk": 0,
        },
        "nodeTypeCounts": {key: int(counts.get(key, 0)) for key in ["LARGE", "MIDDLE", "SMALL", "SUBCATEGORY", "UNIT"]},
        "officialFieldCoverage": {
            "unitName": int(ability["ncsUnitName"].notna().sum()),
            "unitLevel": int(ability["ncsLevel"].notna().sum()),
            "unitDefinition": int(ability["ncsUnitDefinition"].notna().sum()),
            "hierarchyOfficialName": int(nodes.loc[nodes["nodeType"].ne("UNIT"), "officialName"].notna().sum()),
        },
        "graphSemanticSha256": _frame_sha(nodes, ["nodeCode", "nodeType", "parentNodeCode", "officialName", "nameSource", "officialLevel", "sourceSha256"]),
        "edgeSemanticSha256": _frame_sha(edges, ["fromNodeCode", "toNodeCode", "edgeType", "sourceSha256", "isActive"]),
        "abilityUnitSemanticSha256": _frame_sha(ability, ["ncsUnitCode", "ncsUnitName", "ncsLevel", "ncsBand", "subcategoryCode", "sourceSha256"]),
        "liveApiContractStatus": "NOT_EVALUATED",
        "bridgeStatus": "NOT_EVALUATED",
        "crosswalkStatus": "NOT_EVALUATED",
        "promotionAllowed": False,
    }
