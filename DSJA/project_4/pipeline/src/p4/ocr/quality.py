from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from p4.common.hashing import canonical_json_sha256
from p4.common.keys import make_asset_id, make_posting_id


OCR_QUALITY_VERSION = "p4-ocr-quality-v4.0.0"
LAYOUT_TYPES = {"POSTER", "TABLE", "BULLET", "MIXED", "UNKNOWN"}
ACCEPTED_MAPPING_STATUSES = {"ACCEPTED_SINGLE", "ACCEPTED_MULTI", "MODEL_ACCEPTED", "HUMAN_ACCEPTED"}
_HANGUL = re.compile(r"[가-힣]")
_GARBAGE = re.compile(r"[\uFFFD\x00-\x08\x0B\x0C\x0E-\x1F]")
OFFLINE_PILOT_COLUMNS = [
    "sourcePostingId",
    "postingId",
    "assetId",
    "assetUrl",
    "assetType",
    "sourceField",
    "externalAtsAsset",
    "assetBytesAvailableFlag",
    "assetSha256",
    "ocrExecutionStatus",
    "ocrExecutionReason",
    "ocrQualityVersion",
]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _bounded(value: float | None) -> float | None:
    return None if value is None else max(0.0, min(1.0, float(value)))


def compute_ocr_quality(
    *,
    asset_id: str,
    ocr_run_id: str,
    engine: str,
    engine_version: str,
    text: str,
    layout_type: str = "UNKNOWN",
    line_order_confidence: float | None = None,
    html_text: str | None = None,
    mean_engine_confidence: float | None = None,
) -> dict[str, Any]:
    layout = layout_type.upper()
    if layout not in LAYOUT_TYPES:
        raise ValueError(f"invalid OCR layoutType: {layout_type}")
    normalized = str(text or "").strip()
    non_space = [character for character in normalized if not character.isspace()]
    char_count = len(normalized)
    korean_ratio = _ratio(len(_HANGUL.findall(normalized)), len(non_space))
    garbage_rate = _ratio(len(_GARBAGE.findall(normalized)), len(non_space))
    line_order = _bounded(line_order_confidence)
    agreement = (
        SequenceMatcher(None, re.sub(r"\s+", "", html_text or ""), re.sub(r"\s+", "", normalized)).ratio()
        if html_text is not None
        else None
    )
    normalized_lines = [re.sub(r"\s+", "", line) for line in normalized.splitlines() if line.strip()]
    duplicate_overlap = _ratio(len(normalized_lines) - len(set(normalized_lines)), len(normalized_lines))

    reasons: list[str] = []
    if char_count < 30:
        reasons.append("OCR_TEXT_TOO_SHORT")
    if korean_ratio is None or korean_ratio < 0.20:
        reasons.append("OCR_KOREAN_RATIO_LOW")
    if garbage_rate is None or garbage_rate > 0.10:
        reasons.append("OCR_GARBAGE_RATE_HIGH")
    if line_order is None:
        reasons.append("OCR_LINE_ORDER_NOT_EVALUATED")
    elif line_order < 0.70:
        reasons.append("OCR_LINE_ORDER_LOW")
    if layout in {"TABLE", "MIXED"} and (line_order is None or line_order < 0.85):
        reasons.append("OCR_TABLE_MULTICOLUMN_LINE_ORDER_RISK")
    if duplicate_overlap is not None and duplicate_overlap > 0.50:
        reasons.append("OCR_DUPLICATE_OVERLAP_HIGH")

    structure_eligible = (
        char_count >= 30
        and garbage_rate is not None
        and garbage_rate <= 0.20
        and line_order is not None
        and line_order >= 0.50
    )
    mapping_eligible = (
        structure_eligible
        and char_count >= 50
        and korean_ratio is not None
        and korean_ratio >= 0.20
        and garbage_rate is not None
        and garbage_rate <= 0.10
        and line_order is not None
        and line_order >= 0.70
        and not (layout in {"TABLE", "MIXED"} and line_order < 0.85)
        and (duplicate_overlap is None or duplicate_overlap <= 0.50)
    )
    quality_id = f"OQY_{canonical_json_sha256([asset_id, ocr_run_id, OCR_QUALITY_VERSION])[:24]}"
    return {
        "ocrQualityId": quality_id,
        "assetId": asset_id,
        "ocrRunId": ocr_run_id,
        "ocrEngine": engine,
        "ocrEngineVersion": engine_version,
        "ocrCharCount": char_count,
        "ocrKoreanRatio": korean_ratio,
        "ocrGarbageCharRate": garbage_rate,
        "ocrLineOrderConfidence": line_order,
        "ocrDuplicateOverlapRate": duplicate_overlap,
        "layoutType": layout,
        "htmlOcrTextAgreement": agreement,
        "meanEngineConfidence": _bounded(mean_engine_confidence),
        "ocrEligibleForStructure": structure_eligible,
        "ocrEligibleForMapping": mapping_eligible,
        "qualityReasonCodesJson": reasons,
    }


def build_offline_pilot_manifest(
    candidates: pd.DataFrame,
    asset_manifest: pd.DataFrame | None = None,
) -> pd.DataFrame:
    assets = asset_manifest.copy() if asset_manifest is not None else pd.DataFrame()
    by_url: dict[str, dict[str, Any]] = {}
    if len(assets) and "assetUrl" in assets:
        by_url = {str(row["assetUrl"]): row for row in assets.to_dict(orient="records")}
    rows: list[dict[str, Any]] = []
    for candidate in candidates.sort_values(["sourcePostingId", "assetUrl"]).to_dict(orient="records"):
        source_id = str(candidate["sourcePostingId"])
        asset_url = str(candidate["assetUrl"])
        posting_id = make_posting_id("linkareer", source_id)
        asset = by_url.get(asset_url, {})
        asset_sha = asset.get("assetSha256") or asset.get("rawSha256")
        asset_id = str(asset.get("assetId") or make_asset_id(posting_id, asset_url, asset_sha))
        available = bool(asset_sha and asset.get("assetBytesAvailableFlag", False))
        external = bool(candidate.get("externalAtsAsset", False))
        rows.append(
            {
                "sourcePostingId": source_id,
                "postingId": posting_id,
                "assetId": asset_id,
                "assetUrl": asset_url,
                "assetType": candidate.get("assetType"),
                "sourceField": candidate.get("sourceField"),
                "externalAtsAsset": external,
                "assetBytesAvailableFlag": available,
                "assetSha256": asset_sha,
                "ocrExecutionStatus": "READY" if available and not external else "NOT_EVALUATED",
                "ocrExecutionReason": (
                    "EXTERNAL_ATS_EXCLUDED" if external else None if available else "ASSET_BYTES_NOT_AVAILABLE"
                ),
                "ocrQualityVersion": OCR_QUALITY_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=OFFLINE_PILOT_COLUMNS)


def count_ineligible_accepted_mappings(
    mappings: pd.DataFrame,
    chunks: pd.DataFrame,
    source_blocks: pd.DataFrame,
    ocr_quality: pd.DataFrame,
) -> int:
    if mappings.empty:
        return 0
    status_column = "mappingStatus" if "mappingStatus" in mappings else "status"
    accepted = mappings.loc[mappings[status_column].isin(ACCEPTED_MAPPING_STATUSES)].copy()
    if accepted.empty:
        return 0
    evidence = accepted.merge(
        chunks[["chunkId", "sourceBlockId"]], on="chunkId", how="left", validate="many_to_one"
    ).merge(
        source_blocks[["sourceBlockId", "sourceMode", "assetId"]],
        on="sourceBlockId",
        how="left",
        validate="many_to_one",
    )
    quality = ocr_quality[["assetId", "ocrEligibleForMapping"]].drop_duplicates("assetId") if len(ocr_quality) else pd.DataFrame(
        columns=["assetId", "ocrEligibleForMapping"]
    )
    evidence = evidence.merge(quality, on="assetId", how="left", validate="many_to_one")
    violations = evidence["sourceMode"].eq("OCR") & ~evidence["ocrEligibleForMapping"].fillna(False)
    return int(violations.sum())
