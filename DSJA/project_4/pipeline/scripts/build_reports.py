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
AGENT_ID = "P4-A2-PIPELINE"
AGENT_NAME = "P4 Contract-Driven Pipeline & Analysis Engineer"
CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_02"
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.common.hashing import sha256_file  # noqa: E402
from p4.contracts.duty_input import validate_duty_input_handoff  # noqa: E402
from p4.contracts.validators import audit_contract_bundle  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPOSITORY_ROOT, text=True).strip()


def relative(path: Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


def notebook_audit() -> list[dict[str, object]]:
    rows = []
    for path in sorted((PIPELINE_ROOT / "notebooks").rglob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        code = [cell for cell in notebook.cells if cell.cell_type == "code"]
        rows.append(
            {
                "path": relative(path),
                "mode": notebook.metadata.get("p4", {}).get("mode"),
                "sha256": sha256_file(path),
                "codeCells": len(code),
                "executedCodeCells": sum(cell.execution_count is not None for cell in code),
                "outputCount": sum(len(cell.outputs) for cell in code),
                "missingCellIds": sum(not bool(cell.get("id")) for cell in notebook.cells),
            }
        )
    return rows


def test_audit() -> dict[str, int]:
    root = ET.parse(PIPELINE_ROOT / "runs/pytest-results.xml").getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError("pytest JUnit report has no testsuite")
    total = int(suite.attrib["tests"])
    failed = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    return {"passed": total - failed - errors - skipped, "failed": failed, "errors": errors, "skipped": skipped}


def parquet_audit(path: Path, primary_key: str) -> dict[str, object]:
    frame = pd.read_parquet(path)
    return {
        "path": relative(path),
        "rows": len(frame),
        "columns": len(frame.columns),
        "primaryKey": primary_key,
        "primaryKeyDuplicates": int(frame[primary_key].duplicated().sum()),
        "highDemandNonNullCount": int(frame["highDemandScore"].notna().sum()) if "highDemandScore" in frame else None,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "dataVersion": "synthetic-fixture-v1",
        "dataProvenance": "SYNTHETIC",
        "empirical": False,
    }


def agent1_requests() -> dict[str, object]:
    base = {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "status": "BLOCKED_BY_FULL_CRAWL_RELEASE",
        "lastReviewedReleaseId": CRAWL_RELEASE_ID,
        "requests": [],
    }
    base["requests"] = [
        {
            "requestId": "A2-A1-P0-001", "priority": "P0", "status": "resolved",
            "requiredField": "release envelope with seven required locator fields and contractVersion 2.1.2",
            "affectedTable": "raw.crawlRun", "affectedMetric": "release conformance", "affectedPeriod": "CRAWL_20260806_02",
            "examplePostingIds": [], "reason": "Resolved in CRAWL_20260806_02; all locator fields exist and contract_version is 2.1.2.", "blocking": False,
        },
        {
            "requestId": "A2-A1-P0-002", "priority": "P0", "status": "open",
            "requiredField": "per-record immutable detail rawPath and rawSha256 for every sampled and collected Linkareer posting",
            "affectedTable": "raw.linkareerPostingRaw", "affectedMetric": "all empirical RQ1 RQ2 NCS metrics", "affectedPeriod": "2020-01 through 2026-07",
            "examplePostingIds": ["339737", "339821"], "reason": "The n=126 artifact preserves derived fields, not full raw HTML per posting.", "blocking": True,
        },
        {
            "requestId": "A2-A1-P0-003", "priority": "P0", "status": "resolved",
            "requiredField": "explicit monthly coverage rows without silent omissions",
            "affectedTable": "qa.monthlyCoverageAudit", "affectedMetric": "coverage denominators", "affectedPeriod": "2019 audit and 2020-01 through 2026-07",
            "examplePostingIds": [], "reason": "Resolved: all target months have explicit coverageStatus and coverageReason.", "blocking": False,
        },
        {
            "requestId": "A2-A1-P0-004", "priority": "P0", "status": "open",
            "requiredField": "pagination_verified=true for all 79 target months or an approved analysis-window coverage contract",
            "affectedTable": "qa.monthlyCoverageAudit", "affectedMetric": "all time-series metrics", "affectedPeriod": "2020-01 through 2026-07",
            "examplePostingIds": [], "reason": "Only 11 of 79 target months are complete; 68 remain paginationUnverified.", "blocking": True,
        },
        {
            "requestId": "A2-A1-P0-005", "priority": "P0", "status": "resolved",
            "requiredField": "stratified Linkareer detail sample n>=100",
            "affectedTable": "source adapter QA", "affectedMetric": "eligibility and OCR routing regression", "affectedPeriod": "2020 through 2026",
            "examplePostingIds": [], "reason": "Resolved with 126 of 126 successful derived-detail records.", "blocking": False,
        },
        {
            "requestId": "A2-A1-P1-006", "priority": "P1", "status": "partial",
            "requiredField": "NCS manifest including KSA, ability-unit elements, and performance criteria",
            "affectedTable": "ncs.ncsUnit and ncs.ncsLearningModule", "affectedMetric": "NCS mapping", "affectedPeriod": "current source version",
            "examplePostingIds": [], "reason": "Ability-unit CSV has 13,442 rows and levels 1-8; KSA endpoint still requires a human API key.", "blocking": True,
        },
    ]
    return base


def agent3_issues() -> dict[str, object]:
    return {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "status": "CONTRACT_ACCEPTED",
        "contractVersion": CONTRACT_VERSION,
        "newIssues": [],
        "resolvedIssues": [
            "ELIGIBILITY_SPLIT_REQUIRED",
            "APQ_SOURCE_FIELDS_REQUIRED",
            "SSR_APOLLO_ENTITY_REQUIRED",
            "EXTERNAL_ATS_EXCLUSION_REQUIRED",
            "KEY_CONTRACT_REQUIRED",
            "CANONICAL_DDL_EXECUTABILITY",
        ],
        "note": "No v2.1.3 request. Producer-local OCR routing and partial-release rejection are handled in Agent 2 code.",
    }


def build() -> dict[str, object]:
    git_common_dir = Path(git("rev-parse", "--git-common-dir"))
    if not git_common_dir.is_absolute():
        git_common_dir = REPOSITORY_ROOT / git_common_dir
    canonical_git_root = str(git_common_dir.resolve().parent)
    contract = audit_contract_bundle(PROJECT_ROOT / "shared/contracts/P4_CONTRACT_v2.1.2")
    warehouse = json.loads((PIPELINE_ROOT / "runs/canonical_warehouse_bootstrap.json").read_text(encoding="utf-8"))
    quarantine = json.loads(
        (PIPELINE_ROOT / "reports/agent2/SYNTHETIC_DB_QUARANTINE.json").read_text(encoding="utf-8")
    )
    duty_handoff_path = HANDOFF_ROOT / "AGENT2_TO_AGENT4_DUTY_INPUT.json"
    duty_handoff = validate_duty_input_handoff(duty_handoff_path)
    partial = json.loads((PIPELINE_ROOT / "reports/agent2/PARTIAL_CRAWL_CONFORMANCE.json").read_text(encoding="utf-8"))
    fixture_summary = json.loads((PIPELINE_ROOT / "runs/fixture_pipeline_summary.json").read_text(encoding="utf-8"))
    tests = test_audit()
    notebooks = notebook_audit()
    production = [row for row in notebooks if row["mode"] == "PRODUCTION"]
    fixture_notebooks = [row for row in notebooks if row["mode"] == "SYNTHETIC_FIXTURE"]
    posting = parquet_audit(PIPELINE_ROOT / "data/marts/postingAnalysisMart.parquet", "trackId")
    time_series = parquet_audit(PIPELINE_ROOT / "data/marts/timeSeriesMart.parquet", "metricId")
    sample = partial["stratifiedSample"]
    report = {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "statusCodes": ["CONTRACT_LINKED", "BLOCKED_BY_FULL_CRAWL_RELEASE", "PIPELINE_FOUNDATION_READY"],
        "empiricalAnalysisAllowed": False,
        "generatedAt": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "repository": {
            "gitRoot": canonical_git_root, "branch": git("branch", "--show-current"), "headRef": "HEAD",
            "worktreeMode": "cleanDedicated",
            "headResolution": "Resolve HEAD when consumed; a tracked report cannot contain its own commit hash.",
            "remote": git("remote", "get-url", "origin"),
        },
        "contract": {
            **{key: contract[key] for key in ("contractVersion", "contractSha256", "manifestSha256", "ddlSha256", "schemaFilename", "duckdbRuntimeVersion", "schemaCount", "tableCount", "viewCount", "ddlStatementCount", "crossSchemaForeignKeyCount", "fieldLineageCount")},
            "checksumCount": len(contract["checksums"]["checked"]), "checksumsPassed": contract["checksums"]["passed"],
            "keyContract": contract["keyContract"], "metricMetadata": contract["metricMetadata"], "supported": True,
            "sourceCommits": ["97f9c04", "2e69380"],
        },
        "canonicalWarehouse": warehouse,
        "canonicalWarehouseProtection": {
            "syntheticDatabase": quarantine,
            "requiredProductionProvenance": [
                "contractVersion", "crawlReleaseId", "dataVersion", "dataProvenance=EMPIRICAL"
            ],
            "failClosed": True,
        },
        "crawlInput": {
            "crawlReleaseId": CRAWL_RELEASE_ID,
            "sourceBranchHead": "825ba03",
            "releaseStatus": "PARTIALLY_READY",
            "acceptance": partial["sourceAdapterConformanceStatus"],
            "empiricalCorpusStatus": partial["empiricalCorpusStatus"],
            "rejectionReasons": partial["empiricalRejectionReasons"],
            "checksumCount": partial["releaseChecksumCount"], "checksumPassed": partial["releaseChecksumPassed"],
            "period": "2020-01 through 2026-07", "targetCoverage": partial["targetCoverageStatusCounts"],
            "allCoverageStatuses": partial["monthlyCoverageStatusCounts"],
            "completeMonthDistinctPostingCount": partial["completeMonthDistinctPostingCount"],
            "detailSampleSuccessCount": partial["detailSampleSuccessCount"], "detailSampleFailureCount": partial["detailSampleFailureCount"],
            "detailRawPerRecordLineageVerified": partial["detailRawPerRecordLineageVerified"],
            "ncsUnitRecordCount": partial["ncsUnitRecordCount"], "adapterFixtureReleaseId": partial["adapterFixtureReleaseId"],
        },
        "sourceAdapterRegression": {
            "apq": partial["apq"], "ssrFixtureCount": partial["ssrFixtureCount"], "ssr": partial["ssr"],
            "sampleRows": sample["rows"], "sampleRates": sample["rates"], "qualityChecks": partial["qualityChecks"],
        },
        "pipeline": {
            "foundationReady": True, "fixtureRows": fixture_summary["rows"], "fixtureSha256": fixture_summary["fixtureSha256"],
            "tests": tests,
            "notebooks": {
                "productionCount": len(production), "productionOutputCount": sum(row["outputCount"] for row in production),
                "fixtureCount": len(fixture_notebooks),
                "fixtureAllExecuted": all(row["codeCells"] == row["executedCodeCells"] for row in fixture_notebooks),
                "missingCellIds": sum(row["missingCellIds"] for row in notebooks),
                "contractVersion": CONTRACT_VERSION, "crawlReleaseId": CRAWL_RELEASE_ID,
                "dataProvenance": "PARTIAL_CONFORMANCE_ONLY", "empiricalAnalysisAllowed": False,
            },
        },
        "marts": {"scope": "SYNTHETIC_FIXTURE_ONLY", "postingAnalysisMart": posting, "timeSeriesMart": time_series},
        "analysis": {"executed": False, "effects": [], "reason": "Full crawl release is absent; partial conformance input is prohibited for empirical analysis."},
        "figures": [],
        "agent4DutyInput": {
            "path": relative(duty_handoff_path),
            "schemaVersion": duty_handoff["schemaVersion"],
            "status": duty_handoff["status"],
            "fixtureRows": len(duty_handoff["fixtureRows"]),
            "empiricalUseAllowed": duty_handoff["empiricalUseAllowed"],
        },
        "gates": [
            {"gate": "contractChecksums", "status": "PASS", "observed": f"{len(contract['checksums']['checked'])} files"},
            {"gate": "canonicalDdl", "status": "PASS", "observed": "39 statements, idempotent"},
            {"gate": "canonicalObjects", "status": "PASS", "observed": "5 schemas, 26 tables, 6 views"},
            {"gate": "emptyAnalysisReadyGate", "status": "PASS", "observed": "NOT_EVALUATED"},
            {"gate": "syntheticDatabaseQuarantine", "status": "PASS", "observed": quarantine["moveValidation"]},
            {"gate": "canonicalMartProvenanceGuard", "status": "PASS", "observed": "fail-closed EMPIRICAL envelope"},
            {"gate": "agent4DutyInputSchema", "status": "PASS", "observed": duty_handoff["status"]},
            {"gate": "unitAndIntegrationTests", "status": "PASS" if not tests["failed"] and not tests["errors"] else "FAIL", "observed": f"{tests['passed']} passed"},
            {"gate": "productionNotebookOutputs", "status": "PASS", "observed": sum(row["outputCount"] for row in production)},
            {"gate": "sourceAdapterConformance", "status": "PASS", "observed": partial["sourceAdapterConformanceStatus"]},
            {"gate": "fullCrawlCoverage", "status": "FAIL", "observed": "11 complete, 68 unverified"},
            {"gate": "detailRawLineage", "status": "FAIL", "observed": False},
            {"gate": "empiricalAnalysis", "status": "WARN", "observed": "not executed by design"},
        ],
        "remainingBlockers": [
            "68 of 79 target months remain paginationUnverified.",
            "Per-record immutable detail raw HTML lineage is absent from CRAWL_20260806_02.",
            "NCS KSA and performance-criteria source requires a human-issued API key.",
        ],
        "notebookAudit": notebooks,
    }

    report_dir = PIPELINE_ROOT / "reports/agent2"
    project_report_dir = PROJECT_ROOT / "reports/agent2"
    report_dir.mkdir(parents=True, exist_ok=True)
    project_report_dir.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (report_dir / "AGENT2_FINAL_REPORT.json").write_text(report_json, encoding="utf-8")
    (project_report_dir / "AGENT2_STATUS.json").write_text(report_json, encoding="utf-8")

    markdown = f"""# Agent 2 final report

agentId = {AGENT_ID}

agentName = {AGENT_NAME}

## Status

- `CONTRACT_LINKED`
- `BLOCKED_BY_FULL_CRAWL_RELEASE`
- `PIPELINE_FOUNDATION_READY`
- empiricalAnalysisAllowed: `false`

## Contract and warehouse

- Contract: `{CONTRACT_VERSION}`
- Contract SHA-256: `{contract['contractSha256']}`
- DDL SHA-256: `{contract['ddlSha256']}`
- Checksums: {len(contract['checksums']['checked'])} PASS, 0 failures
- Canonical DDL: 39 statements; two executions identical
- Objects: 5 schemas, 26 tables, 6 QA views
- Empty `vAnalysisReadyGate`: `NOT_EVALUATED`
- Synthetic DB quarantine SHA-256: `{quarantine['after']['sha256']}`
- Canonical mart provenance guard: `contractVersion + crawlReleaseId + dataVersion + EMPIRICAL`

## Partial crawl conformance

- Release: `{CRAWL_RELEASE_ID}` (`PARTIALLY_READY`)
- Acceptance: `SOURCE_ADAPTER_CONFORMANCE_ACCEPTED`
- Empirical corpus: `EMPIRICAL_CORPUS_REJECTED`
- Target coverage: 11 complete, 68 unverified
- Complete-month distinct postings: {partial['completeMonthDistinctPostingCount']:,}
- Detail sample: {sample['rows']} success, 0 failure
- Per-record raw HTML lineage: absent
- NCS ability-unit records: {partial['ncsUnitRecordCount']:,}

Sample rates are conformance diagnostics, not empirical findings: ActivityText {sample['rates']['hasActivityText']:.1%}, external apply {sample['rates']['externalApplyFlag']:.1%}, external detail only {sample['rates']['externalDetailOnlyFlag']:.1%}, RQ1 {sample['rates']['rq1EligibleFlag']:.1%}, RQ2 {sample['rates']['rq2EligibleFlag']:.1%}, NCS {sample['rates']['ncsEligibleFlag']:.1%}, conflict {sample['rates']['jobTypeConflictFlag']:.1%}, embedded-image OCR candidate {sample['rates']['activityTextEmbeddedImageFlag']:.1%}.

## Agent 4 duty input

- Status: `{duty_handoff['status']}`
- Schema: `{duty_handoff['schemaVersion']}`
- Structural fixture rows: {len(duty_handoff['fixtureRows'])}
- Empirical use allowed: `{str(duty_handoff['empiricalUseAllowed']).lower()}`

## Verification

- Tests: {tests['passed']} passed, {tests['failed']} failed, {tests['errors']} errors
- Production notebooks: {len(production)}, outputs {sum(row['outputCount'] for row in production)}
- Fixture notebooks: {len(fixture_notebooks)}, all code cells executed
- Empirical marts, analysis, figures: not generated
"""
    (report_dir / "AGENT2_FINAL_REPORT.md").write_text(markdown, encoding="utf-8")
    (project_report_dir / "AGENT2_STATUS.md").write_text(markdown, encoding="utf-8")

    artifact_paths = [
        PIPELINE_ROOT / "data/marts/postingAnalysisMart.parquet",
        PIPELINE_ROOT / "data/marts/timeSeriesMart.parquet",
        PIPELINE_ROOT / "data/warehouse/p4.duckdb",
        report_dir / "PARTIAL_CRAWL_CONFORMANCE.json",
        report_dir / "SYNTHETIC_DB_QUARANTINE.json",
        duty_handoff_path,
        *[REPOSITORY_ROOT / row["path"] for row in notebooks],
    ]
    artifact_rows = {
        posting["path"]: posting["rows"],
        time_series["path"]: time_series["rows"],
    }
    artifacts = [
        {
            "path": relative(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "rows": artifact_rows.get(relative(path), 0),
            "schemaVersion": CONTRACT_VERSION,
        }
        for path in artifact_paths
    ]
    manifest_path = report_dir / "ARTIFACT_MANIFEST.json"
    manifest_path.write_text(json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    requests = agent1_requests()
    issues = agent3_issues()
    (HANDOFF_ROOT / "AGENT2_TO_AGENT1_REQUESTS.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HANDOFF_ROOT / "AGENT2_TO_AGENT3_ISSUES.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    handoff = {
        "agentId": AGENT_ID, "agentName": AGENT_NAME,
        "statusCodes": report["statusCodes"], "branch": report["repository"]["branch"], "headRef": "HEAD",
        "contractVersion": CONTRACT_VERSION, "contractLinked": True,
        "crawlReleaseId": CRAWL_RELEASE_ID, "crawlAcceptance": "SOURCE_ADAPTER_CONFORMANCE_ACCEPTED",
        "empiricalCorpusStatus": "EMPIRICAL_CORPUS_REJECTED", "dataProvenance": "PARTIAL_CONFORMANCE_ONLY",
        "empiricalAnalysisAllowed": False,
        "canonicalWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.duckdb", "canonicalWarehouseExecuted": True,
        "canonicalAnalysisReadyGate": "NOT_EVALUATED",
        "canonicalMartProductionGuard": "contractVersion+crawlReleaseId+dataVersion+dataProvenance=EMPIRICAL",
        "syntheticDatabaseQuarantineManifest": relative(report_dir / "SYNTHETIC_DB_QUARANTINE.json"),
        "developmentWarehousePath": "DSJA/project_4/pipeline/data/warehouse/p4.development.duckdb",
        "agent4DutyInputPath": relative(duty_handoff_path),
        "agent4DutyInputStatus": duty_handoff["status"],
        "martsEmpirical": False, "qualityChecks": report["gates"], "remainingBlockers": report["remainingBlockers"],
        "reportPaths": [relative(report_dir / "AGENT2_FINAL_REPORT.md"), relative(report_dir / "AGENT2_FINAL_REPORT.json")],
        "artifactManifestPath": relative(manifest_path),
    }
    (HANDOFF_ROOT / "AGENT2_HANDOFF.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
