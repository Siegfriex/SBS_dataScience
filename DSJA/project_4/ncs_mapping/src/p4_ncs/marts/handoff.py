"""Fail-closed structural NCS mapping-to-mart handoff.

The handoff proves code/level/band lineage.  It does not turn the observed
lexical baseline into an accepted mapping or HUMAN_GOLD.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


HANDOFF_VERSION = "p4-ncs-mapping-to-mart-v1"
BAND_BY_LEVEL = {
    1: "level1to2", 2: "level1to2", 3: "level3to4", 4: "level3to4",
    5: "level5to6", 6: "level5to6", 7: "level7to8", 8: "level7to8",
}


def _sha_rows(frame: pd.DataFrame) -> str:
    records = frame.where(pd.notna(frame), None).to_dict(orient="records")
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_mapping_to_mart_handoff(
    matches: pd.DataFrame,
    candidates: pd.DataFrame,
    units: pd.DataFrame,
    chunks: pd.DataFrame,
    chunk_roles: pd.DataFrame,
    *,
    mapping_run_id: str,
) -> pd.DataFrame:
    required_match = {"trackId", "sectionId", "matchedNcsUnitCode", "unmappedReason"}
    if missing := sorted(required_match.difference(matches.columns)):
        raise ValueError(f"matches missing columns: {missing}")
    if units["ncsUnitCode"].duplicated().any():
        raise ValueError("official NCS unit code must be unique")
    unit_index = units.set_index("ncsUnitCode", drop=False)
    chunk_index = (
        chunks.merge(chunk_roles, on="chunkId", how="inner", validate="one_to_one")
        .query("sourceRole == 'DUTY' and ncsMappableFlag == True")
        .sort_values(["sectionId", "chunkId"])
        .drop_duplicates("sectionId")
        .set_index("sectionId", drop=False)
    )
    rows: list[dict[str, Any]] = []
    for match in matches.sort_values(["trackId", "sectionId"]).to_dict(orient="records"):
        section_id = str(match["sectionId"])
        if section_id not in chunk_index.index:
            raise ValueError(f"DUTY chunk missing for section: {section_id}")
        code = match.get("matchedNcsUnitCode")
        mapped = pd.notna(code) and bool(str(code))
        if mapped and str(code) not in unit_index.index:
            raise ValueError(f"unsupported official NCS code: {code}")
        unit = unit_index.loc[str(code)] if mapped else None
        level = int(unit["ncsLevel"]) if mapped else None
        band = str(unit["ncsBand"]) if mapped else None
        if mapped and BAND_BY_LEVEL[level] != band:
            raise ValueError(f"official level/band mismatch: {code}")
        candidate_rows = candidates.loc[
            (candidates["trackId"].astype(str) == str(match["trackId"]))
            & (candidates["sectionId"].astype(str) == section_id)
        ].sort_values("candidateRank")
        rows.append(
            {
                "trackId": str(match["trackId"]),
                "sectionId": section_id,
                "chunkId": str(chunk_index.loc[section_id, "chunkId"]),
                "mappingStatus": "REVIEW_REQUIRED" if mapped else "UNMAPPED",
                "ncsUnitCode": str(code) if mapped else None,
                "ncsCorpusVersion": str(unit["ncsSourceVersion"]) if mapped else str(units["ncsSourceVersion"].iloc[0]),
                "officialLevel": level,
                "ncsBand": band,
                "sourceRole": "DUTY",
                "evidencePointer": f"posting_ncs_matches.parquet#trackId={match['trackId']};sectionId={section_id}",
                "candidatePacketSha256": _sha_rows(candidate_rows),
                "mappingRunId": mapping_run_id,
                "handoffVersion": HANDOFF_VERSION,
                "goldAuthority": "NONE",
                "mappingQualityEvaluated": False,
                "promotionAllowed": False,
            }
        )
    result = pd.DataFrame(rows)
    validate_mapping_to_mart_handoff(result)
    return result


def validate_mapping_to_mart_handoff(frame: pd.DataFrame) -> None:
    required = {
        "trackId", "sectionId", "chunkId", "mappingStatus", "ncsUnitCode",
        "ncsCorpusVersion", "officialLevel", "ncsBand", "sourceRole",
        "evidencePointer", "candidatePacketSha256", "mappingRunId",
    }
    if missing := sorted(required.difference(frame.columns)):
        raise ValueError(f"mapping-to-mart handoff missing columns: {missing}")
    if frame[["trackId", "sectionId"]].duplicated().any():
        raise ValueError("mapping-to-mart grain must be unique by trackId+sectionId")
    if not set(frame["mappingStatus"]).issubset({"REVIEW_REQUIRED", "UNMAPPED", "ABSTAIN", "OUT_OF_SCOPE"}):
        raise ValueError("invalid mappingStatus")
    mapped = frame["mappingStatus"].eq("REVIEW_REQUIRED")
    if frame.loc[mapped, ["ncsUnitCode", "officialLevel", "ncsBand"]].isna().any().any():
        raise ValueError("review-required structural mappings require official code/level/band")
    if not frame.loc[mapped, "officialLevel"].astype(int).between(1, 8).all():
        raise ValueError("official NCS level must be 1..8")
    if not frame["candidatePacketSha256"].str.fullmatch(r"[0-9a-f]{64}").all():
        raise ValueError("candidate packet SHA must be SHA-256")
    if frame.get("mappingQualityEvaluated", pd.Series(False, index=frame.index)).fillna(True).any():
        raise ValueError("structural handoff cannot claim mapping quality evaluation")
    if frame.get("promotionAllowed", pd.Series(False, index=frame.index)).fillna(True).any():
        raise ValueError("structural handoff cannot allow promotion")
