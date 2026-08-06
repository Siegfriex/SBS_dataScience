from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.testing import assert_frame_equal

from p4.common.hashing import canonical_json_sha256, sha256_file


REQUIRED_COLUMNS = {
    "trackId", "sectionId", "inputSha256", "parseVersion", "ncsMapVersion",
    "dataVersion", "contractVersion", "crawlReleaseId", "dataProvenance",
    "empiricalAnalysisAllowed", "promotionAllowed", "mappingMode", "codeSetStatus",
    "goldValidatedFlag", "denseScore", "candidateRank", "ncsSubCode", "lexicalScore",
    "developmentConfidenceCategory", "unmappedReason",
}


def _semantic(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.astype("string").fillna("").reset_index(drop=True)


def validate_agent4_ncs_handoff(handoff_path: str | Path, project_root: str | Path) -> dict[str, Any]:
    handoff_path = Path(handoff_path)
    root = Path(project_root)
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    expected_envelope = {
        "agentId": "P4-A4-NCS",
        "recipientAgentId": "P4-A2-PIPELINE",
        "handoffType": "NCS_MAPPING_OBSERVED_DEVELOPMENT",
        "status": "NCS_MAPPING_DEV_READY",
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": "observed-dev-20260806.1",
        "runMode": "observed-dev",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "mappingMode": "LEXICAL_BASELINE",
        "codeSetStatus": "REVIEW_REQUIRED",
        "goldValidatedFlag": False,
        "denseScore": None,
    }
    for key, expected in expected_envelope.items():
        if payload.get(key) != expected:
            raise ValueError(f"Agent4 handoff {key} mismatch")
    declared_self = payload.get("handoffSha256")
    unsigned = dict(payload)
    unsigned.pop("handoffSha256", None)
    if declared_self != canonical_json_sha256(unsigned):
        raise ValueError("Agent4 handoff self SHA mismatch")
    if payload.get("inputDutyRows") != 28 or not payload.get("inputRowsSha256Verified"):
        raise ValueError("Agent4 handoff duty input lineage is incomplete")

    frames: dict[str, pd.DataFrame] = {}
    names = (
        "ncs_units",
        "core_ai_it_codes",
        "ncs_alias_dictionary",
        "posting_ncs_candidates",
        "posting_ncs_matches",
    )
    for name in names:
        record = payload.get("files", {}).get(name, {})
        parquet_rel = str(record.get("parquet") or "")
        csv_rel = str(record.get("csv") or "")
        if not parquet_rel or parquet_rel.startswith(("/", "~")) or ".." in Path(parquet_rel).parts:
            raise ValueError(f"unsafe Agent4 {name} path")
        parquet_path, csv_path = root / parquet_rel, root / csv_rel
        if sha256_file(parquet_path) != record.get("parquetSha256") or sha256_file(csv_path) != record.get("csvSha256"):
            raise ValueError(f"Agent4 {name} checksum mismatch")
        parquet = pd.read_parquet(parquet_path)
        csv = pd.read_csv(csv_path, dtype="string", keep_default_na=False)
        if len(parquet) != record.get("rows"):
            raise ValueError(f"Agent4 {name} row count or schema mismatch")
        if name in {"posting_ncs_candidates", "posting_ncs_matches"} and not REQUIRED_COLUMNS.issubset(parquet.columns):
            raise ValueError(f"Agent4 {name} row count or schema mismatch")
        assert_frame_equal(_semantic(parquet), _semantic(csv), check_dtype=False)
        frames[name] = parquet

    candidates, matches = frames["posting_ncs_candidates"], frames["posting_ncs_matches"]
    units, codes = frames["ncs_units"], frames["core_ai_it_codes"]
    if len(units) != 13_442 or not units["ncsLevel"].between(1, 8).all():
        raise ValueError("Agent4 NCS source must contain 13,442 level 1-8 units")
    if len(codes) != 120 or int(codes["included"].fillna(False).astype(bool).sum()) != 69:
        raise ValueError("Agent4 core-ai-it-v0.1 review set must contain 120 rows / 69 included")
    if set(codes["reviewStatus"].dropna()) != {"REVIEW_REQUIRED"}:
        raise ValueError("Agent4 code set is not review-only")
    if len(candidates) != 128 or len(matches) != 28:
        raise ValueError("Agent4 observed mapping requires 128 candidates and 28 matches")
    if candidates.duplicated(["sectionId", "candidateRank"]).any() or matches["sectionId"].duplicated().any():
        raise ValueError("Agent4 NCS grain is not unique")
    for frame in (candidates, matches):
        if frame["denseScore"].notna().any() or frame["goldValidatedFlag"].any():
            raise ValueError("Agent4 dense/gold development policy violated")
        if set(frame["mappingMode"]) != {"LEXICAL_BASELINE"} or set(frame["codeSetStatus"]) != {"REVIEW_REQUIRED"}:
            raise ValueError("Agent4 mapping policy mismatch")
        if set(frame["dataProvenance"]) != {"OBSERVED_DEVELOPMENT_ONLY"}:
            raise ValueError("Agent4 provenance mismatch")
    if int(matches["unmappedReason"].notna().sum()) != 1 or int(matches["ncsSubCode"].isna().sum()) != 1:
        raise ValueError("Agent4 unmapped preservation mismatch")
    if candidates.groupby("sectionId").size().max() > 5:
        raise ValueError("Agent4 candidate top-5 cap exceeded")
    return {
        "payload": payload,
        "frames": frames,
        "handoffSha256": declared_self,
        "candidateRows": len(candidates),
        "matchRows": len(matches),
        "unmappedRows": 1,
    }
