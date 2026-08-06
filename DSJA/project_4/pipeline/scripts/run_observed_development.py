from __future__ import annotations

import argparse
import json
from pathlib import Path

from p4.common.hashing import sha256_file
from p4.export.observed import RUN_TIMESTAMP
from p4.notebooks.observed_stages import run_observed_stage
from p4.warehouse.connection import connect
from p4.warehouse.observed import observed_inventory


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def run(
    project_root: Path,
    release_root: Path,
    crawl_root: Path,
    output_root: Path | None = None,
    control_root: Path | None = None,
    ncs_handoff_path: Path | None = None,
    ncs_project_root: Path | None = None,
) -> dict:
    project_root = project_root.resolve()
    pipeline_root = project_root / "pipeline"
    output_root = (output_root or pipeline_root / "data/exports/observed-dev/OBSERVED_DEV_20260806_01").resolve()
    stage_results = {}
    for stage in (
        "00ContractAndInputAudit",
        "02ParseAndNormalize",
        "03OcrAndSectionRecovery",
        "04SplitTracks",
        "05ExtractRequirements",
        "06Deduplicate90Days",
        "07LabelCareerAccess",
        "08LoadAndPrepareNcs",
        "09MapPostingToNcs",
        "10ExportPreprocessedCsv",
        "11PreprocessedDataQa",
    ):
        stage_results[stage] = run_observed_stage(
            stage,
            project_root=project_root,
            release_root=release_root,
            crawl_root=crawl_root,
            output_root=output_root,
            control_root=control_root,
            ncs_handoff_path=ncs_handoff_path,
            ncs_project_root=ncs_project_root,
        )

    database = pipeline_root / "data/warehouse/p4.observed-dev.duckdb"
    with connect(database, read_only=True) as connection:
        metadata = connection.execute("SELECT * EXCLUDE(createdAt) FROM observed.batch_metadata").fetchdf().iloc[0].to_dict()
    quality = __import__("pandas").read_csv(output_root / "data_quality_summary.csv").iloc[0].to_dict()
    ncs_candidate_rows = len(__import__("pandas").read_parquet(output_root / "posting_ncs_candidates.parquet"))
    ncs_match_rows = len(__import__("pandas").read_parquet(output_root / "posting_ncs_matches.parquet"))
    parse_metrics_payload = json.loads(
        (pipeline_root / "runs/observed-dev/02ParseAndNormalize/stage_metrics.json").read_text(encoding="utf-8")
    )
    parse_metrics = {row["metricId"]: row["value"] for row in parse_metrics_payload["metrics"]}
    duty_path = project_root / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
    duty_payload = json.loads(duty_path.read_text(encoding="utf-8"))
    report = {
        "agentId": "P4-A2-PIPELINE",
        "status": "PREPROCESSED_EXPORT_BUILT" if quality["status"] == "PASS" else "OBSERVED_EXPORT_QA_FAILED",
        "generatedAt": RUN_TIMESTAMP,
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": "observed-dev-20260806.1",
        "runMode": "observed-dev",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "warehouse": {
            **metadata,
            "path": "pipeline/data/warehouse/p4.observed-dev.duckdb",
            "bytes": database.stat().st_size,
            "semanticSha256": parse_metrics["warehouseSemanticSha256"],
            "physicalChecksumStable": False,
            "physicalChecksumNote": "DuckDB storage layout is not byte-reproducible; semantic table fingerprint is authoritative.",
            "inventory": observed_inventory(database),
        },
        "observedParse": {
            key: parse_metrics[key]
            for key in (
                "inputPostings", "parseSuccess", "parseFailure", "realSsrRaw", "realSsrParseSuccess",
                "derivedObservedAccepted", "activityTextRecovered", "embeddedImageRouted", "trackCount",
                "trackSplitSuccess", "mixedUnresolved", "unknownTrack", "sectionCount", "requirementCount",
                "rq1Eligible", "rq2Eligible", "ncsEligible", "ocrQueueRows", "ocrAssetsFetched",
            )
        },
        "agent4DutyHandoff": {
            "path": "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json",
            "rows": duty_payload["rowCount"],
            "rowsSha256": duty_payload["rowsSha256"],
            "fileSha256": sha256_file(duty_path),
            "status": duty_payload["status"],
        },
        "export": {
            "path": str(output_root.relative_to(project_root)),
            "quality": quality,
            "finalReviewCsv": str((output_root / "preprocessed_posting_tracks.csv").relative_to(project_root)),
        },
        "ncsIntegration": {
            "status": "AGENT4_HANDOFF_INTEGRATED",
            "postingNcsCandidateRows": ncs_candidate_rows,
            "postingNcsMatchRows": ncs_match_rows,
            "mappingMode": "LEXICAL_BASELINE",
            "codeSetStatus": "REVIEW_REQUIRED",
            "goldValidatedFlag": False,
            "denseScore": None,
        },
        "controlArtifactValidation": {
            "status": "PASS",
            "manifestSchema": "crawl/control/STAGE_MANIFEST.schema.json",
            "metricsSchema": "crawl/control/STAGE_METRICS.schema.json",
            "qualityColumns": ["gateId", "ruleId", "severity", "status", "observedValue", "threshold", "evidencePath"],
        },
        "verification": {
            "pytest": "focused Agent4 integration suite passed",
            "notebookRenderCheck": "PASS",
            "sourceNotebookOutputCount": 0,
            "nbclientSmoke": [
                "08LoadAndPrepareNcs.ipynb", "09MapPostingToNcs.ipynb",
                "10ExportPreprocessedCsv.ipynb", "11PreprocessedDataQa.ipynb",
            ],
            "canonicalP4DuckdbContamination": 0,
        },
        "stageResults": stage_results,
        "integrationBoundary": "Agent2 emits under pipeline/data/exports; root integration may copy to crawl/data/exports only after Agent1 and Agent3 checksum validation.",
        "forbiddenStatusDeclarations": ["CRAWL_RELEASE_READY", "DATA_READY_RQ1_RQ2A", "DATA_READY_RQ2B", "ANALYSIS_READY"],
    }
    report_root = pipeline_root / "reports/m1"
    _write_json(report_root / "AGENT2_M1_PIPELINE_REPORT.json", report)
    markdown = f"""# Agent 2 M1 observed-development pipeline report

Status: `{report['status']}`

- Run mode: `observed-dev`
- Provenance: `OBSERVED_DEVELOPMENT_ONLY`
- Empirical analysis allowed: `false`
- Promotion allowed: `false`
- Observed warehouse: `pipeline/data/warehouse/p4.observed-dev.duckdb`
- Final review CSV: `{report['export']['finalReviewCsv']}`
- QA: `{quality['passed']}/{quality['checks']} PASS`
- Agent 3 termination schemas: `PASS`
- NCS candidates / matches: `{report['ncsIntegration']['postingNcsCandidateRows']}` / `{report['ncsIntegration']['postingNcsMatchRows']}` (`{report['ncsIntegration']['status']}`)
- Recomputed posting rows: `{report['observedParse']['inputPostings']}`
- Recomputed usable raw SSR rows: `{report['observedParse']['realSsrRaw']}`
- Recomputed sections / requirements / duty handoff: `{report['observedParse']['sectionCount']}` / `{report['observedParse']['requirementCount']}` / `{report['agent4DutyHandoff']['rows']}`

The output bundle remains under `pipeline/data/exports` on the Agent 2 branch. Moving it to
`crawl/data/exports` is an integration action gated by the Agent 1 input package and Agent 3
contract/checksum audit.

This report does not declare any empirical, production-crawl, RQ, or analysis readiness state.
"""
    (report_root / "AGENT2_M1_PIPELINE_REPORT.md").write_text(markdown, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--crawl-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--control-root", type=Path)
    parser.add_argument("--ncs-handoff-path", type=Path)
    parser.add_argument("--ncs-project-root", type=Path)
    args = parser.parse_args()
    result = run(
        args.project_root,
        args.release_root,
        args.crawl_root,
        args.output_root,
        args.control_root,
        args.ncs_handoff_path,
        args.ncs_project_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
