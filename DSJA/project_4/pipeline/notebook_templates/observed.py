from __future__ import annotations

import hashlib

import nbformat


PARAMETERS = '''RUN_MODE = "observed-dev"  # observed-dev | production
CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_VERSION = "observed-dev-20260806.1"
AS_OF_DATE = "2026-08-06"
RANDOM_SEED = 42
DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"
EMPIRICAL_ANALYSIS_ALLOWED = False
PROMOTION_ALLOWED = False
PROJECT_ROOT = None
RELEASE_ROOT = None
OUTPUT_ROOT = None'''


BOOTSTRAP = '''from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pipeline/pyproject.toml").exists() and (candidate / "pipeline/src/p4").exists():
            return candidate
    raise RuntimeError("project root not found")

PROJECT_ROOT = Path(PROJECT_ROOT).resolve() if PROJECT_ROOT else find_project_root(Path.cwd().resolve())
PIPELINE_ROOT = PROJECT_ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE_ROOT / "src"))
RELEASE_ROOT = Path(RELEASE_ROOT).resolve() if RELEASE_ROOT else PROJECT_ROOT / "crawl/observed_inputs/OBSERVED_INPUT_20260806_01"
CRAWL_ROOT = Path(os.environ.get("P4_CRAWL_ROOT", PROJECT_ROOT / "crawl")).resolve()
OUTPUT_ROOT = Path(OUTPUT_ROOT).resolve() if OUTPUT_ROOT else PIPELINE_ROOT / "data/exports/observed-dev/OBSERVED_DEV_20260806_01"
CONTROL_ROOT = Path(os.environ.get("P4_CONTROL_ROOT", PROJECT_ROOT / "crawl/control")).resolve()
NCS_PROJECT_ROOT = Path(os.environ.get("P4_NCS_PROJECT_ROOT", PROJECT_ROOT)).resolve()
NCS_HANDOFF_PATH = Path(os.environ.get("P4_NCS_HANDOFF_PATH", NCS_PROJECT_ROOT / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json")).resolve()
RUN_ROOT = Path(os.environ.get("P4_NOTEBOOK_RUN_ROOT", PIPELINE_ROOT / "runs/notebooks/observed-dev/AGENT2_20260806_01")).resolve()
BRANCH = subprocess.check_output(["git", "branch", "--show-current"], cwd=PROJECT_ROOT, text=True).strip()
GIT_HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
METADATA = {
    "agentId": "P4-A2-PIPELINE", "branch": BRANCH, "gitHead": GIT_HEAD,
    "contractVersion": CONTRACT_VERSION, "crawlReleaseId": CRAWL_RELEASE_ID,
    "dataVersion": DATA_VERSION, "runMode": RUN_MODE, "dataProvenance": DATA_PROVENANCE,
    "asOfDate": AS_OF_DATE, "randomSeed": RANDOM_SEED,
    "startedAt": datetime.now(timezone.utc).isoformat(),
    "inputManifestPath": "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/HANDOFF.json",
    "outputRoot": "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01",
    "empiricalAnalysisAllowed": EMPIRICAL_ANALYSIS_ALLOWED, "promotionAllowed": PROMOTION_ALLOWED,
    "storagePolicy": {"canonical": "DUCKDB_PARQUET", "inspectionExport": "CSV_UTF8_SIG"},
    "eligibilityColumns": ["postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag"],
    "highDemandScorePolicy": "ALL_NULL",
    "ksaPolicy": {"decisionId": "D-023", "status": "PROVISIONAL", "mode": "OPTIONAL_ENRICHMENT", "blocksM1": False},
    "mappingPolicy": {"mappingMode": "LEXICAL_BASELINE", "codeSetStatus": "REVIEW_REQUIRED", "goldValidatedFlag": False, "denseScore": None},
}
assert RUN_MODE == "observed-dev"
assert DATA_PROVENANCE == "OBSERVED_DEVELOPMENT_ONLY"
assert EMPIRICAL_ANALYSIS_ALLOWED is False and PROMOTION_ALLOWED is False
if (CONTROL_ROOT / "NOTEBOOK_EXECUTION_CONTRACT.schema.json").is_file():
    import jsonschema
    schema = json.loads((CONTROL_ROOT / "NOTEBOOK_EXECUTION_CONTRACT.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(METADATA)
print(json.dumps(METADATA, ensure_ascii=False, indent=2))'''


RUNNERS = {
    "00ContractAndInputAudit": "run_contract_and_input_audit_stage",
    "01LoadCrawlRelease": "run_load_crawl_release_stage",
    "02ParseAndNormalize": "run_parse_and_normalize_stage",
    "03OcrAndSectionRecovery": "run_ocr_and_section_recovery_stage",
    "04SplitTracks": "run_split_tracks_stage",
    "05ExtractRequirements": "run_extract_requirements_stage",
    "06Deduplicate90Days": "run_deduplicate_90_days_stage",
    "07LabelCareerAccess": "run_label_career_access_stage",
    "08LoadAndPrepareNcs": "run_load_and_prepare_ncs_stage",
    "09MapPostingToNcs": "run_map_posting_to_ncs_stage",
    "10ExportPreprocessedCsv": "run_export_preprocessed_csv_stage",
    "11PreprocessedDataQa": "run_preprocessed_data_qa_stage",
}


def _cell_id(stage_id: str, role: str) -> str:
    return hashlib.sha256(f"{stage_id}:{role}".encode()).hexdigest()[:16]


def make_notebook(
    stage_id: str,
    registry_stage_id: str,
    title: str,
    note: str,
    inputs: list[str],
    outputs: list[str],
) -> nbformat.NotebookNode:
    notebook = nbformat.v4.new_notebook()
    notebook.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "p4": {"mode": "observed-dev", "agentId": "P4-A2-PIPELINE", "stage": stage_id, "stageId": registry_stage_id},
        }
    )
    title_cell = f'''# P4 Notebook-First · {registry_stage_id}

## {title}

| Field | Value |
|---|---|
| Agent | `P4-A2-PIPELINE` |
| Run mode | `observed-dev` |
| Contract | `2.1.2` |
| Provenance | `OBSERVED_DEVELOPMENT_ONLY` |
| Empirical / promotion | `false / false` |

{note}'''
    io_cell = "## Stage contract\n\n**Inputs**\n\n" + "\n".join(f"- `{value}`" for value in inputs) + "\n\n**Outputs**\n\n" + "\n".join(f"- `{value}`" for value in outputs)
    audit = f'''from p4.notebooks.observed_stages import audit_observed_stage_inputs
STAGE = {stage_id!r}
INPUT_AUDIT = audit_observed_stage_inputs(
    STAGE,
    project_root=PROJECT_ROOT,
    release_root=RELEASE_ROOT,
    ncs_handoff_path=NCS_HANDOFF_PATH,
)
assert INPUT_AUDIT["missingInputCount"] == 0
print(json.dumps(INPUT_AUDIT, ensure_ascii=False, indent=2))'''
    runner = RUNNERS[stage_id]
    run = f'''from p4.notebooks.observed_stages import {runner}
RESULT = {runner}(
    project_root=PROJECT_ROOT,
    release_root=RELEASE_ROOT,
    crawl_root=CRAWL_ROOT,
    output_root=OUTPUT_ROOT,
    control_root=CONTROL_ROOT,
    ncs_handoff_path=NCS_HANDOFF_PATH,
    ncs_project_root=NCS_PROJECT_ROOT,
    run_root=RUN_ROOT,
)
assert RESULT["qualityStatus"] == "PASS", RESULT
print(json.dumps(RESULT, ensure_ascii=False, indent=2))'''
    summary = '''from IPython.display import display
import pandas as pd

SUMMARY = pd.DataFrame([
    {"field": "stage", "value": STAGE},
    {"field": "qualityStatus", "value": RESULT["qualityStatus"]},
    {"field": "stageManifest", "value": RESULT["stageManifest"]},
    {"field": "stageMetrics", "value": RESULT["stageMetrics"]},
    {"field": "stageQuality", "value": RESULT["stageQuality"]},
    {"field": "checksums", "value": RESULT["checksums"]},
])
display(SUMMARY)'''
    terminal = '''REQUIRED_TERMINATION_ARTIFACTS = (
    "stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256",
)
artifact_root = RUN_ROOT / "artifacts" / STAGE
missing = [name for name in REQUIRED_TERMINATION_ARTIFACTS if not (artifact_root / name).is_file()]
assert not missing, missing
assert RESULT["qualityStatus"] == "PASS"
print(json.dumps({
    "stage": STAGE,
    "terminationArtifacts": list(REQUIRED_TERMINATION_ARTIFACTS),
    "artifactRoot": str(artifact_root.relative_to(PROJECT_ROOT)),
    "empiricalAnalysisAllowed": False,
    "promotionAllowed": False,
}, ensure_ascii=False, indent=2))'''
    notebook.cells = [
        nbformat.v4.new_code_cell(PARAMETERS, id=_cell_id(stage_id, "parameters"), metadata={"tags": ["parameters"]}),
        nbformat.v4.new_markdown_cell(title_cell, id=_cell_id(stage_id, "title")),
        nbformat.v4.new_code_cell(BOOTSTRAP, id=_cell_id(stage_id, "bootstrap")),
        nbformat.v4.new_markdown_cell(io_cell, id=_cell_id(stage_id, "contract")),
        nbformat.v4.new_code_cell(audit, id=_cell_id(stage_id, "input-audit")),
        nbformat.v4.new_markdown_cell("## Execute versioned stage module", id=_cell_id(stage_id, "execute-title")),
        nbformat.v4.new_code_cell(run, id=_cell_id(stage_id, "run")),
        nbformat.v4.new_markdown_cell("## Stage summary", id=_cell_id(stage_id, "summary-title")),
        nbformat.v4.new_code_cell(summary, id=_cell_id(stage_id, "summary")),
        nbformat.v4.new_markdown_cell("## Termination contract", id=_cell_id(stage_id, "terminal-title")),
        nbformat.v4.new_code_cell(terminal, id=_cell_id(stage_id, "terminal")),
    ]
    return notebook
