"""Validate committed M1 artifacts against the current Agent 3 contracts."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import nbformat
import pandas as pd
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "data/runs/observed-dev/NCS_MAPPING_OBSERVED_20260806_01"
EXPORT_ROOT = ROOT / "data/exports/observed-dev/NCS_MAPPING_OBSERVED_20260806_01"
STAGES = [
    "A4-00-NCS-SOURCE", "A4-01-CODESET", "A4-02-RETRIEVAL",
    "A4-03-MAP-OBSERVED", "A4-04-EXPORT",
]
NOTEBOOKS = [
    "00NcsSourceAudit.ipynb", "01BuildCoreAiItCodeSet.ipynb",
    "02BuildNcsRetrievalIndex.ipynb", "03MapObservedDuties.ipynb",
    "04ExportNcsMappingCsv.ipynb",
]
TERMINATION = {"stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"}
QUALITY_COLUMNS = ["gateId", "ruleId", "severity", "status", "observedValue", "threshold", "evidencePath"]
EXPORTS = [
    "ncs_units", "core_ai_it_codes", "ncs_alias_dictionary",
    "posting_ncs_candidates", "posting_ncs_matches", "ncs_mapping_summary",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_schema = json.loads((args.schema_dir / "STAGE_MANIFEST.schema.json").read_text(encoding="utf-8"))
    metrics_schema = json.loads((args.schema_dir / "STAGE_METRICS.schema.json").read_text(encoding="utf-8"))
    for stage in STAGES:
        stage_root = RUN_ROOT / stage
        assert {path.name for path in stage_root.iterdir() if path.is_file()} == TERMINATION
        manifest = json.loads((stage_root / "stage_manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((stage_root / "stage_metrics.json").read_text(encoding="utf-8"))
        Draft202012Validator(manifest_schema).validate(manifest)
        Draft202012Validator(metrics_schema).validate(metrics)
        quality = pd.read_csv(stage_root / "stage_quality.csv", encoding="utf-8-sig")
        assert quality.columns.tolist() == QUALITY_COLUMNS
        for line in (stage_root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
            expected, name = line.split(None, 1)
            assert _sha(stage_root / name.strip()) == expected
    for name in NOTEBOOKS:
        notebook = nbformat.read(ROOT / "notebooks" / name, as_version=4)
        nbformat.validate(notebook)
        assert notebook.cells[0].cell_type == "code"
        assert "parameters" in notebook.cells[0].metadata.get("tags", [])
        for cell in notebook.cells:
            if cell.cell_type == "code":
                ast.parse(cell.source)
                assert cell.execution_count is None
                assert cell.outputs == []
    for stem in EXPORTS:
        parquet = pd.read_parquet(EXPORT_ROOT / f"{stem}.parquet").astype("string").fillna("")
        csv = pd.read_csv(EXPORT_ROOT / f"{stem}.csv", dtype="string", keep_default_na=False).fillna("")
        pd.testing.assert_frame_equal(parquet.reset_index(drop=True), csv.reset_index(drop=True), check_dtype=False)
    print("PASS Agent3 schemas=10 stageDirs=5 notebooks=5 exports=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
