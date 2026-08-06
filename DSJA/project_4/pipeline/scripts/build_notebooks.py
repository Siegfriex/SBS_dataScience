from __future__ import annotations

from pathlib import Path

import nbformat as nbf


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"
FIXTURE_NOTEBOOK_ROOT = NOTEBOOK_ROOT / "fixture"


NOTEBOOKS = [
    ("00ContractAndInputAudit.ipynb", "Contract and input audit", "contract/input presence; no empirical rows"),
    ("01LoadCrawlRelease.ipynb", "Load crawl release", "official CRAWL_ release validation"),
    ("02ParseAndNormalize.ipynb", "Parse and normalize", "APQ/SSR parsing and normalization"),
    ("03OcrAndSectionRecovery.ipynb", "OCR and section recovery", "asset and section lineage recovery"),
    ("04SplitTracks.ipynb", "Split tracks", "track split and mixedUnresolved preservation"),
    ("05ExtractRequirements.ipynb", "Extract requirements", "mandatory/preferred boundary extraction"),
    ("06Deduplicate90Days.ipynb", "Deduplicate 90 days", "repost grouping with eligibility kept separate"),
    ("07LabelCareerAccess.ipynb", "Label career access", "E/I accessibility labeling"),
    ("08LoadAndPrepareNcs.ipynb", "Load and prepare NCS", "NCS level 1-8 preservation and bands"),
    ("09MapPostingToNcs.ipynb", "Map postings to NCS", "evidence-preserving NCS matching"),
    ("10BuildPostingMart.ipynb", "Build posting mart", "canonical track-grain mart build"),
    ("11BuildTimeSeriesMart.ipynb", "Build time-series mart", "RQ denominators and coverage metrics"),
    ("12AnalyzeRq1Rq2.ipynb", "Analyze RQ1 and RQ2", "segmented regression and panel robustness"),
    ("13BuildArticleFigures.ipynb", "Build article figures", "source-backed figures only"),
    ("90AuxSimilarity.ipynb", "Auxiliary similarity", "auxiliary analysis after canonical marts"),
]


ROOT_LOCATOR = '''from pathlib import Path
import json, subprocess, sys

def find_pipeline_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src/p4").exists():
            return candidate
    raise RuntimeError("pipeline root not found")

PIPELINE_ROOT = find_pipeline_root(Path.cwd().resolve())
sys.path.insert(0, str(PIPELINE_ROOT / "src"))
BRANCH = subprocess.check_output(["git", "branch", "--show-current"], cwd=PIPELINE_ROOT, text=True).strip()
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PIPELINE_ROOT, text=True).strip()
'''


PRODUCTION_FIRST_CELL = ROOT_LOCATOR + '''
METADATA = {
    "agentId": "P4-A2-PIPELINE",
    "agentName": "P4 Contract-Driven Pipeline & Analysis Engineer",
    "branch": BRANCH,
    "HEAD": HEAD,
    "contractVersion": None,
    "crawlReleaseId": None,
    "dataVersion": None,
    "asOfDate": "2026-08-06",
}
print(json.dumps(METADATA, ensure_ascii=False, indent=2))'''


FIXTURE_FIRST_CELL = ROOT_LOCATOR + '''
SUMMARY_PATH = PIPELINE_ROOT / "runs/fixture_pipeline_summary.json"
SUMMARY = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
METADATA = {
    "agentId": "P4-A2-PIPELINE",
    "agentName": "P4 Contract-Driven Pipeline & Analysis Engineer",
    "branch": BRANCH,
    "HEAD": HEAD,
    "contractVersion": None,
    "crawlReleaseId": None,
    "dataVersion": SUMMARY.get("dataVersion", "SYNTHETIC"),
    "asOfDate": "2026-08-06",
    "dataProvenance": "SYNTHETIC",
}
print(json.dumps(METADATA, ensure_ascii=False, indent=2))'''


PRODUCTION_BODY_CELL = '''STAGE = {stage!r}
NOTE = {note!r}
STATUS = {{
    "stage": STAGE,
    "note": NOTE,
    "qualityStatus": "BLOCKED_BY_CONTRACT_AND_CRAWL_RELEASE",
    "empiricalAnalysisAllowed": False,
    "syntheticInputUsed": False,
}}
print(json.dumps(STATUS, ensure_ascii=False, indent=2))'''


FIXTURE_BODY_CELL = '''STAGE = {stage!r}
NOTE = {note!r}
print(json.dumps({{
    "stage": STAGE,
    "note": NOTE,
    "dataProvenance": "SYNTHETIC",
    "empiricalAnalysisAllowed": False,
    "contractReady": SUMMARY.get("contract", {{}}).get("ready", False),
    "crawlReleaseCount": SUMMARY.get("crawlReleaseCount", 0),
    "fixtureRows": SUMMARY.get("rows", {{}}),
}}, ensure_ascii=False, indent=2))'''


PRODUCTION_LAST_CELL = '''FINAL = {
    "inputRows": 0,
    "outputRows": 0,
    "excludedRows": 0,
    "qualityStatus": "BLOCKED_BY_CONTRACT_AND_CRAWL_RELEASE",
    "outputPaths": [],
    "outputSha256": [],
}
print(json.dumps(FINAL, ensure_ascii=False, indent=2))'''


FIXTURE_LAST_CELL = '''rows = SUMMARY.get("rows", {})
FINAL = {
    "inputRows": rows.get("raw", 0),
    "outputRows": rows.get("postingAnalysisMart", 0),
    "excludedRows": rows.get("excludedPostings", 0),
    "qualityStatus": "PASS_SYNTHETIC_FIXTURE_ONLY" if SUMMARY.get("postingMartQuality", {}).get("passed") else "BLOCKED_NO_FIXTURE",
    "outputPaths": [item.get("path") for item in SUMMARY.get("artifactManifest", [])],
    "outputSha256": [item.get("sha256") for item in SUMMARY.get("artifactManifest", [])],
}
print(json.dumps(FINAL, ensure_ascii=False, indent=2))'''


def make_notebook(filename: str, title: str, note: str, fixture: bool):
    notebook = nbf.v4.new_notebook()
    notebook["metadata"].update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "p4": {"mode": "SYNTHETIC_FIXTURE" if fixture else "PRODUCTION", "agentId": "P4-A2-PIPELINE"},
        }
    )
    first = FIXTURE_FIRST_CELL if fixture else PRODUCTION_FIRST_CELL
    body = FIXTURE_BODY_CELL if fixture else PRODUCTION_BODY_CELL
    last = FIXTURE_LAST_CELL if fixture else PRODUCTION_LAST_CELL
    label = "SYNTHETIC FIXTURE" if fixture else "PRODUCTION - BLOCKED"
    notebook["cells"] = [
        nbf.v4.new_code_cell(first),
        nbf.v4.new_markdown_cell(
            f"# {title}\n\n**{label}**\n\n"
            + ("This notebook verifies code paths only; outputs are not observations." if fixture else "This notebook does not execute empirical stages until canonical inputs are available.")
        ),
        nbf.v4.new_code_cell(body.format(stage=filename.removesuffix(".ipynb"), note=note)),
        nbf.v4.new_code_cell(last),
    ]
    return notebook


def build() -> list[Path]:
    NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    FIXTURE_NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for filename, title, note in NOTEBOOKS:
        production_target = NOTEBOOK_ROOT / filename
        fixture_target = FIXTURE_NOTEBOOK_ROOT / filename
        nbf.write(make_notebook(filename, title, note, fixture=False), production_target)
        nbf.write(make_notebook(filename, title, note, fixture=True), fixture_target)
        outputs.extend([production_target, fixture_target])
    return outputs


if __name__ == "__main__":
    for output in build():
        print(output.relative_to(PIPELINE_ROOT))
