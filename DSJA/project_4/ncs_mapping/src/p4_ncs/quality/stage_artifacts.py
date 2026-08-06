"""Agent 3 contract-compatible stage termination artifacts."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

TERMINATION_ARTIFACTS = [
    "stage_manifest.json",
    "stage_metrics.json",
    "stage_quality.csv",
    "CHECKSUMS.sha256",
]
QUALITY_COLUMNS = [
    "gateId", "ruleId", "severity", "status", "observedValue", "threshold", "evidencePath"
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_value(ncs_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ncs_root, text=True).strip()


@dataclass(frozen=True)
class StageContext:
    ncs_root: Path
    stage_id: str
    schema_version: str
    data_version: str = "observed-dev-20260806.1"
    run_id: str = "NCS_MAPPING_OBSERVED_20260806_01"
    run_mode: str = "observed-dev"
    contract_version: str = "2.1.2"
    crawl_release_id: str = "CRAWL_20260806_03"
    data_provenance: str = "OBSERVED_DEVELOPMENT_ONLY"

    @property
    def stage_dir(self) -> Path:
        return self.ncs_root / "data" / "runs" / self.run_mode / self.run_id / self.stage_id


def file_record(
    path: Path,
    ncs_root: Path,
    source_stage: str,
    grain: str,
    rows: int | None,
    columns: int | None,
) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(ncs_root.resolve().parent).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "columns": columns,
        "format": path.suffix.lstrip(".") or "text",
        "grain": grain,
        "nullablePolicy": "schema-defined nullable values preserved",
        "sourceStage": source_stage,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
    }


def write_stage_artifacts(
    context: StageContext,
    input_manifest_sha256: str,
    row_counts: dict[str, int],
    metrics: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
    business_files: list[dict[str, Any]],
    warnings: list[str] | None = None,
    schema_dir: Path | None = None,
) -> dict[str, Any]:
    """Write exactly four termination artifacts and optionally validate JSON schemas."""
    stage_dir = context.stage_dir
    stage_dir.mkdir(parents=True, exist_ok=True)
    for child in stage_dir.iterdir():
        if child.is_file() and child.name not in TERMINATION_ARTIFACTS:
            raise ValueError(f"unexpected file in stage artifact directory: {child.name}")
    started_at = utc_now()
    parameters = {
        "runMode": context.run_mode,
        "contractVersion": context.contract_version,
        "crawlReleaseId": context.crawl_release_id,
        "dataVersion": context.data_version,
        "dataProvenance": context.data_provenance,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
    }
    quality = pd.DataFrame(quality_rows, columns=QUALITY_COLUMNS)
    quality_path = stage_dir / "stage_quality.csv"
    quality.to_csv(quality_path, index=False, encoding="utf-8-sig")
    gate_results = [
        {
            "gateId": str(row["gateId"]),
            "status": str(row["status"]),
            "evidencePath": str(row["evidencePath"]),
        }
        for row in quality_rows
    ]
    completed_at = utc_now()
    manifest = {
        "manifestVersion": "stage-manifest-v1",
        "runId": context.run_id,
        "runMode": context.run_mode,
        "stageId": context.stage_id,
        "status": "FAILED" if any(row["status"] == "FAIL" for row in quality_rows) else "SUCCEEDED",
        "agentId": "P4-A4-NCS",
        "branch": _git_value(context.ncs_root, "branch", "--show-current"),
        "gitHead": _git_value(context.ncs_root, "rev-parse", "HEAD"),
        "contractVersion": context.contract_version,
        "schemaVersion": context.schema_version,
        "dataVersion": context.data_version,
        "crawlReleaseId": context.crawl_release_id,
        "dataProvenance": context.data_provenance,
        "startedAt": started_at,
        "completedAt": completed_at,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "inputManifestSha256": input_manifest_sha256,
        "parameterSha256": canonical_sha(parameters),
        "rowCounts": row_counts,
        "gateResults": gate_results,
        "warnings": list(warnings or []),
        "errors": [str(row["ruleId"]) for row in quality_rows if row["status"] == "FAIL"],
        "files": business_files,
        "terminationArtifacts": TERMINATION_ARTIFACTS,
        "dataPolicies": {
            "canonicalStorage": "DUCKDB_PARQUET",
            "csvPurpose": "HUMAN_INSPECTION_EXPORT",
            "eligibilityColumns": [
                "postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag"
            ],
            "highDemandScore": "ALL_NULL",
        },
        "mappingPolicy": {
            "mappingMode": "LEXICAL_BASELINE",
            "codeSetStatus": "REVIEW_REQUIRED",
            "goldValidatedFlag": False,
            "denseScore": None,
        },
    }
    metrics_document = {
        "metricsVersion": "stage-metrics-v1",
        "runId": context.run_id,
        "runMode": context.run_mode,
        "stageId": context.stage_id,
        "contractVersion": context.contract_version,
        "crawlReleaseId": context.crawl_release_id,
        "dataVersion": context.data_version,
        "dataProvenance": context.data_provenance,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "generatedAt": completed_at,
        "metrics": metrics,
    }
    manifest_path = stage_dir / "stage_manifest.json"
    metrics_path = stage_dir / "stage_metrics.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if schema_dir is not None:
        from jsonschema import Draft202012Validator

        manifest_schema = json.loads((schema_dir / "STAGE_MANIFEST.schema.json").read_text(encoding="utf-8"))
        metrics_schema = json.loads((schema_dir / "STAGE_METRICS.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(manifest_schema).validate(manifest)
        Draft202012Validator(metrics_schema).validate(metrics_document)

    checksum_lines = [
        f"{sha256_file(stage_dir / name)}  {name}"
        for name in TERMINATION_ARTIFACTS
        if name != "CHECKSUMS.sha256"
    ]
    (stage_dir / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    actual_names = sorted(path.name for path in stage_dir.iterdir() if path.is_file())
    if actual_names != sorted(TERMINATION_ARTIFACTS):
        raise AssertionError(f"termination artifact set mismatch: {actual_names}")
    return manifest
