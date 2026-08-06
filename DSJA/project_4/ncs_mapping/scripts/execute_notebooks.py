"""Execute six source notebooks in fresh kernels and save separate run copies."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "AGENT4_20260806_01"
RUN_ROOT = ROOT / "runs" / "notebooks" / "observed-dev" / RUN_ID
NOTEBOOKS = [
    ("00NcsSourceAudit.ipynb", "A4-00-NCS-SOURCE"),
    ("01BuildCoreAiItCodeSet.ipynb", "A4-01-CODESET"),
    ("02BuildNcsRetrievalIndex.ipynb", "A4-02-RETRIEVAL"),
    ("03MapObservedDuties.ipynb", "A4-03-MAP-OBSERVED"),
    ("04ExportNcsMappingCsv.ipynb", "A4-04-EXPORT"),
    ("05EvaluateNcsMapping.ipynb", "A4-05-EVALUATE"),
]
STAGE_ROOT = ROOT / "data" / "runs" / "observed-dev" / "NCS_MAPPING_OBSERVED_20260806_01"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if RUN_ROOT.exists():
        raise FileExistsError(f"run output already exists: {RUN_ROOT}")
    executed_root = RUN_ROOT / "executed"
    artifacts_root = RUN_ROOT / "artifacts"
    executed_root.mkdir(parents=True)
    artifacts_root.mkdir(parents=True)
    inventory = []
    for name, stage_id in NOTEBOOKS:
        source_path = ROOT / "notebooks" / name
        notebook = nbformat.read(source_path, as_version=4)
        executed = NotebookClient(
            notebook,
            timeout=180,
            kernel_name="python3",
            resources={"metadata": {"path": str(ROOT)}},
        ).execute(cwd=str(ROOT))
        executed_path = executed_root / name
        nbformat.write(executed, executed_path)
        source_after = nbformat.read(source_path, as_version=4)
        assert all(not cell.get("outputs") for cell in source_after.cells if cell.cell_type == "code")
        source_stage_root = STAGE_ROOT / stage_id
        target_stage_root = artifacts_root / stage_id
        target_stage_root.mkdir()
        for artifact_name in ("stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"):
            shutil.copy2(source_stage_root / artifact_name, target_stage_root / artifact_name)
        assert {path.name for path in target_stage_root.iterdir()} == {
            "stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"
        }
        inventory.append({
            "notebook": f"executed/{name}",
            "notebookSha256": _sha256(executed_path),
            "stageId": stage_id,
            "stageStatus": json.loads((target_stage_root / "stage_manifest.json").read_text(encoding="utf-8"))["status"],
            "artifactRoot": f"artifacts/{stage_id}",
        })
        print(f"PASS {name}")
    run_manifest = {
        "runId": RUN_ID,
        "runMode": "observed-dev",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "sourceNotebookOutputCount": 0,
        "notebooks": inventory,
    }
    (RUN_ROOT / "RUN_MANIFEST.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
