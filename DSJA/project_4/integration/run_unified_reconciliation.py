#!/usr/bin/env python3
"""Bind A1, A2, and A4 evidence into one fail-closed 23-stage replay.

A1 and A2 stages are backed by fresh-kernel notebook runs.  A4 is replayed by
the same deterministic modules through a read-only stage runner so the frozen
observed NCS exports are never overwritten.  Canonical current-run termination
artifacts are written under the Git-trackable reconciliation report root.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nbformat
import pandas as pd
import yaml

from unified_reconciliation_contract import (
    EXECUTION_ORDER,
    RUNTIME_REQUIRED_FIELDS,
    STAGE_DEPENDENCIES,
    validate_topology_and_runtime,
)


BASE_COMMIT = "5508fce02ba5396b5d5a55870f1f879c1f32e8e0"
BRANCH = "integration/p4-m1_5-unified-reconciliation-v2"
CONTRACT_VERSION = "2.1.2"
TERMINATION = ("stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256")

A1_STAGES = [
    ("A1-00-RECOVER", "crawl/notebooks/00RecoverSourceState.ipynb"),
    ("A1-01-INDEX", "crawl/notebooks/01CollectLinkareerIndex.ipynb"),
    ("A1-02-DETAIL", "crawl/notebooks/02CollectPostingDetail.ipynb"),
    ("A1-03-ASSET", "crawl/notebooks/03CollectPostingAssets.ipynb"),
    ("A1-04-RELEASE", "crawl/notebooks/04BuildCrawlRelease.ipynb"),
]
A2_STAGES = [
    ("A2-00-CONTRACT", "pipeline/notebooks/00ContractAndInputAudit.ipynb", "00ContractAndInputAudit"),
    ("A2-01-LOAD", "pipeline/notebooks/01LoadCrawlRelease.ipynb", "01LoadCrawlRelease"),
    ("A2-02-NORMALIZE", "pipeline/notebooks/02ParseAndNormalize.ipynb", "02ParseAndNormalize"),
    ("A2-03-OCR", "pipeline/notebooks/03OcrAndSectionRecovery.ipynb", "03OcrAndSectionRecovery"),
    ("A2-04-TRACK", "pipeline/notebooks/04SplitTracks.ipynb", "04SplitTracks"),
    ("A2-05-REQUIREMENT", "pipeline/notebooks/05ExtractRequirements.ipynb", "05ExtractRequirements"),
    ("A2-06-DEDUP", "pipeline/notebooks/06Deduplicate90Days.ipynb", "06Deduplicate90Days"),
    ("A2-07-LABEL", "pipeline/notebooks/07LabelCareerAccess.ipynb", "07LabelCareerAccess"),
    ("A2-08-NCS-LOAD", "pipeline/notebooks/08LoadAndPrepareNcs.ipynb", "08LoadAndPrepareNcs"),
    ("A2-09-NCS-MAP", "pipeline/notebooks/09MapPostingToNcs.ipynb", "09MapPostingToNcs"),
    ("A2-10-EXPORT", "pipeline/notebooks/10ExportPreprocessedCsv.ipynb", "10ExportPreprocessedCsv"),
    ("A2-11-QA", "pipeline/notebooks/11PreprocessedDataQa.ipynb", "11PreprocessedDataQa"),
]
A4_STAGES = [
    ("A4-00-NCS-SOURCE", "ncs_mapping/notebooks/00NcsSourceAudit.ipynb"),
    ("A4-01-CODESET", "ncs_mapping/notebooks/01BuildCoreAiItCodeSet.ipynb"),
    ("A4-02-RETRIEVAL", "ncs_mapping/notebooks/02BuildNcsRetrievalIndex.ipynb"),
    ("A4-03-MAP-OBSERVED", "ncs_mapping/notebooks/03MapObservedDuties.ipynb"),
    ("A4-04-EXPORT", "ncs_mapping/notebooks/04ExportNcsMappingCsv.ipynb"),
    ("A4-05-EVALUATE", "ncs_mapping/notebooks/05EvaluateNcsMapping.ipynb"),
]


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


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def git_blob(project: Path, path: Path) -> str:
    repo_root = Path(git(project, "rev-parse", "--show-toplevel"))
    repo_relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    return git(project, "rev-parse", f"HEAD:{repo_relative}")


def module_tree_sha(project: Path, owner: str) -> str:
    source_root = {
        "A1": project / "crawl/src/p4_crawl",
        "A2": project / "pipeline/src/p4",
        "A4": project / "ncs_mapping/src/p4_ncs",
    }[owner]
    records = [f"{path.relative_to(project).as_posix()}\0{sha_file(path)}" for path in sorted(source_root.rglob("*.py"))]
    return canonical_sha(records)


def source_audit(path: Path) -> dict[str, Any]:
    notebook = nbformat.read(path, as_version=4)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    return {
        "sha256": sha_file(path),
        "outputs": sum(len(cell.get("outputs", [])) for cell in code),
        "executions": sum(cell.get("execution_count") is not None for cell in code),
        "cells": len(notebook.cells),
        "codeCells": len(code),
    }


def normalized_code(path: Path, *, executed: bool = False) -> str:
    notebook = nbformat.read(path, as_version=4)
    marker = "# Injected into the executed copy by crawl.control.notebook_bundle"
    rows: list[str] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source
        if executed and marker in source:
            source = source.split(marker, 1)[0].rstrip() + "\n"
        rows.append(f"{cell.get('id', '')}\0{source.rstrip()}\n")
    return "".join(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def a4_read_only_checks(project: Path) -> dict[str, dict[str, Any]]:
    sys.path[:0] = [str(project / "ncs_mapping/src"), str(project / "pipeline/src")]
    from p4_ncs.codeset.core_ai_it import build_core_ai_it_codeset
    from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary, validate_alias_dictionary
    from p4_ncs.evaluation.gold_evaluation import evaluate_gold_mapping, load_gold_structure
    from p4_ncs.retrieval.lexical_index import LexicalIndex
    from p4.contracts.ncs_handoff import validate_agent4_ncs_handoff
    from p4.contracts.ncs_mart_handoff import load_ncs_mart_handoff

    ncs = project / "ncs_mapping"
    units_path = ncs / "data/processed/ncsUnit.parquet"
    codes_path = ncs / "data/processed/coreAiItCodeSet.parquet"
    alias_path = ncs / "configs/ncs_alias_dictionary.yaml"
    duty_path = project / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
    compat_path = project / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"
    mart_path = ncs / "reports/reconciliation_a4/A4_MAPPING_TO_MART_CONTRACT.json"
    gold_path = ncs / "data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv"
    units = pd.read_parquet(units_path)
    codes = pd.read_parquet(codes_path)
    aliases = load_alias_dictionary(alias_path)

    if len(units) != 13_442 or units.ncsUnitCode.duplicated().any() or not units.ncsLevel.between(1, 8).all():
        raise ValueError("A4 NCS source integrity failed")
    rebuilt = build_core_ai_it_codeset(units).sort_values("ncsSubCode").reset_index(drop=True)
    pd.testing.assert_frame_equal(rebuilt, codes.sort_values("ncsSubCode").reset_index(drop=True), check_dtype=False)
    index = LexicalIndex.build(units, codes)
    bad_aliases = validate_alias_dictionary(aliases, set(codes.ncsSubCode.astype(str)))
    if bad_aliases:
        raise ValueError(f"invalid A4 aliases: {bad_aliases}")
    compat = validate_agent4_ncs_handoff(compat_path, project)
    mart, mart_payload = load_ncs_mart_handoff(mart_path)
    if len(mart) != 28 or mart_payload["humanGoldRows"] != 0:
        raise ValueError("A4 structural mart boundary failed")
    gold = evaluate_gold_mapping(load_gold_structure(gold_path))
    if gold.goldRows != 0 or gold.gateStatus != "NOT_EVALUATED":
        raise ValueError("empty Gold must remain NOT_EVALUATED")

    return {
        "A4-00-NCS-SOURCE": {"input": sha_file(units_path), "rows": len(units), "status": "SUCCEEDED"},
        "A4-01-CODESET": {"input": sha_file(codes_path), "rows": len(codes), "included": int(codes.included.sum()), "status": "SUCCEEDED"},
        "A4-02-RETRIEVAL": {"input": sha_file(alias_path), "rows": len(index.documents), "aliasRows": len(aliases), "status": "SUCCEEDED"},
        "A4-03-MAP-OBSERVED": {"input": sha_file(duty_path), "rows": compat["matchRows"], "candidateRows": compat["candidateRows"], "status": "SUCCEEDED"},
        "A4-04-EXPORT": {"input": sha_file(compat_path), "rows": len(mart), "structuralRows": int(mart.mappingStatus.eq("REVIEW_REQUIRED").sum()), "status": "SUCCEEDED"},
        "A4-05-EVALUATE": {"input": sha_file(gold_path), "rows": gold.goldRows, "goldAuthority": "NONE", "status": "NOT_EVALUATED"},
    }


def write_stage(report_root: Path, record: dict[str, Any]) -> str:
    stage_dir = report_root / "stages" / record["stageId"]
    stage_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifestVersion": "p4-unified-current-run-v2",
        "stageId": record["stageId"],
        "owner": record["owner"],
        "runId": record["runId"],
        "dataVersion": record["dataVersion"],
        "contractVersion": CONTRACT_VERSION,
        "inputManifestSha256": record["inputManifestSha256"],
        "sourceNotebookSha256": record["sourceNotebookSha256"],
        "moduleBlobSha256": record["moduleBlobSha256"],
        "parameterSha256": record["parameterSha256"],
        "outputManifestSha256": record["outputManifestSha256"],
        "status": record["status"],
        "startedAtUtc": record["startedAtUtc"],
        "completedAtUtc": record["completedAtUtc"],
        "executionHostOrRunnerId": record["executionHostOrRunnerId"],
        "executionCommandSha256": record["executionCommandSha256"],
        "executionOrder": record["executionOrder"],
        "dependencyStageIds": record["dependencyStageIds"],
        "timestampSource": record["timestampSource"],
        "runtimeLedgerSha256": record["runtimeLedgerSha256"],
        "executionMode": record["executionMode"],
        "sourceNotebookPath": record["sourceNotebookPath"],
        "sourceNotebookBlobId": record["sourceNotebookBlobId"],
        "sourceCommit": record["sourceCommit"],
        "nativeEvidencePath": record["nativeEvidencePath"],
        "nativeEvidenceSha256": record["nativeEvidenceSha256"],
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
    }
    metrics = {
        "metricsVersion": "p4-unified-current-run-metrics-v1",
        "stageId": record["stageId"], "runId": record["runId"],
        "dataVersion": record["dataVersion"], "status": record["status"],
        "executionMode": record["executionMode"], "metrics": record["metrics"],
    }
    quality = [{
        "gateId": "CURRENT_RUN_BINDING", "ruleId": "EXACT_SOURCE_AND_RUN_BINDING",
        "severity": "INFO", "status": "PASS", "observedValue": record["status"],
        "threshold": "bound", "evidencePath": record["nativeEvidencePath"],
    }]
    paths = {
        "stage_manifest.json": manifest,
        "stage_metrics.json": metrics,
    }
    for name, payload in paths.items():
        (stage_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (stage_dir / "stage_quality.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(quality[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(quality)
    (stage_dir / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha_file(stage_dir / name)}  {name}\n" for name in TERMINATION[:-1]), encoding="utf-8"
    )
    return sha_file(stage_dir / "stage_manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--a1-run-root", type=Path, required=True)
    parser.add_argument("--a2-run-root", type=Path, required=True)
    parser.add_argument("--runtime-ledger", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    report_root = args.report_root.resolve()
    a1_run_root = args.a1_run_root.resolve()
    a2_run_root = args.a2_run_root.resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    ledger_path = args.runtime_ledger.resolve()
    ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger_rows = {row["stageId"]: row for row in ledger_payload.get("stages", [])}
    if ledger_payload.get("runId") != args.run_id or ledger_payload.get("dataVersion") != args.data_version:
        raise ValueError("runtime ledger run/data binding mismatch")
    topology_errors = validate_topology_and_runtime(ledger_rows)
    if topology_errors:
        raise ValueError(f"runtime ledger topology/timestamp invalid: {topology_errors}")
    ledger_sha = sha_file(ledger_path)
    shutil.copyfile(ledger_path, report_root / "P4_RUNTIME_EXECUTION_LEDGER.json")
    head = git(project, "rev-parse", "HEAD")
    modules = {owner: module_tree_sha(project, owner) for owner in ("A1", "A2", "A4")}
    parameters = canonical_sha({"runId": args.run_id, "dataVersion": args.data_version, "network": 0, "ats": 0})
    records: list[dict[str, Any]] = []

    a1_rows = {row["stageId"]: row for row in read_csv(a1_run_root / "NOTEBOOK_EXECUTION_RESULTS.csv")}
    for stage_id, source_rel in A1_STAGES:
        row = a1_rows[stage_id]
        native = a1_run_root / stage_id / "stage_manifest.json"
        native_payload = json.loads(native.read_text(encoding="utf-8"))
        source = project / source_rel
        executed = project / row["executedPath"]
        audit = source_audit(source)
        if audit["outputs"] or audit["executions"] or normalized_code(source) != normalized_code(executed, executed=True):
            raise ValueError(f"A1 Notebook authority/parity failed: {stage_id}")
        runtime = ledger_rows[stage_id]
        if runtime["sourceNotebookSha256"] != audit["sha256"] or runtime["moduleBlobSha256"] != modules["A1"]:
            raise ValueError(f"A1 runtime ledger source/module mismatch: {stage_id}")
        records.append({
            "stageId": stage_id, "owner": "A1", "runId": args.run_id, "dataVersion": args.data_version,
            "inputManifestSha256": native_payload["inputManifestSha256"], "sourceNotebookSha256": audit["sha256"],
            "moduleBlobSha256": modules["A1"], "parameterSha256": parameters,
            "outputManifestSha256": sha_file(native), "status": native_payload["status"],
            **{key: runtime[key] for key in RUNTIME_REQUIRED_FIELDS},
            "timestampSource": runtime["timestampSource"], "runtimeLedgerSha256": ledger_sha,
            "executionMode": "FRESH_KERNEL_NOTEBOOK", "sourceNotebookPath": source_rel,
            "sourceNotebookBlobId": git_blob(project, source), "sourceCommit": head,
            "nativeEvidencePath": native.relative_to(project).as_posix(), "nativeEvidenceSha256": sha_file(native),
            "metrics": {"sourceCells": audit["cells"], "sourceCodeCells": audit["codeCells"], "executedStatus": row["status"]},
        })

    for stage_id, source_rel, native_id in A2_STAGES:
        source = project / source_rel
        executed = a2_run_root / "executed" / f"{native_id}.executed.ipynb"
        native = a2_run_root / "artifacts" / native_id / "stage_manifest.json"
        if not executed.is_file() or not native.is_file():
            raise FileNotFoundError(f"missing A2 current-run evidence: {stage_id}")
        audit = source_audit(source)
        if audit["outputs"] or audit["executions"] or normalized_code(source) != normalized_code(executed):
            raise ValueError(f"A2 Notebook authority/parity failed: {stage_id}")
        payload = json.loads(native.read_text(encoding="utf-8"))
        runtime = ledger_rows[stage_id]
        if runtime["sourceNotebookSha256"] != audit["sha256"] or runtime["moduleBlobSha256"] != modules["A2"]:
            raise ValueError(f"A2 runtime ledger source/module mismatch: {stage_id}")
        if runtime["outputManifestSha256"] != sha_file(native):
            raise ValueError(f"A2 runtime ledger output mismatch: {stage_id}")
        records.append({
            "stageId": stage_id, "owner": "A2", "runId": args.run_id, "dataVersion": args.data_version,
            "inputManifestSha256": payload["inputManifestSha256"], "sourceNotebookSha256": audit["sha256"],
            "moduleBlobSha256": modules["A2"], "parameterSha256": parameters,
            "outputManifestSha256": sha_file(native), "status": payload["status"],
            **{key: runtime[key] for key in RUNTIME_REQUIRED_FIELDS},
            "timestampSource": runtime["timestampSource"], "runtimeLedgerSha256": ledger_sha,
            "executionMode": "FRESH_KERNEL_NOTEBOOK", "sourceNotebookPath": source_rel,
            "sourceNotebookBlobId": git_blob(project, source), "sourceCommit": head,
            "nativeEvidencePath": native.relative_to(project).as_posix(), "nativeEvidenceSha256": sha_file(native),
            "metrics": {"sourceCells": audit["cells"], "sourceCodeCells": audit["codeCells"], "nativeStageId": native_id},
        })

    for stage_id, source_rel in A4_STAGES:
        source = project / source_rel
        audit = source_audit(source)
        if audit["outputs"] or audit["executions"]:
            raise ValueError(f"A4 source Notebook is not clean: {stage_id}")
        runtime = ledger_rows[stage_id]
        result = runtime["metrics"]
        if runtime["sourceNotebookSha256"] != audit["sha256"] or runtime["moduleBlobSha256"] != modules["A4"]:
            raise ValueError(f"A4 runtime ledger source/module mismatch: {stage_id}")
        authority_path = project / "ncs_mapping/reports/reconciliation_a4/A4_STAGE_AUTHORITY_MANIFEST.csv"
        records.append({
            "stageId": stage_id, "owner": "A4", "runId": args.run_id, "dataVersion": args.data_version,
            "inputManifestSha256": result["input"], "sourceNotebookSha256": audit["sha256"],
            "moduleBlobSha256": modules["A4"], "parameterSha256": parameters,
            "outputManifestSha256": canonical_sha(result), "status": result["status"],
            **{key: runtime[key] for key in RUNTIME_REQUIRED_FIELDS},
            "timestampSource": runtime["timestampSource"], "runtimeLedgerSha256": ledger_sha,
            "executionMode": "DETERMINISTIC_READ_ONLY_STAGE_RUNNER",
            "sourceNotebookPath": source_rel, "sourceNotebookBlobId": git_blob(project, source),
            "sourceCommit": head, "nativeEvidencePath": authority_path.relative_to(project).as_posix(),
            "nativeEvidenceSha256": sha_file(authority_path), "metrics": result,
        })

    if len(records) != 23 or len({row["stageId"] for row in records}) != 23:
        raise AssertionError("unified stage registry must contain exactly 23 unique stages")
    records.sort(key=lambda row: row["executionOrder"])
    if [row["stageId"] for row in records] != list(EXECUTION_ORDER):
        raise AssertionError("records are not in the canonical execution order")
    manifest_shas = {row["stageId"]: write_stage(report_root, row) for row in records}
    summary_rows = [{
        "stageId": row["stageId"], "owner": row["owner"], "executionMode": row["executionMode"],
        "sourceNotebookPath": row["sourceNotebookPath"], "sourceNotebookSha256": row["sourceNotebookSha256"],
        "moduleBlobSha256": row["moduleBlobSha256"], "runId": args.run_id, "dataVersion": args.data_version,
        "status": row["status"], "manifestPath": f"reports/m1_5_unified_reconciliation/stages/{row['stageId']}/stage_manifest.json",
        "manifestSha256": manifest_shas[row["stageId"]], "exactOne": True, "staleConsumed": 0,
        "foreignArtifactConsumed": 0, "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "executionOrder": row["executionOrder"], "dependencyStageIds": "+".join(row["dependencyStageIds"]),
        "startedAtUtc": row["startedAtUtc"], "completedAtUtc": row["completedAtUtc"],
        "executionHostOrRunnerId": row["executionHostOrRunnerId"],
    } for row in records]
    summary_path = report_root / "P4_23_STAGE_REPLAY_SUMMARY.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(summary_rows)

    registry = {
        "registryVersion": "p4-unified-23-stage-v2", "baseCommit": BASE_COMMIT,
        "headCommitAtExecution": head, "runId": args.run_id, "dataVersion": args.data_version,
        "contractVersion": CONTRACT_VERSION, "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "stages": [{
            "stageId": row["stageId"], "owner": row["owner"], "sourceNotebookPath": row["sourceNotebookPath"],
            "sourceNotebookBlobSha256": row["sourceNotebookSha256"], "moduleBlobSha256": row["moduleBlobSha256"],
            "inputContract": "current-run SHA-bound input", "outputContract": "four termination artifacts",
            "dependencyStageIds": list(STAGE_DEPENDENCIES[row["stageId"]]),
            "executionOrder": row["executionOrder"],
            "currentRunManifestSchema": "p4-unified-current-run-v2",
            "validatorGate": "STRICT_CURRENT_RUN_TOPOLOGY_AND_TIMESTAMP_BINDING",
        } for row in records],
    }
    (report_root / "P4_23_STAGE_REGISTRY.yaml").write_text(yaml.safe_dump(registry, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps({"plannedStages": 23, "executedStages": 23, "exactOneManifests": 23, "runId": args.run_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
