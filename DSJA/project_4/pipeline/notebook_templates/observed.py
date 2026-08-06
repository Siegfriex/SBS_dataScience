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
CRAWL_ROOT = None
OUTPUT_ROOT = None
CONTROL_ROOT = None
NCS_HANDOFF_PATH = None
NCS_PROJECT_ROOT = None'''

BOOTSTRAP = '''from pathlib import Path
import json, subprocess, sys

def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pipeline/pyproject.toml").exists() and (candidate / "pipeline/src/p4").exists():
            return candidate
    raise RuntimeError("project root not found")

PROJECT_ROOT = Path(PROJECT_ROOT).resolve() if PROJECT_ROOT else find_project_root(Path.cwd().resolve())
PIPELINE_ROOT = PROJECT_ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE_ROOT / "src"))
BRANCH = subprocess.check_output(["git", "branch", "--show-current"], cwd=PROJECT_ROOT, text=True).strip()
GIT_HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
RELEASE_ROOT = Path(RELEASE_ROOT).resolve() if RELEASE_ROOT else PROJECT_ROOT / "crawl/observed_inputs/OBSERVED_INPUT_20260806_01"
CRAWL_ROOT = Path(CRAWL_ROOT).resolve() if CRAWL_ROOT else PROJECT_ROOT / "crawl"
OUTPUT_ROOT = Path(OUTPUT_ROOT).resolve() if OUTPUT_ROOT else PIPELINE_ROOT / "data/exports/observed-dev/OBSERVED_DEV_20260806_01"
CONTROL_ROOT = Path(CONTROL_ROOT).resolve() if CONTROL_ROOT else PROJECT_ROOT / "crawl/control"
NCS_HANDOFF_PATH = Path(NCS_HANDOFF_PATH).resolve() if NCS_HANDOFF_PATH else PROJECT_ROOT / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"
NCS_PROJECT_ROOT = Path(NCS_PROJECT_ROOT).resolve() if NCS_PROJECT_ROOT else PROJECT_ROOT
METADATA = {
    "agentId": "P4-A2-PIPELINE",
    "branch": BRANCH,
    "gitHead": GIT_HEAD,
    "contractVersion": CONTRACT_VERSION,
    "crawlReleaseId": CRAWL_RELEASE_ID,
    "dataVersion": DATA_VERSION,
    "runMode": RUN_MODE,
    "dataProvenance": DATA_PROVENANCE,
    "asOfDate": AS_OF_DATE,
    "randomSeed": RANDOM_SEED,
    "startedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "inputManifestPath": "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/HANDOFF.json",
    "outputRoot": "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01",
    "empiricalAnalysisAllowed": EMPIRICAL_ANALYSIS_ALLOWED,
    "promotionAllowed": PROMOTION_ALLOWED,
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


def _cell_id(stage_id: str, role: str) -> str:
    return hashlib.sha256(f"{stage_id}:{role}".encode()).hexdigest()[:16]


def make_notebook(stage_id: str, registry_stage_id: str, title: str, note: str) -> nbformat.NotebookNode:
    notebook = nbformat.v4.new_notebook()
    notebook.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "p4": {
                "mode": "observed-dev",
                "agentId": "P4-A2-PIPELINE",
                "stage": stage_id,
                "stageId": registry_stage_id,
            },
        }
    )
    run = f'''from p4.notebooks.observed_stages import run_observed_stage
STAGE = {stage_id!r}
RESULT = run_observed_stage(
    STAGE,
    project_root=PROJECT_ROOT,
    release_root=RELEASE_ROOT,
    crawl_root=CRAWL_ROOT,
    output_root=OUTPUT_ROOT,
    control_root=CONTROL_ROOT,
    ncs_handoff_path=NCS_HANDOFF_PATH,
    ncs_project_root=NCS_PROJECT_ROOT,
)
print(json.dumps(RESULT, ensure_ascii=False, indent=2))'''
    terminal = '''REQUIRED_TERMINATION_ARTIFACTS = (
    "stage_manifest.json",
    "stage_metrics.json",
    "stage_quality.csv",
    "CHECKSUMS.sha256",
)
assert RESULT["qualityStatus"] in {"PASS", "FAIL"}
assert all(RESULT[key] for key in ("stageManifest", "stageMetrics", "stageQuality", "checksums"))
print(json.dumps({"stage": STAGE, "terminationArtifacts": REQUIRED_TERMINATION_ARTIFACTS, **RESULT}, ensure_ascii=False, indent=2))'''
    notebook.cells = [
        nbformat.v4.new_code_cell(PARAMETERS, id=_cell_id(stage_id, "parameters"), metadata={"tags": ["parameters"]}),
        nbformat.v4.new_markdown_cell(f"# {title}\n\n{note}", id=_cell_id(stage_id, "title")),
        nbformat.v4.new_code_cell(BOOTSTRAP, id=_cell_id(stage_id, "bootstrap")),
        nbformat.v4.new_code_cell(run, id=_cell_id(stage_id, "run")),
        nbformat.v4.new_code_cell(terminal, id=_cell_id(stage_id, "terminal")),
    ]
    return notebook
