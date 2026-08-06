from __future__ import annotations

from pathlib import Path

import nbformat as nbf


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"


NOTEBOOKS = [
    ("00ContractAndInputAudit.ipynb", "Contract and input audit", "contract/input presence; no empirical rows"),
    ("01LoadCrawlRelease.ipynb", "Load crawl release", "release adapter blocked because HANDOFF.json is absent"),
    ("02ParseAndNormalize.ipynb", "Parse and normalize", "synthetic structural fixture transformation only"),
    ("03OcrAndSectionRecovery.ipynb", "OCR and section recovery", "section lineage code verified; no Agent 1 assets available"),
    ("04SplitTracks.ipynb", "Split tracks", "fixture track split and mixedUnresolved preservation"),
    ("05ExtractRequirements.ipynb", "Extract requirements", "fixture mandatory/preferred boundary extraction"),
    ("06Deduplicate90Days.ipynb", "Deduplicate 90 days", "fixture repost grouping with eligibility kept separate"),
    ("07LabelCareerAccess.ipynb", "Label career access", "fixture E/I rule verification only"),
    ("08LoadAndPrepareNcs.ipynb", "Load and prepare NCS", "fixture NCS 1-8 band validation only"),
    ("09MapPostingToNcs.ipynb", "Map postings to NCS", "fixture evidence-preserving match validation only"),
    ("10BuildPostingMart.ipynb", "Build posting mart", "fixture mart; highDemandScore remains null"),
    ("11BuildTimeSeriesMart.ipynb", "Build time-series mart", "fixture denominator and coverage contract verification"),
    ("12AnalyzeRq1Rq2.ipynb", "Analyze RQ1 and RQ2", "BLOCKED: empirical analysis requires crawl_release provenance"),
    ("13BuildArticleFigures.ipynb", "Build article figures", "BLOCKED: no source-backed mart; no graph generated"),
    ("90AuxSimilarity.ipynb", "Auxiliary similarity", "BLOCKED: auxiliary analysis awaits stable source-backed RQ1/RQ2 mart"),
]


FIRST_CELL = '''from pathlib import Path
import json, subprocess, sys

PIPELINE_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(PIPELINE_ROOT / "src"))
REPOSITORY_ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=PIPELINE_ROOT, text=True).strip())
BRANCH = subprocess.check_output(["git", "branch", "--show-current"], cwd=PIPELINE_ROOT, text=True).strip()
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PIPELINE_ROOT, text=True).strip()
SUMMARY_PATH = PIPELINE_ROOT / "runs/fixture_pipeline_summary.json"
SUMMARY = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
METADATA = {
    "repositoryRoot": str(REPOSITORY_ROOT),
    "branch": BRANCH,
    "HEAD": HEAD,
    "contractVersion": "MISSING",
    "crawlReleaseId": "NONE",
    "dataVersion": SUMMARY.get("dataVersion", "NONE"),
    "asOfDate": "2026-08-06",
}
print(json.dumps(METADATA, ensure_ascii=False, indent=2))'''


BODY_CELL = '''STAGE = {stage!r}
NOTE = {note!r}
print(json.dumps({{
    "stage": STAGE,
    "note": NOTE,
    "dataProvenance": SUMMARY.get("dataProvenance", "none"),
    "empiricalAnalysisAllowed": SUMMARY.get("empiricalAnalysisAllowed", False),
    "contractReady": SUMMARY.get("contract", {{}}).get("ready", False),
    "crawlReleaseCount": SUMMARY.get("crawlReleaseCount", 0),
    "fixtureRows": SUMMARY.get("rows", {{}}),
}}, ensure_ascii=False, indent=2))'''


LAST_CELL = '''rows = SUMMARY.get("rows", {})
FINAL = {
    "inputRows": rows.get("raw", 0),
    "outputRows": rows.get("postingAnalysisMart", 0),
    "excludedRows": rows.get("excludedPostings", 0),
    "qualityStatus": "PASS_FIXTURE_ONLY" if SUMMARY.get("postingMartQuality", {}).get("passed") else "BLOCKED_NO_INPUT",
    "outputPaths": [item.get("path") for item in SUMMARY.get("artifactManifest", [])],
    "outputSha256": [item.get("sha256") for item in SUMMARY.get("artifactManifest", [])],
}
print(json.dumps(FINAL, ensure_ascii=False, indent=2))'''


def build() -> list[Path]:
    NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for filename, title, note in NOTEBOOKS:
        notebook = nbf.v4.new_notebook()
        notebook["metadata"]["kernelspec"] = {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        }
        notebook["cells"] = [
            nbf.v4.new_code_cell(FIRST_CELL),
            nbf.v4.new_markdown_cell(f"# {title}\n\nThis notebook never treats synthetic fixtures as source observations."),
            nbf.v4.new_code_cell(BODY_CELL.format(stage=filename.removesuffix(".ipynb"), note=note)),
            nbf.v4.new_code_cell(LAST_CELL),
        ]
        target = NOTEBOOK_ROOT / filename
        nbf.write(notebook, target)
        outputs.append(target)
    return outputs


if __name__ == "__main__":
    for output in build():
        print(output)

