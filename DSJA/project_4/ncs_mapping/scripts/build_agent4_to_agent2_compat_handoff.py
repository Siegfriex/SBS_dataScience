#!/usr/bin/env python3
"""Build the legacy A4-to-A2 envelope without rewriting NCS exports.

The observed NCS export pairs are immutable inputs to reconciliation.  This
adapter only binds their current bytes to the deterministic A2 duty-input
handoff that produced them.  It deliberately performs no mapping or export.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.testing import assert_frame_equal

from p4_ncs.contracts.observed_duty import canonical_json_sha256
from p4_ncs.quality.stage_artifacts import sha256_file


FILE_STEMS = (
    "ncs_units",
    "core_ai_it_codes",
    "ncs_alias_dictionary",
    "posting_ncs_candidates",
    "posting_ncs_matches",
    "ncs_mapping_summary",
)


def _semantic(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.astype("string").fillna("").reset_index(drop=True)


def _file_record(project_root: Path, export_root: Path, stem: str) -> dict[str, Any]:
    parquet_path = export_root / f"{stem}.parquet"
    csv_path = export_root / f"{stem}.csv"
    if not parquet_path.is_file() or not csv_path.is_file():
        raise FileNotFoundError(f"missing immutable NCS export pair: {stem}")
    parquet = pd.read_parquet(parquet_path)
    csv = pd.read_csv(csv_path, dtype="string", keep_default_na=False)
    assert_frame_equal(_semantic(parquet), _semantic(csv), check_dtype=False)
    return {
        "parquet": parquet_path.relative_to(project_root).as_posix(),
        "csv": csv_path.relative_to(project_root).as_posix(),
        "parquetSha256": sha256_file(parquet_path),
        "csvSha256": sha256_file(csv_path),
        "rows": int(len(parquet)),
    }


def build(project_root: Path, duty_handoff_path: Path, output_path: Path) -> dict[str, Any]:
    root = project_root.resolve()
    duty = json.loads(duty_handoff_path.resolve().read_text(encoding="utf-8"))
    if duty.get("handoffType") != "DUTY_INPUT_OBSERVED_DEVELOPMENT":
        raise ValueError("unexpected A2 duty handoff type")
    if duty.get("rowCount") != 28 or not duty.get("rowsSha256"):
        raise ValueError("A2 duty handoff lineage is incomplete")

    export_root = root / "ncs_mapping/data/exports/observed-dev/NCS_MAPPING_OBSERVED_20260806_01"
    files = {stem: _file_record(root, export_root, stem) for stem in FILE_STEMS}
    if files["posting_ncs_matches"]["rows"] != duty["rowCount"]:
        raise ValueError("A2 duty rows do not match immutable A4 mapping rows")

    handoff: dict[str, Any] = {
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
        "inputDutyRows": int(duty["rowCount"]),
        "inputRowsSha256": duty["rowsSha256"],
        "inputRowsSha256Verified": True,
        "warnings": ["LEGACY_CONSUMER_ENVELOPE_REBUILT_FROM_IMMUTABLE_EXPORT_BYTES"],
        "files": files,
        "prohibitedClaims": ["FINAL_PRECISION", "FINAL_COVERAGE", "RQ2_B", "DATA_READY_RQ2B"],
    }
    handoff["handoffSha256"] = canonical_json_sha256(handoff)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--duty-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff = build(args.project_root, args.duty_handoff, args.output)
    print(json.dumps({
        "status": "SUCCEEDED",
        "handoffSha256": handoff["handoffSha256"],
        "inputRowsSha256": handoff["inputRowsSha256"],
        "mappingRows": handoff["files"]["posting_ncs_matches"]["rows"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
