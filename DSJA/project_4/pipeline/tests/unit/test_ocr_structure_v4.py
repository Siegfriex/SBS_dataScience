from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from p4.chunking.semantic import build_semantic_chunk_bundle
from p4.ocr.quality import (
    build_offline_pilot_manifest,
    compute_ocr_quality,
    count_ineligible_accepted_mappings,
)
from p4.source_blocks.build import build_source_block_bundle, legacy_source_mode


def _observed_frames():
    postings = pd.DataFrame(
        [
            {
                "postingId": "PST_1",
                "rawPostingId": "RAW_1",
                "bodyText": "데이터 분석 및 모델 개발",
                "inputSha256": "a" * 64,
                "parseVersion": "parse-v1",
            }
        ]
    )
    tracks = pd.DataFrame([{"trackId": "TRK_1", "postingId": "PST_1"}])
    sections = pd.DataFrame(
        [
            {
                "sectionId": "SEC_1",
                "trackId": "TRK_1",
                "sectionType": "duty",
                "sectionOrdinal": 0,
                "sectionText": "데이터 분석\n모델 개발",
                "sourceMode": "SSR_ACTIVITY_TEXT",
            }
        ]
    )
    return postings, tracks, sections


def test_source_blocks_keep_addendum_uppercase_and_legacy_adapter():
    blocks, links = build_source_block_bundle(*_observed_frames())
    assert blocks.loc[0, "sourceMode"] == "ACTIVITY_TEXT"
    assert legacy_source_mode("ACTIVITY_TEXT") == "html"
    assert links.loc[0, "sourceBlockId"] == blocks.loc[0, "sourceBlockId"]
    assert len(blocks.loc[0, "rawSha256"]) == 64


def _validate_schema(name: str, record: dict):
    schema_path = Path(__file__).parents[3] / f"shared/contracts/semantic_ncs_reference/v4.0/schemas/{name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(record)


def test_chunking_links_every_chunk_to_source_block_and_role():
    postings, tracks, sections = _observed_frames()
    _, links = build_source_block_bundle(postings, tracks, sections)
    chunks, roles = build_semantic_chunk_bundle(sections, links)
    assert len(chunks) == 2
    assert set(chunks["chunkType"]) == {"DUTY"}
    assert chunks["sourceBlockId"].notna().all()
    assert set(roles["sourceRole"]) == {"DUTY"}
    block_record = json.loads(build_source_block_bundle(postings, tracks, sections)[0].to_json(orient="records"))[0]
    chunk_record = json.loads(chunks.to_json(orient="records"))[0]
    _validate_schema("source_block", block_record)
    _validate_schema("semantic_chunk", chunk_record)


def test_offline_pilot_is_not_evaluated_without_asset_bytes():
    candidates = pd.DataFrame(
        [
            {
                "sourcePostingId": "1",
                "assetUrl": "https://api.linkareer.com/attachments/1",
                "assetType": "embeddedActivityTextImage",
                "sourceField": "ActivityText.text",
                "externalAtsAsset": False,
            }
        ]
    )
    pilot = build_offline_pilot_manifest(candidates)
    assert pilot.loc[0, "ocrExecutionStatus"] == "NOT_EVALUATED"
    assert pilot.loc[0, "ocrExecutionReason"] == "ASSET_BYTES_NOT_AVAILABLE"
    assert not pilot.loc[0, "externalAtsAsset"]


def test_ocr_quality_and_ineligible_mapping_enforcement():
    quality = compute_ocr_quality(
        asset_id="AST_1",
        ocr_run_id="OCR_RUN_1",
        engine="fixture",
        engine_version="1",
        text="짧음",
        layout_type="TABLE",
        line_order_confidence=0.2,
    )
    assert quality["ocrEligibleForMapping"] is False
    assert "OCR_TABLE_MULTICOLUMN_LINE_ORDER_RISK" in quality["qualityReasonCodesJson"]
    _validate_schema("ocr_quality", quality)
    mappings = pd.DataFrame([{"chunkId": "CHK_1", "mappingStatus": "ACCEPTED_SINGLE"}])
    chunks = pd.DataFrame([{"chunkId": "CHK_1", "sourceBlockId": "SBK_1"}])
    blocks = pd.DataFrame([{"sourceBlockId": "SBK_1", "sourceMode": "OCR", "assetId": "AST_1"}])
    quality_frame = pd.DataFrame([quality])
    assert count_ineligible_accepted_mappings(mappings, chunks, blocks, quality_frame) == 1
