"""Render deterministic, output-free Agent 1 orchestration notebooks."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = ROOT / "notebooks"

PARAMETERS = '''RUN_MODE = "observed-dev"  # observed-dev | production
CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_VERSION = "OBSERVED_DEV_20260806_01"
AS_OF_DATE = "2026-08-06"
RANDOM_SEED = 42
RUN_ID = "E2E_20260806_RESUME_01"
EXECUTE_LIVE = False
MAX_ITEMS = 0
STARTED_AT = "2026-08-06T00:00:00+09:00"'''

BOOTSTRAP = '''from pathlib import Path
import sys

def locate_project_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "crawl" / "src" / "p4_crawl").is_dir():
            return candidate
        nested = candidate / "DSJA" / "project_4"
        if (nested / "crawl" / "src" / "p4_crawl").is_dir():
            return nested
    raise RuntimeError("Could not locate DSJA/project_4")

PROJECT_ROOT = locate_project_root(Path.cwd())
sys.path.insert(0, str(PROJECT_ROOT / "crawl" / "src"))
from p4_crawl.config import RunConfig
from p4_crawl.stage import write_stage_artifacts

config = RunConfig(
    project_root=PROJECT_ROOT,
    run_id=RUN_ID,
    run_mode=RUN_MODE,
    contract_version=CONTRACT_VERSION,
    crawl_release_id=CRAWL_RELEASE_ID,
    data_version=DATA_VERSION,
    as_of_date=AS_OF_DATE,
    random_seed=RANDOM_SEED,
    execute_live=EXECUTE_LIVE,
)'''

STAGES = {
    "00RecoverSourceState": '''from p4_crawl.release import recover_source_state

metrics = recover_source_state(config)
quality = [
    {"gate": "run_mode", "status": "PASS" if RUN_MODE == "observed-dev" else "FAIL", "detail": RUN_MODE},
    {"gate": "raw_lineage", "status": "PASS" if metrics["rawHtmlRows"] > 0 else "FAIL", "detail": metrics["rawHtmlRows"]},
]
stage_root = write_stage_artifacts(config, "A1-00", STARTED_AT, metrics, quality,
    inputs=[f"crawl/releases/{CRAWL_RELEASE_ID}"],
    outputs=["resume_state.json", "remaining_months.csv", "detail_frontier.parquet", "asset_frontier.parquet"])
metrics''',
    "01CollectLinkareerIndex": '''from p4_crawl.query_registry import QueryRegistry

registry = QueryRegistry.load(PROJECT_ROOT / "crawl" / "configs" / "queryRegistry.yaml")
if EXECUTE_LIVE:
    from p4_crawl.cli import main as crawl_cli
    crawl_cli(["--project-root", str(PROJECT_ROOT), "--run-id", RUN_ID, "--run-mode", RUN_MODE,
        "--crawl-release-id", CRAWL_RELEASE_ID, "--execute-live", "index", "--max-items", str(MAX_ITEMS)])
metrics = {"registeredOperations": list(registry.names()), "liveExecuted": EXECUTE_LIVE, "status": "M1_NO_LIVE_CRAWL" if not EXECUTE_LIVE else "LIVE_EXECUTED"}
quality = [
    {"gate": "query_registry", "status": "PASS", "detail": len(registry.names())},
    {"gate": "no_live_m1", "status": "PASS" if not EXECUTE_LIVE else "FAIL", "detail": EXECUTE_LIVE},
]
stage_root = write_stage_artifacts(config, "A1-01", STARTED_AT, metrics, quality,
    inputs=["crawl/configs/queryRegistry.yaml"],
    outputs=["posting_discovery_index.parquet", "monthly_coverage.parquet", "index_fetch_manifest.jsonl"])
metrics''',
    "02CollectPostingDetail": '''from p4_crawl.manifests import load_jsonl

raw_manifest = PROJECT_ROOT / "crawl" / "observed_inputs" / "OBSERVED_INPUT_20260806_01" / "raw_detail_manifest.jsonl"
rows = load_jsonl(raw_manifest)
if EXECUTE_LIVE:
    from p4_crawl.cli import main as crawl_cli
    crawl_cli(["--project-root", str(PROJECT_ROOT), "--run-id", RUN_ID, "--run-mode", RUN_MODE,
        "--crawl-release-id", CRAWL_RELEASE_ID, "--execute-live", "detail", "--max-items", str(MAX_ITEMS)])
metrics = {"observedRawHtmlRows": len(rows), "liveExecuted": EXECUTE_LIVE, "status": "OBSERVED_DETAIL_LINEAGE_READY"}
quality = [
    {"gate": "raw_detail_rows", "status": "PASS" if len(rows) == 29 else "FAIL", "detail": len(rows)},
    {"gate": "no_live_m1", "status": "PASS" if not EXECUTE_LIVE else "FAIL", "detail": EXECUTE_LIVE},
]
stage_root = write_stage_artifacts(config, "A1-02", STARTED_AT, metrics, quality,
    inputs=[str(raw_manifest.relative_to(PROJECT_ROOT))],
    outputs=["posting_manifest.parquet", "detail_fetch_manifest.jsonl"])
metrics''',
    "03CollectPostingAssets": '''from p4_crawl.manifests import load_jsonl

asset_manifest = PROJECT_ROOT / "crawl" / "releases" / CRAWL_RELEASE_ID / "asset_manifest.jsonl"
rows = load_jsonl(asset_manifest)
if EXECUTE_LIVE:
    from p4_crawl.cli import main as crawl_cli
    crawl_cli(["--project-root", str(PROJECT_ROOT), "--run-id", RUN_ID, "--run-mode", RUN_MODE,
        "--crawl-release-id", CRAWL_RELEASE_ID, "--execute-live", "assets", "--max-items", str(MAX_ITEMS)])
metrics = {"observedAssetRows": len(rows), "liveExecuted": EXECUTE_LIVE, "status": "ASSET_GAP_DECLARED"}
quality = [
    {"gate": "asset_gap_explicit", "status": "PASS" if len(rows) == 0 else "FAIL", "detail": len(rows)},
    {"gate": "no_live_m1", "status": "PASS" if not EXECUTE_LIVE else "FAIL", "detail": EXECUTE_LIVE},
]
stage_root = write_stage_artifacts(config, "A1-03", STARTED_AT, metrics, quality,
    inputs=[str(asset_manifest.relative_to(PROJECT_ROOT))],
    outputs=["asset_manifest.jsonl", "ocr_candidate_manifest.parquet"])
metrics''',
    "04BuildCrawlRelease": '''from p4_crawl.release import crawl_release_readiness

metrics = crawl_release_readiness(config)
quality = [
    {"gate": "production_promotion_blocked", "status": "PASS" if not metrics["releaseReady"] else "FAIL", "detail": metrics["status"]},
    {"gate": "observed_only", "status": "PASS" if RUN_MODE == "observed-dev" else "FAIL", "detail": RUN_MODE},
]
stage_root = write_stage_artifacts(config, "A1-04", STARTED_AT, metrics, quality,
    inputs=[f"crawl/releases/{CRAWL_RELEASE_ID}"], outputs=[])
metrics''',
}


def render() -> None:
    NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    for name, body in STAGES.items():
        prefix = name[:2]
        cells = [
            new_code_cell(PARAMETERS, metadata={"tags": ["parameters"]}, id=f"p4-a1-{prefix}-params"),
            new_markdown_cell(f"# {name}\n\nThin orchestration notebook for `p4_crawl`.", id=f"p4-a1-{prefix}-title"),
            new_code_cell(BOOTSTRAP, id=f"p4-a1-{prefix}-bootstrap"),
            new_code_cell(body, id=f"p4-a1-{prefix}-run"),
        ]
        notebook = new_notebook(
            cells=cells,
            metadata={
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "version": "3.12"},
            },
        )
        nbformat.validate(notebook)
        nbformat.write(notebook, NOTEBOOK_ROOT / f"{name}.ipynb", version=4)


if __name__ == "__main__":
    render()
