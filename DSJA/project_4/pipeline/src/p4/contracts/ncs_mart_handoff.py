"""Validate the A4 structural mapping-to-mart handoff without promoting it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "trackId", "sectionId", "chunkId", "mappingStatus", "ncsUnitCode",
    "ncsCorpusVersion", "officialLevel", "ncsBand", "sourceRole",
    "evidencePointer", "candidatePacketSha256", "mappingRunId",
]


def load_ncs_mart_handoff(path: str | Path) -> tuple[pd.DataFrame, dict]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "p4-ncs-mapping-to-mart-v1":
        raise ValueError("unsupported NCS mapping-to-mart schema")
    if payload.get("mappingQualityStatus") != "NOT_EVALUATED":
        raise ValueError("structural NCS handoff cannot claim mapping quality")
    if payload.get("goldAuthority") != "NONE" or int(payload.get("humanGoldRows", -1)) != 0:
        raise ValueError("HUMAN_GOLD boundary violated")
    if payload.get("promotionAllowed") is not False or payload.get("empiricalAnalysisAllowed") is not False:
        raise ValueError("structural NCS handoff cannot allow promotion or empirical analysis")
    rows = payload.get("rows", [])
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    if hashlib.sha256(canonical.encode()).hexdigest() != payload.get("rowsSha256"):
        raise ValueError("NCS mapping-to-mart rows SHA mismatch")
    frame = pd.DataFrame(rows)
    if missing := sorted(set(REQUIRED_COLUMNS).difference(frame.columns)):
        raise ValueError(f"NCS mapping-to-mart columns missing: {missing}")
    if len(frame) != int(payload.get("rowCount", -1)):
        raise ValueError("NCS mapping-to-mart row count mismatch")
    if frame[["trackId", "sectionId"]].duplicated().any():
        raise ValueError("NCS mapping-to-mart duplicate grain")
    if not set(frame["mappingStatus"]).issubset({"REVIEW_REQUIRED", "UNMAPPED", "ABSTAIN", "OUT_OF_SCOPE"}):
        raise ValueError("invalid NCS mapping status")
    return frame, payload
