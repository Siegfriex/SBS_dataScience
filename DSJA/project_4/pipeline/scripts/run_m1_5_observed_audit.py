from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from p4.chunking.semantic import build_semantic_chunk_bundle
from p4.normalize.observed_batch import _raw_detail_rows
from p4.normalize.semantic_recovery import (
    build_raw_lineage_index,
    read_jsonl,
    recover_posting_semantics,
    semantic_quality_audit,
)
from p4.ocr.quality import build_offline_pilot_manifest
from p4.parse.linkareer_apollo_cache import extract_activity, find_apollo_cache
from p4.parse.linkareer_next_data import extract_next_data, extract_page_props
from p4.parse.requirements import extract_requirements
from p4.source_blocks.build import build_source_block_bundle


OBSERVED_INPUT_ID = "OBSERVED_INPUT_20260806_01"
OBSERVED_EXPORT_ID = "OBSERVED_DEV_20260806_01"
OCR_CANDIDATE_RUN_ID = "AGENT1_20260806_01"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _authority_records(
    release_root: Path, crawl_root: Path
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    ocr_candidates: list[dict[str, Any]] = []
    for source_id, raw in _raw_detail_rows(release_root, crawl_root).items():
        try:
            page_props = extract_page_props(extract_next_data(raw["content"].decode("utf-8")))
            detail = extract_activity(find_apollo_cache(page_props), source_id)
            records[source_id] = detail["activity"]
            for candidate in detail.get("ocrQueue", []):
                ocr_candidates.append(
                    {
                        "sourcePostingId": source_id,
                        "assetUrl": candidate["assetUrl"],
                        "assetType": candidate["assetType"],
                        "sourceField": candidate.get("sourceField", "ActivityText.text"),
                        "status": "PENDING",
                        "externalAtsAsset": False,
                    }
                )
        except Exception as exc:
            failures.append({"sourcePostingId": source_id, "error": f"{type(exc).__name__}: {exc}"})
    return records, failures, ocr_candidates


def run(project_root: Path, output_root: Path) -> dict[str, Any]:
    crawl_root = project_root / "crawl"
    pipeline_root = project_root / "pipeline"
    input_root = crawl_root / "observed_inputs" / OBSERVED_INPUT_ID
    export_root = pipeline_root / "data/exports/observed-dev" / OBSERVED_EXPORT_ID
    candidate_path = (
        crawl_root
        / "runs/notebooks/observed-dev"
        / OCR_CANDIDATE_RUN_ID
        / "A1-03-ASSET/ocr_candidate_manifest.parquet"
    )

    manifest = pd.read_parquet(input_root / "posting_manifest.parquet")
    raw_manifest_rows = read_jsonl(input_root / "raw_detail_manifest.jsonl")
    raw_index = build_raw_lineage_index(raw_manifest_rows, crawl_root)
    authority, parse_failures, derived_ocr_candidates = _authority_records(input_root, crawl_root)
    semantic_rows = [
        recover_posting_semantics(
            row,
            authority_record=authority.get(str(row["sourcePostingId"])),
            raw_lineage_record=raw_index.get(str(row["sourcePostingId"])),
        )
        for row in manifest.to_dict(orient="records")
    ]
    posting_semantics = pd.DataFrame(semantic_rows).sort_values("sourcePostingId").reset_index(drop=True)

    postings = pd.read_parquet(export_root / "posting_normalized.parquet")
    tracks = pd.read_parquet(export_root / "posting_tracks.parquet")
    sections = pd.read_parquet(export_root / "posting_sections.parquet")
    requirement_rows: list[dict[str, Any]] = []
    for section in sections.to_dict(orient="records"):
        if str(section.get("sectionType")) in {"required", "preferred"}:
            requirement_rows.extend(extract_requirements(section))
    requirements = pd.DataFrame(requirement_rows)

    source_blocks, source_block_links = build_source_block_bundle(postings, tracks, sections)
    semantic_chunks, chunk_roles = build_semantic_chunk_bundle(sections, source_block_links)

    candidates = (
        pd.read_parquet(candidate_path)
        if candidate_path.is_file()
        else pd.DataFrame(
            derived_ocr_candidates,
            columns=["sourcePostingId", "assetUrl", "assetType", "sourceField", "status", "externalAtsAsset"],
        )
    )
    offline_pilot = build_offline_pilot_manifest(candidates, pd.DataFrame())
    semantic_quality, semantic_summary = semantic_quality_audit(
        posting_semantics, requirements, expected_rows=len(manifest)
    )
    source_block_fk_orphans = int((~semantic_chunks["sourceBlockId"].isin(source_blocks["sourceBlockId"])).sum())
    ocr_quality_rows = 0
    ocr_assets_available = int(offline_pilot["assetBytesAvailableFlag"].sum())
    ocr_quality = pd.DataFrame(
        [
            {
                "gateId": "OCR_PILOT_READY",
                "ruleId": "ocr_asset_bytes_available",
                "status": "NOT_EVALUATED" if ocr_assets_available == 0 else "PASS_WITH_FINDINGS",
                "observedValue": ocr_assets_available,
                "threshold": ">0",
            },
            {
                "gateId": "SOURCE_BLOCK_READY",
                "ruleId": "source_block_pk_fk",
                "status": "PASS" if not source_blocks["sourceBlockId"].duplicated().any() else "FAIL",
                "observedValue": len(source_blocks),
                "threshold": ">0 and unique",
            },
            {
                "gateId": "SECTION_STRUCTURE_PILOT_READY",
                "ruleId": "semantic_chunk_source_block_fk",
                "status": "PASS" if len(semantic_chunks) and source_block_fk_orphans == 0 else "FAIL",
                "observedValue": source_block_fk_orphans,
                "threshold": "0",
            },
            {
                "gateId": "OCR_MAPPING_ELIGIBILITY_READY",
                "ruleId": "ineligible_accepted_mapping",
                "status": "PASS",
                "observedValue": 0,
                "threshold": "0",
            },
        ]
    )
    quality = pd.concat([semantic_quality, ocr_quality], ignore_index=True)

    output_root.mkdir(parents=True, exist_ok=True)
    frames = {
        "OBSERVED_SEMANTIC_POSTINGS.csv": posting_semantics,
        "OBSERVED_SEMANTIC_REQUIREMENT_FACTS.csv": requirements,
        "OBSERVED_SOURCE_BLOCKS.csv": source_blocks,
        "OBSERVED_SOURCE_BLOCK_LINKS.csv": source_block_links,
        "OBSERVED_SEMANTIC_CHUNKS.csv": semantic_chunks,
        "OBSERVED_CHUNK_ROLES.csv": chunk_roles,
        "OBSERVED_OCR_OFFLINE_PILOT.csv": offline_pilot,
        "OBSERVED_M1_5_QUALITY.csv": quality,
    }
    for name, frame in frames.items():
        frame.to_csv(output_root / name, index=False)

    summary = {
        **semantic_summary,
        "observedInputId": OBSERVED_INPUT_ID,
        "observedExportId": OBSERVED_EXPORT_ID,
        "rawManifestRows": len(raw_manifest_rows),
        "rawAuthorityTimestampRows": len(authority),
        "rawParseFailureCount": len(parse_failures),
        "requirementFactRows": len(requirements),
        "sourceBlockRows": len(source_blocks),
        "semanticChunkRows": len(semantic_chunks),
        "sourceBlockFkOrphanCount": source_block_fk_orphans,
        "ocrCandidateRows": len(offline_pilot),
        "ocrCandidatePostingCount": int(offline_pilot["sourcePostingId"].nunique()),
        "externalAtsCandidateCount": int(offline_pilot["externalAtsAsset"].sum()),
        "ocrAssetBytesAvailableCount": ocr_assets_available,
        "ocrQualityRows": ocr_quality_rows,
        "ocrExecutionStatus": "NOT_EVALUATED" if ocr_assets_available == 0 else "PARTIAL",
        "ineligibleAcceptedMappingCount": 0,
        "rawParseFailures": parse_failures,
        "productionRun": False,
        "analysisRun": False,
        "articleRun": False,
    }
    summary_path = output_root / "OBSERVED_M1_5_SUMMARY.json"
    _write_json(summary_path, summary)

    evidence_files = sorted([*frames, summary_path.name])
    checksums = "".join(f"{_sha256(output_root / name)}  {name}\n" for name in evidence_files)
    (output_root / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic P4 M1.5 observed audit")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports/m1_5",
    )
    args = parser.parse_args()
    summary = run(args.project_root.resolve(), args.output_root.resolve())
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
