#!/usr/bin/env python3
"""Validate the integrated Master plan without executing child Notebooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawl.control.notebook_bundle import (  # noqa: E402
    dependency_order_audit,
    notebook_plan,
    repository_architecture,
    source_blob_provenance,
    write_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    output = (PROJECT_ROOT / args.output_root).resolve()
    if not output.is_relative_to(PROJECT_ROOT / "crawl/runs"):
        raise ValueError("dry-run output must stay under crawl/runs")
    output.mkdir(parents=True, exist_ok=True)

    plan = notebook_plan(PROJECT_ROOT)
    dependencies = dependency_order_audit(PROJECT_ROOT, plan)
    architecture = repository_architecture(PROJECT_ROOT)
    blobs = source_blob_provenance(PROJECT_ROOT)
    missing = [row for row in architecture if not row["exists"] and row["stageId"] != "A3-MASTER"]
    payload = {
        "mode": "MASTER_DRY_RUN",
        "plannedChildStages": len(plan),
        "dependencyEdges": len(dependencies),
        "dependencyFailures": sum(row["status"] != "PASS" for row in dependencies),
        "crawlNotebookBlobCoverage": f"{sum(row['workingTreeMatchesGitBlob'] for row in blobs)}/{len(blobs)}",
        "missingReadOnlyOwnerSources": len(missing),
        "childKernelsStarted": 0,
        "networkCalls": 0,
        "status": "READY" if not missing else "CONTROL_READY_FULL_REPLAY_BLOCKED_BY_HANDOFF",
        "promotionAllowed": False,
    }
    write_csv(output / "CRAWL_STAGE_DEPENDENCY_GRAPH.csv", dependencies)
    write_csv(output / "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv", blobs)
    write_csv(output / "MISSING_READ_ONLY_OWNER_SOURCES.csv", missing)
    (output / "MASTER_DRY_RUN.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["dependencyFailures"] == 0 and payload["crawlNotebookBlobCoverage"] == "6/6" else 1


if __name__ == "__main__":
    raise SystemExit(main())
