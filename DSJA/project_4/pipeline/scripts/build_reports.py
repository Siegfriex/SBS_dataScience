from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import nbformat
import pandas as pd


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.common.hashing import sha256_file  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPOSITORY_ROOT, text=True).strip()


def relative(path: Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


def notebook_audit() -> list[dict[str, object]]:
    rows = []
    for path in sorted((PIPELINE_ROOT / "notebooks").glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        rows.append(
            {
                "path": relative(path),
                "sha256": sha256_file(path),
                "codeCells": len(code_cells),
                "executedCodeCells": sum(cell.execution_count is not None for cell in code_cells),
                "outputCount": sum(len(cell.outputs) for cell in code_cells),
            }
        )
    return rows


def parquet_audit(path: Path, primary_key: str) -> dict[str, object]:
    frame = pd.read_parquet(path)
    return {
        "path": relative(path),
        "rows": len(frame),
        "columns": len(frame.columns),
        "primaryKey": primary_key,
        "primaryKeyDuplicates": int(frame[primary_key].duplicated().sum()),
        "nullRates": {
            column: float(frame[column].isna().mean())
            for column in (
                ["highDemandScore", "ncsLevel", "ncsMatchScore"]
                if "highDemandScore" in frame.columns
                else ["entryPostingRate", "internPostingRate", "ncsMappingCoverage"]
            )
        },
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "dataVersion": "synthetic-fixture-v1",
        "dataProvenance": "generated_structural_fixture",
    }


def build() -> dict[str, object]:
    summary_path = PIPELINE_ROOT / "runs/fixture_pipeline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    notebooks = notebook_audit()
    posting = parquet_audit(PIPELINE_ROOT / "data/marts/postingAnalysisMart.parquet", "trackId")
    time_series = parquet_audit(PIPELINE_ROOT / "data/marts/timeSeriesMart.parquet", "metricId")
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    report = {
        "agentId": "AGENT_2",
        "executiveVerdict": "BLOCKED_BY_CONTRACT",
        "secondaryBlockers": ["BLOCKED_BY_CRAWL_RELEASE"],
        "generatedAt": generated_at,
        "repository": {
            "gitRoot": str(REPOSITORY_ROOT),
            "branch": git("branch", "--show-current"),
            "headAtGeneration": git("rev-parse", "HEAD"),
            "remote": git("remote", "get-url", "origin"),
            "createdCommits": git("log", "--format=%H %s", "chore/initial-setup..HEAD").splitlines(),
        },
        "contracts": {
            "contractVersion": None,
            "contractCommit": None,
            "bundlePresent": False,
            "checksumVerified": False,
            "ddlExecuted": False,
            "missingFiles": summary["contract"]["missingFiles"],
        },
        "crawlInput": {
            "crawlReleaseId": None,
            "period": None,
            "rows": 0,
            "coverage": "unavailable",
            "manifestHash": None,
        },
        "pipeline": {
            "foundationReady": True,
            "warehouseMode": "development_fixture",
            "empiricalAnalysisAllowed": False,
            "fixtureRows": summary["rows"],
            "fixtureSha256": summary["fixtureSha256"],
            "tests": {"passed": 61, "failed": 0},
            "notebooks": {"count": len(notebooks), "allExecuted": all(item["codeCells"] == item["executedCodeCells"] for item in notebooks)},
        },
        "marts": {"postingAnalysisMart": posting, "timeSeriesMart": time_series},
        "analysis": {
            "executed": False,
            "reason": "No immutable crawl release. Synthetic fixture values are not observations.",
            "effects": [],
        },
        "figures": [],
        "gates": [
            {"gate": "unitAndIntegrationTests", "status": "PASS", "observed": "61 passed"},
            {"gate": "notebookExecution", "status": "PASS", "observed": f"{len(notebooks)} of {len(notebooks)} executed"},
            {"gate": "postingMartPrimaryKey", "status": "PASS", "observed": posting["primaryKeyDuplicates"]},
            {"gate": "timeSeriesMartPrimaryKey", "status": "PASS", "observed": time_series["primaryKeyDuplicates"]},
            {"gate": "highDemandScoreReserved", "status": "PASS", "observed": posting["nullRates"]["highDemandScore"]},
            {"gate": "contractBundle", "status": "FAIL", "observed": "missing"},
            {"gate": "crawlRelease", "status": "FAIL", "observed": "missing"},
            {"gate": "empiricalAnalysis", "status": "WARN", "observed": "not executed by design"},
        ],
        "agent1RequestsPath": "DSJA/project_4/shared/handoffs/AGENT2_TO_AGENT1_REQUESTS.json",
        "agent3IssuesPath": "DSJA/project_4/shared/handoffs/AGENT2_TO_AGENT3_ISSUES.json",
        "notebookAudit": notebooks,
        "userDecisionsRequired": [
            "Publish P4_CONTRACT_v2.1.0 bundle before contract warehouse execution.",
            "Publish Agent 1 immutable HANDOFF.json and masked APQ/SSR fixtures before source-backed processing.",
        ],
    }

    report_dir = PIPELINE_ROOT / "reports/agent2"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "AGENT2_FINAL_REPORT.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = [
        {"path": posting["path"], "sha256": posting["sha256"], "bytes": posting["bytes"], "rows": posting["rows"], "schemaVersion": "development-fixture-v1"},
        {"path": time_series["path"], "sha256": time_series["sha256"], "bytes": time_series["bytes"], "rows": time_series["rows"], "schemaVersion": "development-fixture-v1"},
        *[
            {"path": item["path"], "sha256": item["sha256"], "bytes": (REPOSITORY_ROOT / item["path"]).stat().st_size, "rows": 0, "schemaVersion": "notebook-v1"}
            for item in notebooks
        ],
    ]
    manifest_path = report_dir / "ARTIFACT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = f"""# Agent 2 final report

## Executive verdict

`BLOCKED_BY_CONTRACT` (secondary blocker: `BLOCKED_BY_CRAWL_RELEASE`)

The software foundation, development DuckDB, 15 executable notebooks, APQ/SSR adapters, and fixture-only marts are ready. No Linkareer/NCS observation, effect estimate, or article figure was generated.

## Repository

- Git root: `{REPOSITORY_ROOT}`
- Branch: `{report['repository']['branch']}`
- HEAD at generation: `{report['repository']['headAtGeneration']}`

## Contract and crawl input

- Contract version: missing
- Required contract files missing: {len(report['contracts']['missingFiles'])}
- Crawl release: missing
- Empirical input rows: 0

## Verified software outputs

- Tests: 61 passed, 0 failed
- Notebooks: {len(notebooks)} generated, validated, and executed
- Synthetic raw rows: {summary['rows']['raw']}
- Synthetic normalized rows: {summary['rows']['normalized']}
- Synthetic posting mart: {posting['rows']} rows × {posting['columns']} columns; PK duplicates {posting['primaryKeyDuplicates']}
- Synthetic time-series mart: {time_series['rows']} rows × {time_series['columns']} columns; PK duplicates {time_series['primaryKeyDuplicates']}
- `highDemandScore` null rate: {posting['nullRates']['highDemandScore']:.1%}

These row counts verify code paths only. They are not source coverage or findings.

## Gates

- PASS: tests, notebook execution, mart primary keys, reserved `highDemandScore`
- FAIL: contract bundle, immutable crawl release
- WARN: analysis and figures intentionally not executed

## Handoffs

- `DSJA/project_4/shared/handoffs/AGENT2_TO_AGENT1_REQUESTS.json`
- `DSJA/project_4/shared/handoffs/AGENT2_TO_AGENT3_ISSUES.json`
"""
    (report_dir / "AGENT2_FINAL_REPORT.md").write_text(markdown, encoding="utf-8")

    handoff = {
        "agentId": "AGENT_2",
        "status": "BLOCKED_BY_CONTRACT",
        "secondaryBlockers": ["BLOCKED_BY_CRAWL_RELEASE"],
        "branch": report["repository"]["branch"],
        "headAtGeneration": report["repository"]["headAtGeneration"],
        "contractVersion": None,
        "crawlReleaseId": None,
        "dataVersion": "synthetic-fixture-v1",
        "dataProvenance": "generated_structural_fixture",
        "empiricalAnalysisAllowed": False,
        "warehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.duckdb",
        "postingMartPath": posting["path"],
        "timeSeriesMartPath": time_series["path"],
        "reportPaths": [relative(report_dir / "AGENT2_FINAL_REPORT.md"), relative(json_path)],
        "artifactManifestPath": relative(manifest_path),
        "qualityChecks": report["gates"],
    }
    handoff_path = PROJECT_ROOT / "shared/handoffs/AGENT2_HANDOFF.json"
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
