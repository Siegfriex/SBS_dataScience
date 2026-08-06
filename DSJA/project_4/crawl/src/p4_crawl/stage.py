"""Common stage artifacts for thin orchestration notebooks."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

from .config import AGENT_ID
from .manifests import write_checksums
from .storage import atomic_write_json


def git_value(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def notebook_metadata(config, started_at: str) -> dict[str, Any]:
    return {
        "agentId": AGENT_ID,
        "branch": git_value(config.project_root, "branch", "--show-current"),
        "gitHead": git_value(config.project_root, "rev-parse", "HEAD"),
        "contractVersion": config.contract_version,
        "crawlReleaseId": config.crawl_release_id,
        "dataVersion": config.data_version,
        "runMode": config.run_mode,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY" if config.run_mode == "observed-dev" else "PRODUCTION_CRAWL",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "startedAt": started_at,
    }


def write_stage_artifacts(
    config,
    stage_id: str,
    started_at: str,
    metrics: dict[str, Any],
    quality_rows: list[dict[str, Any]],
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> Path:
    root = config.run_root / "stages" / stage_id
    root.mkdir(parents=True, exist_ok=True)
    quality_path = root / "stage_quality.csv"
    fieldnames = sorted({key for row in quality_rows for key in row}) or ["gate", "status", "detail"]
    with quality_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(quality_rows)
    atomic_write_json(root / "stage_metrics.json", metrics)
    manifest = {
        **notebook_metadata(config, started_at),
        "stageId": stage_id,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "stageStatus": "PASS" if all(row.get("status") == "PASS" for row in quality_rows) else "FAIL",
    }
    atomic_write_json(root / "stage_manifest.json", manifest)
    write_checksums(root, ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv"])
    return root
