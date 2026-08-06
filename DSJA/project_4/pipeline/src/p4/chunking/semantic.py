from __future__ import annotations

import re
from typing import Any

import pandas as pd

from p4.common.hashing import canonical_json_sha256
from p4.common.keys import normalize


CHUNKING_VERSION = "p4-semantic-chunk-v4.0.0"
CHUNK_TYPES = {
    "DUTY",
    "REQUIREMENT",
    "KNOWLEDGE",
    "SKILL",
    "COMPETENCY_EXPERIENCE",
    "PROCESS",
    "OTHER",
}
SOURCE_ROLES = {"DUTY", "REQUIRED", "PREFERRED", "OTHER"}
_LINE = re.compile(r"(?:^|\n)\s*(?:[-*•·]|\d+[.)])?\s*(.+?)(?=\n|$)")
_KNOWLEDGE = re.compile(r"(?:지식|이해|knowledge)", re.IGNORECASE)
_SKILL = re.compile(r"(?:기술|활용|능숙|skill|tool)", re.IGNORECASE)
_EXPERIENCE = re.compile(r"(?:경력|경험|포트폴리오|프로젝트|학력|자격증)")


def section_source_role(section_type: Any) -> str:
    token = str(section_type or "").casefold()
    return {"duty": "DUTY", "required": "REQUIRED", "preferred": "PREFERRED"}.get(token, "OTHER")


def _chunk_type(section_type: Any, text: str) -> str:
    token = str(section_type or "").casefold()
    if token == "duty":
        return "DUTY"
    if token in {"required", "preferred", "qualification"}:
        if _KNOWLEDGE.search(text):
            return "KNOWLEDGE"
        if _SKILL.search(text):
            return "SKILL"
        if _EXPERIENCE.search(text):
            return "COMPETENCY_EXPERIENCE"
        return "REQUIREMENT"
    if token == "process":
        return "PROCESS"
    return "OTHER"


def _chunk_id(section_id: str, source_block_id: str, ordinal: int, text: str) -> str:
    digest = canonical_json_sha256([section_id, source_block_id, ordinal, normalize(text), CHUNKING_VERSION])
    return f"CHK_{digest[:24]}"


def build_semantic_chunk_bundle(
    sections: pd.DataFrame,
    source_block_links: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    joined = sections.merge(source_block_links, on="sectionId", how="left", validate="one_to_one")
    if joined["sourceBlockId"].isna().any():
        raise ValueError("every semantic chunk requires a sourceBlockId")
    chunks: list[dict[str, Any]] = []
    roles: list[dict[str, str]] = []
    for section in joined.sort_values(["trackId", "sectionOrdinal"]).to_dict(orient="records"):
        lines = [match.group(1).strip() for match in _LINE.finditer(str(section.get("sectionText") or ""))]
        lines = [line for line in lines if line]
        if not lines and str(section.get("sectionText") or "").strip():
            lines = [str(section["sectionText"]).strip()]
        source_role = section_source_role(section.get("sectionType"))
        for ordinal, text in enumerate(lines):
            chunk_type = _chunk_type(section.get("sectionType"), text)
            chunk_id = _chunk_id(str(section["sectionId"]), str(section["sourceBlockId"]), ordinal, text)
            chunks.append(
                {
                    "chunkId": chunk_id,
                    "trackId": str(section["trackId"]),
                    "sectionId": str(section["sectionId"]),
                    "sourceBlockId": str(section["sourceBlockId"]),
                    "chunkType": chunk_type,
                    "chunkText": text,
                    "normalizedText": normalize(text),
                    "ncsMappableFlag": chunk_type not in {"PROCESS", "OTHER"},
                    "chunkingVersion": CHUNKING_VERSION,
                }
            )
            roles.append({"chunkId": chunk_id, "sourceRole": source_role})
    chunk_frame = pd.DataFrame(chunks)
    role_frame = pd.DataFrame(roles)
    if len(chunk_frame) and chunk_frame["chunkId"].duplicated().any():
        raise ValueError("chunkId primary-key violation")
    return chunk_frame, role_frame


def build_semantic_chunks(sections: pd.DataFrame, source_block_links: pd.DataFrame) -> pd.DataFrame:
    chunks, _ = build_semantic_chunk_bundle(sections, source_block_links)
    return chunks
