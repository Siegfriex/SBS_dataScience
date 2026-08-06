"""Render the five deterministic, thin Agent 4 M1 orchestration notebooks."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    ("00NcsSourceAudit.ipynb", "A4-00-NCS-SOURCE", "Audit the 13,442-row NCS source and hierarchy."),
    ("01BuildCoreAiItCodeSet.ipynb", "A4-01-CODESET", "Audit the 120-row review-required core AI/IT code set."),
    ("02BuildNcsRetrievalIndex.ipynb", "A4-02-RETRIEVAL", "Build the lexical-only retrieval index."),
    ("03MapObservedDuties.ipynb", "A4-03-MAP-OBSERVED", "Map observed duty rows to lexical top-5 candidates."),
    ("04ExportNcsMappingCsv.ipynb", "A4-04-EXPORT", "Export canonical Parquet and inspection CSV artifacts."),
]


def _cell_id(stage_id: str, label: str) -> str:
    return hashlib.sha256(f"{stage_id}:{label}".encode()).hexdigest()[:8]


def render() -> None:
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    notebook_dir = ROOT / "notebooks"
    notebook_dir.mkdir(parents=True, exist_ok=True)
    for filename, stage_id, description in STAGES:
        parameter_source = "\n".join([
            'RUN_MODE = "observed-dev"',
            'CONTRACT_VERSION = "2.1.2"',
            'CRAWL_RELEASE_ID = "CRAWL_20260806_03"',
            'DATA_VERSION = "observed-dev-20260806.1"',
            'AS_OF_DATE = "2026-08-06"',
            'RANDOM_SEED = 42',
            'DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"',
            'EMPIRICAL_ANALYSIS_ALLOWED = False',
            'PROMOTION_ALLOWED = False',
            'DUTY_INPUT_PATH = ""',
            'CONTROL_SCHEMA_DIR = ""',
        ])
        parameters = nbformat.v4.new_code_cell(
            parameter_source,
            metadata={"tags": ["parameters"]},
            id=_cell_id(stage_id, "parameters"),
        )
        bootstrap = nbformat.v4.new_code_cell(
            "from pathlib import Path\n"
            "import sys\n\n"
            "NCS_ROOT = Path.cwd().resolve()\n"
            "if NCS_ROOT.name != 'ncs_mapping':\n"
            "    raise RuntimeError('run this notebook with cwd=ncs_mapping')\n"
            "sys.path.insert(0, str(NCS_ROOT / 'src'))\n"
            "from p4_ncs.workflow.observed import run_stage",
            id=_cell_id(stage_id, "bootstrap"),
        )
        execute = nbformat.v4.new_code_cell(
            f"stage_manifest = run_stage(\n"
            f"    {stage_id!r},\n"
            "    root=NCS_ROOT,\n"
            "    duty_input_path=DUTY_INPUT_PATH or None,\n"
            "    schema_dir=CONTROL_SCHEMA_DIR or None,\n"
            ")\n"
            "stage_manifest",
            id=_cell_id(stage_id, "execute"),
        )
        notebook = nbformat.v4.new_notebook(
            cells=[parameters, bootstrap, execute],
            metadata={
                "agentId": "P4-A4-NCS",
                "branch": branch,
                "gitHead": git_head,
                "contractVersion": "2.1.2",
                "crawlReleaseId": "CRAWL_20260806_03",
                "dataVersion": "observed-dev-20260806.1",
                "runMode": "observed-dev",
                "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
                "empiricalAnalysisAllowed": False,
                "promotionAllowed": False,
                "stageId": stage_id,
                "description": description,
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "version": "3"},
            },
        )
        nbformat.write(notebook, notebook_dir / filename)


if __name__ == "__main__":
    render()
