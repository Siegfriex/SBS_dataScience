#!/usr/bin/env python3
"""Execute the unified 23-stage observed reconciliation in DAG order.

The wrapper records runtime evidence immediately around each execution.  It
never performs production transport and refuses to overwrite a prior run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from a4_reconciliation_runtime import run_a4_stage
from unified_reconciliation_contract import EXECUTION_ORDER, STAGE_DEPENDENCIES


A1_STAGE_NOTEBOOKS = {
    "A1-00-RECOVER": "crawl/notebooks/00RecoverSourceState.ipynb",
    "A1-01-INDEX": "crawl/notebooks/01CollectLinkareerIndex.ipynb",
    "A1-02-DETAIL": "crawl/notebooks/02CollectPostingDetail.ipynb",
    "A1-03-ASSET": "crawl/notebooks/03CollectPostingAssets.ipynb",
    "A1-04-RELEASE": "crawl/notebooks/04BuildCrawlRelease.ipynb",
}
A2_STAGE_NOTEBOOKS = {
    "A2-00-CONTRACT": ("00ContractAndInputAudit.ipynb", "00ContractAndInputAudit"),
    "A2-01-LOAD": ("01LoadCrawlRelease.ipynb", "01LoadCrawlRelease"),
    "A2-02-NORMALIZE": ("02ParseAndNormalize.ipynb", "02ParseAndNormalize"),
    "A2-03-OCR": ("03OcrAndSectionRecovery.ipynb", "03OcrAndSectionRecovery"),
    "A2-04-TRACK": ("04SplitTracks.ipynb", "04SplitTracks"),
    "A2-05-REQUIREMENT": ("05ExtractRequirements.ipynb", "05ExtractRequirements"),
    "A2-06-DEDUP": ("06Deduplicate90Days.ipynb", "06Deduplicate90Days"),
    "A2-07-LABEL": ("07LabelCareerAccess.ipynb", "07LabelCareerAccess"),
    "A2-08-NCS-LOAD": ("08LoadAndPrepareNcs.ipynb", "08LoadAndPrepareNcs"),
    "A2-09-NCS-MAP": ("09MapPostingToNcs.ipynb", "09MapPostingToNcs"),
    "A2-10-EXPORT": ("10ExportPreprocessedCsv.ipynb", "10ExportPreprocessedCsv"),
    "A2-11-QA": ("11PreprocessedDataQa.ipynb", "11PreprocessedDataQa"),
}
A4_STAGE_NOTEBOOKS = {
    "A4-00-NCS-SOURCE": "ncs_mapping/notebooks/00NcsSourceAudit.ipynb",
    "A4-01-CODESET": "ncs_mapping/notebooks/01BuildCoreAiItCodeSet.ipynb",
    "A4-02-RETRIEVAL": "ncs_mapping/notebooks/02BuildNcsRetrievalIndex.ipynb",
    "A4-03-MAP-OBSERVED": "ncs_mapping/notebooks/03MapObservedDuties.ipynb",
    "A4-04-EXPORT": "ncs_mapping/notebooks/04ExportNcsMappingCsv.ipynb",
    "A4-05-EVALUATE": "ncs_mapping/notebooks/05EvaluateNcsMapping.ipynb",
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def module_tree_sha(project: Path, owner: str) -> str:
    source_root = {
        "A1": project / "crawl/src/p4_crawl",
        "A2": project / "pipeline/src/p4",
        "A4": project / "ncs_mapping/src/p4_ncs",
    }[owner]
    rows = [f"{path.relative_to(project).as_posix()}\0{sha_file(path)}" for path in sorted(source_root.rglob("*.py"))]
    return canonical_sha(rows)


def command_sha(stage_id: str, run_id: str, data_version: str, mode: str) -> str:
    return canonical_sha({
        "stageId": stage_id, "runId": run_id, "dataVersion": data_version,
        "mode": mode, "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
    })


def write_ledger(path: Path, run_id: str, data_version: str, runner_id: str, rows: list[dict[str, Any]]) -> None:
    payload = {
        "ledgerVersion": "p4-unified-runtime-ledger-v1",
        "runId": run_id, "dataVersion": data_version,
        "executionHostOrRunnerId": runner_id,
        "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0, "stageCount": len(rows), "stages": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--runner-id", default="LOCAL_FRESH_KERNEL_WRAPPER")
    parser.add_argument("--kernel", default="python3")
    args = parser.parse_args()
    project = args.project_root.resolve()
    raw_root = args.raw_root.resolve()
    integration_run = project / "integration/runs" / args.run_id
    a1_run = project / "crawl/runs/notebooks/observed-dev" / f"{args.run_id}_A1"
    a2_run = project / "pipeline/runs/notebooks/observed-dev" / args.run_id
    for path in (integration_run, a1_run, a2_run):
        if path.exists():
            raise RuntimeError(f"run root already exists; refusing overwrite: {path}")
    integration_run.mkdir(parents=True)
    export_root = integration_run / "pipeline_export"
    database = integration_run / "warehouse/p4.observed-dev.duckdb"
    database.parent.mkdir(parents=True)
    ledger_path = integration_run / "P4_RUNTIME_EXECUTION_LEDGER.json"
    module_shas = {owner: module_tree_sha(project, owner) for owner in ("A1", "A2", "A4")}
    ledger_rows: list[dict[str, Any]] = []

    env = os.environ.copy()
    env["P4_CRAWL_RAW_SOURCE_ROOT"] = str(raw_root)
    env["P4_OBSERVED_DATABASE_PATH"] = str(database)
    env["PYTHONPATH"] = os.pathsep.join((str(project / "pipeline/src"), str(project / "ncs_mapping/src"), env.get("PYTHONPATH", "")))

    # A1 currently exposes one authority wrapper for its five sequential stages.
    a1_started = utc_now()
    a1_command = [
        sys.executable, "crawl/scripts/execute_agent1_notebooks.py",
        "--run-root", a1_run.relative_to(project).as_posix(),
        "--data-version", args.data_version,
    ]
    subprocess.run(a1_command, cwd=project, env=env, check=True)
    a1_completed = utc_now()
    with (a1_run / "NOTEBOOK_EXECUTION_RESULTS.csv").open(encoding="utf-8-sig", newline="") as stream:
        a1_rows = {row["stageId"]: row for row in csv.DictReader(stream)}
    for stage_id in A1_STAGE_NOTEBOOKS:
        row = a1_rows[stage_id]
        native = a1_run / stage_id / "stage_manifest.json"
        payload = json.loads(native.read_text(encoding="utf-8"))
        source = project / A1_STAGE_NOTEBOOKS[stage_id]
        ledger_rows.append({
            "stageId": stage_id, "owner": "A1", "runId": args.run_id,
            "dataVersion": args.data_version, "executionOrder": EXECUTION_ORDER.index(stage_id),
            "dependencyStageIds": list(STAGE_DEPENDENCIES[stage_id]),
            "startedAtUtc": row.get("runtimeStartedAtUtc") or a1_started,
            "completedAtUtc": row.get("runtimeEndedAtUtc") or a1_completed,
            "executionHostOrRunnerId": args.runner_id,
            "executionCommandSha256": command_sha(stage_id, args.run_id, args.data_version, "A1_FRESH_KERNEL"),
            "sourceNotebookSha256": sha_file(source), "moduleBlobSha256": module_shas["A1"],
            "inputManifestSha256": payload["inputManifestSha256"], "outputManifestSha256": sha_file(native),
            "status": payload["status"], "timestampSource": "EXECUTION_WRAPPER_CAPTURED",
            "nativeEvidencePath": native.relative_to(project).as_posix(),
            "nativeEvidenceSha256": sha_file(native),
            "metrics": {"executedStatus": row["status"]},
        })
    write_ledger(ledger_path, args.run_id, args.data_version, args.runner_id, ledger_rows)

    for stage_id in EXECUTION_ORDER[5:]:
        started = utc_now()
        if stage_id.startswith("A2-"):
            notebook, native_id = A2_STAGE_NOTEBOOKS[stage_id]
            command = [
                sys.executable, "pipeline/scripts/execute_notebooks.py", "--mode", "observed-dev",
                "--notebook", notebook, "--project-root", str(project),
                "--release-root", str(project / "crawl/observed_inputs/OBSERVED_INPUT_20260806_01"),
                "--crawl-root", str(raw_root), "--output-root", str(export_root),
                "--control-root", str(project / "crawl/control"),
                "--ncs-project-root", str(project),
                "--ncs-handoff-path", str(project / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"),
                "--kernel", args.kernel, "--run-id", args.run_id, "--save-executed",
            ]
            subprocess.run(command, cwd=project, env=env, check=True)
            completed = utc_now()
            native = a2_run / "artifacts" / native_id / "stage_manifest.json"
            payload = json.loads(native.read_text(encoding="utf-8"))
            source = project / "pipeline/notebooks" / notebook
            result = {"nativeStageId": native_id}
            mode = "A2_FRESH_KERNEL"
        else:
            result = run_a4_stage(project, stage_id)
            completed = utc_now()
            source = project / A4_STAGE_NOTEBOOKS[stage_id]
            native = project / "ncs_mapping/reports/reconciliation_a4/A4_STAGE_AUTHORITY_MANIFEST.csv"
            payload = {"inputManifestSha256": result["input"], "status": result["status"]}
            mode = "A4_DETERMINISTIC_READ_ONLY"
        owner = stage_id[:2]
        ledger_rows.append({
            "stageId": stage_id, "owner": owner, "runId": args.run_id,
            "dataVersion": args.data_version, "executionOrder": EXECUTION_ORDER.index(stage_id),
            "dependencyStageIds": list(STAGE_DEPENDENCIES[stage_id]),
            "startedAtUtc": started, "completedAtUtc": completed,
            "executionHostOrRunnerId": args.runner_id,
            "executionCommandSha256": command_sha(stage_id, args.run_id, args.data_version, mode),
            "sourceNotebookSha256": sha_file(source), "moduleBlobSha256": module_shas[owner],
            "inputManifestSha256": payload["inputManifestSha256"],
            "outputManifestSha256": sha_file(native) if owner == "A2" else canonical_sha(result),
            "status": payload["status"], "timestampSource": "EXECUTION_WRAPPER_CAPTURED",
            "nativeEvidencePath": native.relative_to(project).as_posix(),
            "nativeEvidenceSha256": sha_file(native), "metrics": result,
        })
        write_ledger(ledger_path, args.run_id, args.data_version, args.runner_id, ledger_rows)

    if [row["stageId"] for row in sorted(ledger_rows, key=lambda row: row["executionOrder"])] != list(EXECUTION_ORDER):
        raise AssertionError("runtime ledger does not cover the canonical 23-stage order")
    print(json.dumps({
        "runId": args.run_id, "dataVersion": args.data_version, "executedStages": len(ledger_rows),
        "runtimeLedger": ledger_path.relative_to(project).as_posix(), "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
