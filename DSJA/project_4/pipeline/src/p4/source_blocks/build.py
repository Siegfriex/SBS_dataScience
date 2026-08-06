from __future__ import annotations

from typing import Any

import pandas as pd

from p4.common.hashing import canonical_json_sha256


SOURCE_BLOCK_VERSION = "p4-source-block-v4.0.0"
SOURCE_MODES = {"HTML", "ACTIVITY_TEXT", "OCR", "MERGED"}


def _source_block_id(raw_posting_id: str, section_id: str, source_mode: str, source_text: str) -> str:
    digest = canonical_json_sha256([raw_posting_id, section_id, source_mode, source_text])
    return f"SBK_{digest[:24]}"


def addendum_source_mode(value: Any) -> str:
    token = str(value or "").strip().upper()
    aliases = {
        "HTML": "HTML",
        "SSR_HTML": "HTML",
        "SSR_ACTIVITY_TEXT": "ACTIVITY_TEXT",
        "ACTIVITY_TEXT": "ACTIVITY_TEXT",
        "OCR": "OCR",
        "MERGED": "MERGED",
    }
    mode = aliases.get(token)
    if mode is None:
        raise ValueError(f"unsupported sourceMode for semantic addendum: {value!r}")
    return mode


def legacy_source_mode(value: Any) -> str:
    mode = addendum_source_mode(value)
    return {"HTML": "html", "ACTIVITY_TEXT": "html", "OCR": "ocr", "MERGED": "merged"}[mode]


def build_source_block_bundle(
    postings: pd.DataFrame,
    tracks: pd.DataFrame,
    sections: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    posting_fields = postings[["postingId", "rawPostingId", "bodyText", "inputSha256", "parseVersion"]].copy()
    joined = sections.merge(tracks[["trackId", "postingId"]], on="trackId", how="left", validate="many_to_one").merge(
        posting_fields, on="postingId", how="left", validate="many_to_one"
    )
    if joined[["postingId", "rawPostingId", "inputSha256"]].isna().any().any():
        raise ValueError("source blocks require posting/raw lineage for every section")

    rows: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    for record in joined.sort_values(["trackId", "sectionOrdinal"]).to_dict(orient="records"):
        text = str(record.get("sectionText") or "")
        body = str(record.get("bodyText") or "")
        start = body.find(text) if text else 0
        start = start if start >= 0 else 0
        end = start + len(text)
        source_mode = addendum_source_mode(record.get("sourceMode"))
        source_block_id = _source_block_id(
            str(record["rawPostingId"]), str(record["sectionId"]), source_mode, text
        )
        rows.append(
            {
                "sourceBlockId": source_block_id,
                "postingId": str(record["postingId"]),
                "rawPostingId": str(record["rawPostingId"]),
                "assetId": None,
                "sourceMode": source_mode,
                "sourceText": text,
                "startChar": start,
                "endChar": end,
                "pageNo": None,
                "bboxJson": None,
                "rawSha256": str(record["inputSha256"]),
                "parserVersion": str(record.get("parseVersion") or SOURCE_BLOCK_VERSION),
            }
        )
        links.append({"sectionId": str(record["sectionId"]), "sourceBlockId": source_block_id})
    result = pd.DataFrame(rows)
    if result["sourceBlockId"].duplicated().any():
        raise ValueError("sourceBlockId primary-key violation")
    link_frame = pd.DataFrame(links)
    if link_frame["sectionId"].duplicated().any():
        raise ValueError("observed source-block bundle requires one block per section")
    return result, link_frame


def build_source_blocks(
    postings: pd.DataFrame,
    tracks: pd.DataFrame,
    sections: pd.DataFrame,
) -> pd.DataFrame:
    blocks, _ = build_source_block_bundle(postings, tracks, sections)
    return blocks
