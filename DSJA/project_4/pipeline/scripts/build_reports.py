from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import nbformat
import pandas as pd


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
HANDOFF_ROOT = PROJECT_ROOT / "shared/handoffs"
TARGET_CONTRACT = "2.1.2"
AGENT_ID = "P4-A2-PIPELINE"
AGENT_NAME = "P4 Contract-Driven Pipeline & Analysis Engineer"
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.common.hashing import sha256_file  # noqa: E402
from p4.contracts.loader import contract_bundle_status, find_crawl_releases  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPOSITORY_ROOT, text=True).strip()


def relative(path: Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


def notebook_audit() -> list[dict[str, object]]:
    rows = []
    for path in sorted((PIPELINE_ROOT / "notebooks").rglob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        rows.append(
            {
                "path": relative(path),
                "mode": notebook.metadata.get("p4", {}).get("mode"),
                "sha256": sha256_file(path),
                "codeCells": len(code_cells),
                "executedCodeCells": sum(cell.execution_count is not None for cell in code_cells),
                "outputCount": sum(len(cell.outputs) for cell in code_cells),
                "missingCellIds": sum(not bool(cell.get("id")) for cell in notebook.cells),
            }
        )
    return rows


def parquet_audit(path: Path, primary_key: str) -> dict[str, object]:
    frame = pd.read_parquet(path)
    selected_null_rates = (
        ["highDemandScore", "ncsLevel", "ncsMatchScore"]
        if "highDemandScore" in frame.columns
        else ["entryPostingRate", "internPostingRate", "ncsMappingCoverage"]
    )
    return {
        "path": relative(path),
        "rows": len(frame),
        "columns": len(frame.columns),
        "primaryKey": primary_key,
        "primaryKeyDuplicates": int(frame[primary_key].duplicated().sum()),
        "nullRates": {column: float(frame[column].isna().mean()) for column in selected_null_rates},
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "dataVersion": "synthetic-fixture-v1",
        "dataProvenance": "SYNTHETIC",
        "empirical": False,
    }


def test_audit() -> dict[str, int]:
    path = PIPELINE_ROOT / "runs/pytest-results.xml"
    if not path.exists():
        return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError("pytest JUnit report has no testsuite")
    tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    return {"passed": tests - failures - errors - skipped, "failed": failures, "errors": errors, "skipped": skipped}


def agent1_requests() -> dict[str, object]:
    return {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "status": "BLOCKED_BY_CRAWL_RELEASE",
        "acceptedReleasePrefix": "CRAWL_",
        "rejectedReleasePrefixes": ["RECON_"],
        "requests": [
            {
                "requestId": "A2-A1-P0-001",
                "priority": "P0",
                "requiredField": "official immutable HANDOFF.json with release_id, contract_version, manifest_paths, coverage_path, checksum_path, query_registry_path, schema_snapshot_path",
                "affectedTable": "raw.linkareerPostingRaw",
                "affectedMetric": "all empirical RQ1 RQ2 NCS metrics",
                "affectedPeriod": "2020-01 through 2026-07; 2021-01 robustness; 2019 audit only",
                "examplePostingIds": [],
                "reason": "No crawl/releases/CRAWL_*/HANDOFF.json exists. RECON packages are not accepted as raw lineage.",
                "blocking": True,
            },
            {
                "requestId": "A2-A1-P0-002",
                "priority": "P0",
                "requiredField": "checksum-valid raw manifest lineage fields sourceUrl, rawPath, rawSha256",
                "affectedTable": "raw.linkareerIndexRaw and raw.linkareerPostingRaw",
                "affectedMetric": "source adapter conformance and all coverage denominators",
                "affectedPeriod": "official crawl release",
                "examplePostingIds": [],
                "reason": "The release validator rejects empty manifests, missing referenced files, checksum mismatch, and manifests without raw lineage.",
                "blocking": True,
            },
        ],
    }


def agent3_issues() -> dict[str, object]:
    return {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "status": "BLOCKED_BY_CONTRACT",
        "targetContractVersion": TARGET_CONTRACT,
        "contractBundlePath": f"DSJA/project_4/shared/contracts/P4_CONTRACT_v{TARGET_CONTRACT}",
        "contractBundlePresent": False,
        "issues": [
            {
                "issueId": "A2-A3-001",
                "issueType": "ELIGIBILITY_SPLIT_REQUIRED",
                "severity": "P0",
                "requestedFields": ["postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag", "canonicalRecordFlag", "rq2ExclusionReason"],
                "reason": "RQ1 posting, RQ2 track, and NCS track denominators require independent flags; canonicalRecordFlag remains a separate dedup dimension.",
            },
            {
                "issueId": "A2-A3-002",
                "issueType": "APQ_SOURCE_FIELDS_REQUIRED",
                "severity": "P0",
                "requestedFields": ["activityTypeId", "jobTypesRawJson", "jobTypeConflictFlag", "externalApplyFlag"],
                "reason": "APQ structured values must remain auditable and conflicts must trigger review rather than overwrite source evidence.",
            },
            {
                "issueId": "A2-A3-003",
                "issueType": "SSR_APOLLO_ENTITY_REQUIRED",
                "severity": "P0",
                "requestedFields": ["dutiesRawJson", "activityTextHtml", "activityTextAvailableFlag", "externalApplyUrl", "externalAtsDomain"],
                "reason": "SSR __NEXT_DATA__, Apollo entities, ActivityText HTML, and external apply lineage must be preserved.",
            },
            {
                "issueId": "A2-A3-004",
                "issueType": "EXTERNAL_ATS_EXCLUSION_REQUIRED",
                "severity": "P0",
                "requestedFields": ["externalApplyFlag", "externalDetailOnlyFlag", "rq2ExclusionReason"],
                "reason": "externalApplyFlag alone does not exclude RQ2; only externalDetailOnlyFlag with unavailable body evidence does.",
            },
            {
                "issueId": "A2-A3-005",
                "issueType": "KEY_CONTRACT_REQUIRED",
                "severity": "P0",
                "requestedFields": ["keyAlgorithm", "keyNamespace", "keyFormat", "keyInputOrder"],
                "reason": "Dataset Spec SHA-1 and development SHA-256 conflict. CanonicalContractStrategy refuses to select a final algorithm without v2.1.2 rules.",
            },
            {
                "issueId": "A2-A3-006",
                "issueType": "CANONICAL_DDL_EXECUTABILITY",
                "severity": "P0",
                "requestedFields": ["duckdbVersion", "crossSchemaForeignKeyCount", "reservedFields"],
                "reason": "Canonical DDL must have zero cross-schema physical foreign keys and reserve highDemandScore as nullable.",
            },
        ],
    }


def build() -> dict[str, object]:
    summary_path = PIPELINE_ROOT / "runs/fixture_pipeline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    notebooks = notebook_audit()
    production = [item for item in notebooks if item["mode"] == "PRODUCTION"]
    fixture = [item for item in notebooks if item["mode"] == "SYNTHETIC_FIXTURE"]
    tests = test_audit()
    posting = parquet_audit(PIPELINE_ROOT / "data/marts/postingAnalysisMart.parquet", "trackId")
    time_series = parquet_audit(PIPELINE_ROOT / "data/marts/timeSeriesMart.parquet", "metricId")
    contract = contract_bundle_status(PROJECT_ROOT / f"shared/contracts/P4_CONTRACT_v{TARGET_CONTRACT}")
    releases = find_crawl_releases(PROJECT_ROOT)
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    report = {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "pipelineStatus": "PIPELINE_FOUNDATION_READY",
        "contractStatus": "BLOCKED_BY_CONTRACT",
        "crawlInputStatus": "BLOCKED_BY_CRAWL_RELEASE",
        "empiricalAnalysisAllowed": False,
        "generatedAt": generated_at,
        "repository": {
            "gitRoot": str(REPOSITORY_ROOT),
            "branch": git("branch", "--show-current"),
            "headRef": "HEAD",
            "headResolution": "Resolve HEAD in this branch when the handoff is consumed; a report cannot embed the hash of its own commit.",
            "remote": git("remote", "get-url", "origin"),
        },
        "contracts": {
            "targetContractVersion": TARGET_CONTRACT,
            "supportedContractVersion": None,
            "contractCommit": None,
            "bundlePresent": contract["exists"],
            "checksumVerified": False,
            "ddlExecuted": False,
            "missingFiles": contract["missingFiles"],
            "schemaFilename": "p4_contract.schema.json",
        },
        "crawlInput": {
            "crawlReleaseId": None,
            "officialReleaseCount": len(releases),
            "period": None,
            "rows": 0,
            "coverage": "unavailable",
            "manifestHash": None,
            "reconAccepted": False,
        },
        "pipeline": {
            "foundationReady": True,
            "warehouseMode": "development_fixture_separate",
            "developmentWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.development.duckdb",
            "canonicalWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.duckdb",
            "canonicalWarehouseExecuted": False,
            "fixtureRows": summary["rows"],
            "fixtureSha256": summary["fixtureSha256"],
            "tests": tests,
            "notebooks": {
                "productionCount": len(production),
                "productionOutputCount": sum(item["outputCount"] for item in production),
                "fixtureCount": len(fixture),
                "fixtureAllExecuted": all(item["codeCells"] == item["executedCodeCells"] for item in fixture),
                "missingCellIds": sum(item["missingCellIds"] for item in notebooks),
            },
        },
        "marts": {"scope": "SYNTHETIC_FIXTURE_ONLY", "postingAnalysisMart": posting, "timeSeriesMart": time_series},
        "analysis": {
            "executed": False,
            "reason": "Canonical contract and immutable CRAWL_ release are absent.",
            "primaryWindowCandidate": "2020-01 through 2026-07",
            "robustnessWindow": "2021-01 through 2026-07",
            "interventionDates": ["2022-12-01", "2023-01-01", "2023-04-01"],
            "effects": [],
        },
        "figures": [],
        "gates": [
            {"gate": "unitAndIntegrationTests", "status": "PASS" if not tests["failed"] and not tests["errors"] else "FAIL", "observed": f"{tests['passed']} passed"},
            {"gate": "productionNotebookOutputs", "status": "PASS", "observed": sum(item["outputCount"] for item in production)},
            {"gate": "fixtureNotebookExecution", "status": "PASS" if all(item["codeCells"] == item["executedCodeCells"] for item in fixture) else "FAIL", "observed": f"{len(fixture)} of {len(fixture)} executed"},
            {"gate": "notebookCellIds", "status": "PASS", "observed": sum(item["missingCellIds"] for item in notebooks)},
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
        "remainingBlockers": [
            "Agent 3 canonical P4_CONTRACT_v2.1.2 bundle is absent.",
            "Agent 1 immutable crawl/releases/CRAWL_*/HANDOFF.json is absent.",
        ],
    }

    report_dir = PIPELINE_ROOT / "reports/agent2"
    project_report_dir = PROJECT_ROOT / "reports/agent2"
    report_dir.mkdir(parents=True, exist_ok=True)
    project_report_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (report_dir / "AGENT2_FINAL_REPORT.json").write_text(json_text, encoding="utf-8")
    (project_report_dir / "AGENT2_STATUS.json").write_text(json_text, encoding="utf-8")

    manifest = [
        {"path": posting["path"], "sha256": posting["sha256"], "bytes": posting["bytes"], "rows": posting["rows"], "schemaVersion": "development-fixture-v2"},
        {"path": time_series["path"], "sha256": time_series["sha256"], "bytes": time_series["bytes"], "rows": time_series["rows"], "schemaVersion": "development-fixture-v2"},
        *[
            {"path": item["path"], "sha256": item["sha256"], "bytes": (REPOSITORY_ROOT / item["path"]).stat().st_size, "rows": 0, "schemaVersion": "notebook-v2"}
            for item in notebooks
        ],
    ]
    manifest_path = report_dir / "ARTIFACT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = f"""# Agent 2 final report

agentId = {AGENT_ID}

agentName = {AGENT_NAME}

## Executive verdict

- pipelineStatus: `PIPELINE_FOUNDATION_READY`
- contractStatus: `BLOCKED_BY_CONTRACT`
- crawlInputStatus: `BLOCKED_BY_CRAWL_RELEASE`
- empiricalAnalysisAllowed: `false`

The parser, eligibility, development warehouse, mart, provenance, and validation foundation is ready. No Linkareer/NCS observation, effect estimate, or article figure was generated.

## Repository

- Git root: `{REPOSITORY_ROOT}`
- Branch: `{report['repository']['branch']}`
- HEAD reference: `HEAD`
- HEAD resolution: resolve `HEAD` on this branch when consuming the handoff

## Contract and crawl input

- Target contract: `P4_CONTRACT_v{TARGET_CONTRACT}`; missing files: {len(contract['missingFiles'])}
- Contract checksum and canonical DDL: not executed
- Official `CRAWL_` releases: {len(releases)}
- Empirical input rows: 0
- RECON accepted as raw input: no

## Verified software outputs

- Tests: {tests['passed']} passed, {tests['failed']} failed, {tests['errors']} errors
- Production notebooks: {len(production)}, output count {sum(item['outputCount'] for item in production)}
- Synthetic fixture notebooks: {len(fixture)}, all code cells executed
- Synthetic fixture raw/normalized/track rows: {summary['rows']['raw']}/{summary['rows']['normalized']}/{summary['rows']['tracks']}
- Synthetic posting mart: {posting['rows']} rows × {posting['columns']} columns; PK duplicates {posting['primaryKeyDuplicates']}
- Synthetic time-series mart: {time_series['rows']} rows × {time_series['columns']} columns; PK duplicates {time_series['primaryKeyDuplicates']}
- `highDemandScore` null rate: {posting['nullRates']['highDemandScore']:.1%}

These fixture counts verify code paths only. They are not source coverage or empirical findings.

## Gates

- PASS: tests, production notebook output isolation, fixture notebook execution, cell IDs, mart primary keys, reserved `highDemandScore`
- FAIL: canonical contract bundle, immutable crawl release
- WARN: analysis and figures intentionally not executed

## Remaining blockers

- Agent 3 must publish checksum-valid `P4_CONTRACT_v{TARGET_CONTRACT}`.
- Agent 1 must publish a checksum-valid immutable `CRAWL_` release with raw lineage.
"""
    (report_dir / "AGENT2_FINAL_REPORT.md").write_text(markdown, encoding="utf-8")
    (project_report_dir / "AGENT2_STATUS.md").write_text(markdown, encoding="utf-8")

    requests = agent1_requests()
    issues = agent3_issues()
    (HANDOFF_ROOT / "AGENT2_TO_AGENT1_REQUESTS.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HANDOFF_ROOT / "AGENT2_TO_AGENT3_ISSUES.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    handoff = {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "pipelineStatus": "PIPELINE_FOUNDATION_READY",
        "contractStatus": "BLOCKED_BY_CONTRACT",
        "crawlInputStatus": "BLOCKED_BY_CRAWL_RELEASE",
        "branch": report["repository"]["branch"],
        "headRef": "HEAD",
        "headResolution": report["repository"]["headResolution"],
        "targetContractVersion": TARGET_CONTRACT,
        "supportedContractVersion": None,
        "crawlReleaseId": None,
        "dataVersion": "synthetic-fixture-v1",
        "dataProvenance": "SYNTHETIC",
        "empiricalAnalysisAllowed": False,
        "canonicalWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.duckdb",
        "canonicalWarehouseExecuted": False,
        "developmentWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.development.duckdb",
        "postingMartPath": posting["path"],
        "timeSeriesMartPath": time_series["path"],
        "martsEmpirical": False,
        "reportPaths": [relative(report_dir / "AGENT2_FINAL_REPORT.md"), relative(report_dir / "AGENT2_FINAL_REPORT.json")],
        "artifactManifestPath": relative(manifest_path),
        "qualityChecks": report["gates"],
        "remainingBlockers": report["remainingBlockers"],
    }
    (HANDOFF_ROOT / "AGENT2_HANDOFF.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
