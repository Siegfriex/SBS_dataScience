"""Agent 3-compatible termination artifacts for thin notebooks."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any

from .config import AGENT_ID
from .storage import atomic_write_json, canonical_json, sha256_bytes, sha256_file

TERMINATION_ARTIFACTS = ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"]
DATA_POLICIES = {
    "canonicalStorage": "DUCKDB_PARQUET",
    "csvPurpose": "HUMAN_INSPECTION_EXPORT",
    "eligibilityColumns": ["postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag"],
    "highDemandScore": "ALL_NULL",
}


def git_head(project_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _file_shape(path: Path) -> tuple[int | None, int | None]:
    if path.suffix == ".csv":
        import pandas as pd
        frame = pd.read_csv(path, encoding="utf-8-sig")
        return len(frame), len(frame.columns)
    if path.suffix == ".parquet":
        import pandas as pd
        frame = pd.read_parquet(path)
        return len(frame), len(frame.columns)
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), None
    return None, None


def _format(path: Path) -> str:
    return {".json": "json", ".jsonl": "jsonl", ".csv": "csv", ".parquet": "parquet", ".sha256": "sha256"}.get(path.suffix, "binary")


def write_stage_artifacts(
    *, config, stage_id: str, schema_version: str, started_at: str,
    parameters: dict[str, Any], input_manifest_path: Path, stage_root: Path,
    metric_values: dict[str, Any], quality_rows: list[dict[str, Any]],
    persisted_files: list[Path], warnings: list[str] | None = None,
    errors: list[str] | None = None, branch: str = "agent/p4-crawl-release-v2",
) -> dict:
    stage_root.mkdir(parents=True, exist_ok=True)
    warnings, errors = warnings or [], errors or []
    quality_columns = ["gateId", "ruleId", "severity", "status", "observedValue", "threshold", "evidencePath"]
    with (stage_root / "stage_quality.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=quality_columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in quality_columns} for row in quality_rows])

    metrics = []
    for metric_id, value in metric_values.items():
        numeric = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        metrics.append({
            "metricId": metric_id,
            "value": value if isinstance(value, (int, float, str, bool)) or value is None else canonical_json(value),
            "numerator": numeric,
            "denominator": None,
            "unit": "count" if numeric is not None else "value",
            "grain": stage_id,
            "unknownHandling": "preserve_unknown",
            "status": "INFORMATIONAL",
        })
    atomic_write_json(stage_root / "stage_metrics.json", {
        "metricsVersion": "stage-metrics-v1", "runId": config.data_version,
        "runMode": config.run_mode, "stageId": stage_id, "contractVersion": config.contract_version,
        "crawlReleaseId": config.crawl_release_id, "dataVersion": config.data_version,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY", "empiricalAnalysisAllowed": False,
        "promotionAllowed": False, "generatedAt": started_at, "metrics": metrics,
    })

    files = []
    row_counts: dict[str, int] = {}
    for path in sorted(set(persisted_files)):
        rows, columns = _file_shape(path)
        files.append({
            "path": path.relative_to(config.project_root).as_posix(), "sha256": sha256_file(path),
            "bytes": path.stat().st_size, "rows": rows, "columns": columns, "format": _format(path),
            "grain": stage_id, "nullablePolicy": "schema_defined", "sourceStage": stage_id,
            "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        })
        if rows is not None:
            row_counts[path.stem] = rows
    gate_results = [{"gateId": row["gateId"], "status": row["status"], "evidencePath": row["evidencePath"]} for row in quality_rows]
    failed = any(row["status"] == "FAIL" for row in quality_rows)
    manifest = {
        "manifestVersion": "stage-manifest-v1", "runId": config.data_version, "runMode": config.run_mode,
        "stageId": stage_id, "status": "FAILED" if failed else "SUCCEEDED", "agentId": AGENT_ID,
        "branch": branch, "gitHead": git_head(config.project_root), "contractVersion": config.contract_version,
        "schemaVersion": schema_version, "dataVersion": config.data_version, "crawlReleaseId": config.crawl_release_id,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY", "startedAt": started_at, "completedAt": started_at,
        "empiricalAnalysisAllowed": False, "promotionAllowed": False,
        "inputManifestSha256": sha256_file(input_manifest_path),
        "parameterSha256": sha256_bytes(canonical_json(parameters).encode("utf-8")), "rowCounts": row_counts,
        "gateResults": gate_results, "warnings": warnings, "errors": errors, "files": files,
        "terminationArtifacts": TERMINATION_ARTIFACTS, "dataPolicies": DATA_POLICIES,
    }
    atomic_write_json(stage_root / "stage_manifest.json", manifest)
    checksum_files = sorted(set(persisted_files + [stage_root / "stage_manifest.json", stage_root / "stage_metrics.json", stage_root / "stage_quality.csv"]))
    lines = [f"{sha256_file(path)}  {path.relative_to(stage_root).as_posix()}" for path in checksum_files]
    (stage_root / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return manifest
