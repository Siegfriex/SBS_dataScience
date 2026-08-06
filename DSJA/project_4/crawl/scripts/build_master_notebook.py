#!/usr/bin/env python3
"""Render the deterministic P4 Notebook-First master orchestration notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat as nbf


def markdown(cell_id: str, source: str):
    cell = nbf.v4.new_markdown_cell(source.strip() + "\n")
    cell["id"] = cell_id
    return cell


def code(cell_id: str, source: str, tags: list[str] | None = None):
    cell = nbf.v4.new_code_cell(source.strip() + "\n")
    cell["id"] = cell_id
    cell["metadata"] = {"tags": tags or []}
    cell["execution_count"] = None
    cell["outputs"] = []
    return cell


def build() -> nbf.NotebookNode:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
        "p4": {"contractVersion": "2.1.2", "stageId": "A3-MASTER", "sourceOutputCount": 0},
    }
    notebook["cells"] = [
        markdown("a3-master-title", """
# P4 Notebook-First Master — observed-development

| 항목 | 내용 |
|---|---|
| 목적 | 23개 Agent Notebook의 source gate, 실행 순서, stage manifest, 최종 bundle QA를 통합한다. |
| 담당 Agent | `P4-A3-CONTROL` |
| Stage ID | `A3-MASTER` |
| 입력 | stage registry, Agent 1·2·4 source Notebook, observed input과 NCS handoff |
| 처리 | 구조감사 → architecture/index → fresh-kernel child 실행 → manifest 수집 → bundle gate |
| 출력 | executed Notebook, 실행결과 CSV, 4개 종료 artifact, 최종 보고 입력 |
| 선행 Gate | `CRAWL_OBSERVED_INPUT_READY`, `OBSERVED_PARSE_READY`, `NCS_MAPPING_DEV_READY` |
| 후속 활용 | 사용자 검수용 Notebook bundle; empirical analysis나 production 승격에는 사용하지 않는다. |
"""),
        code("a3-master-parameters", """
RUN_MODE = "observed-dev"
AGENT_ID = "P4-A3-CONTROL"
STAGE_ID = "A3-MASTER"
CONTRACT_VERSION = "2.1.2"
SCHEMA_VERSION = "notebook-bundle-v1"
DATA_VERSION = "observed-dev-20260806.1"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
AS_OF_DATE = "2026-08-06"
INPUT_MANIFEST_PATH = "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml"
OUTPUT_ROOT = "crawl/runs/notebooks/observed-dev/MASTER_20260806_01/master_stage"
RANDOM_SEED = 20260806
FAIL_ON_GATE = True
EMPIRICAL_ANALYSIS_ALLOWED = False
""", ["parameters"]),
        code("a3-master-environment", """
import platform
import sys
from pathlib import Path

from crawl.control.notebook_bundle import (
    NOTEBOOKS,
    audit_source_bundle,
    collect_stage_manifests,
    bind_current_run_manifests,
    dependency_order_audit,
    execute_notebook_plan,
    git_head,
    load_stage_registry,
    notebook_plan,
    repository_architecture,
    resolve_project_root,
    sha256_file,
    source_blob_provenance,
    source_executed_parity_rows,
    write_csv,
    write_master_stage_artifacts,
)

PROJECT_ROOT = resolve_project_root(Path.cwd())
CONTRACT_PATH = PROJECT_ROOT / "crawl/control/NOTEBOOK_EXECUTION_CONTRACT.md"
environment = {
    "repoRoot": ".",
    "gitHead": git_head(PROJECT_ROOT),
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "contractPath": str(CONTRACT_PATH.relative_to(PROJECT_ROOT)),
    "contractSha256": sha256_file(CONTRACT_PATH),
}
environment
"""),
        code("a3-master-input-audit", """
registry = load_stage_registry(PROJECT_ROOT)
source_audit = audit_source_bundle(PROJECT_ROOT)
source_blob_rows = source_blob_provenance(PROJECT_ROOT)
invalid_sources = [row for row in source_audit if not row.get("valid")]
invalid_blobs = [row for row in source_blob_rows if not row["tracked"] or not row["workingTreeMatchesGitBlob"]]
input_audit = {
    "registryVersion": registry["registryVersion"],
    "contractVersion": registry["contractVersion"],
    "sourceNotebookCount": len(source_audit),
    "validSourceNotebookCount": len(source_audit) - len(invalid_sources),
    "crawlNotebookBlobCoverage": f"{len(source_blob_rows) - len(invalid_blobs)}/{len(source_blob_rows)}",
    "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
    "empiricalAnalysisAllowed": EMPIRICAL_ANALYSIS_ALLOWED,
    "upstreamGate": "OBSERVED_DEV_CSV_READY",
}
if FAIL_ON_GATE and (invalid_sources or invalid_blobs):
    raise RuntimeError(f"Notebook source/blob gate failed: sources={invalid_sources}, blobs={invalid_blobs}")
input_audit
"""),
        markdown("a3-master-index", """
## 1부 — Source·수집·전처리·NCS

Agent 1은 offline/dry-run/replay 수집 단계를, Agent 2는 observed 전처리 단계를,
Agent 4는 lexical baseline 단계를 담당한다.

## 2부 — 통합 실행·검수

Master는 stage registry 순서로 source Notebook을 fresh kernel에서 실행하고,
실행본과 stage artifact를 source와 분리해 보존한다.
"""),
        code("a3-master-architecture", """
architecture_rows = repository_architecture(PROJECT_ROOT)
topological_plan = notebook_plan(PROJECT_ROOT)
dependency_rows = dependency_order_audit(PROJECT_ROOT, topological_plan)
architecture_summary = {
    "agent1": sum(row["agentId"] == "P4-A1-SOURCE" for row in architecture_rows),
    "agent2": sum(row["agentId"] == "P4-A2-PIPELINE" for row in architecture_rows),
    "agent4": sum(row["agentId"] == "P4-A4-NCS" for row in architecture_rows),
    "master": sum(row["agentId"] == "P4-A3-CONTROL" for row in architecture_rows),
    "total": len(architecture_rows),
}
architecture_summary, architecture_rows
"""),
        code("a3-master-stage-registry", """
registry_rows = [
    {
        "stageId": stage["stageId"],
        "ownerAgent": stage["ownerAgent"],
        "notebookPath": stage["notebookPath"],
        "requiredGate": stage["requiredGate"],
        "producedGate": stage["producedGate"],
    }
    for stage in registry["stages"]
]
registry_rows
"""),
        code("a3-master-execute", """
MASTER_OUTPUT = (PROJECT_ROOT / OUTPUT_ROOT).resolve() if not Path(OUTPUT_ROOT).is_absolute() else Path(OUTPUT_ROOT)
CHILD_RUN_ROOT = MASTER_OUTPUT.parent / "children"
execution_results = execute_notebook_plan(
    PROJECT_ROOT,
    CHILD_RUN_ROOT,
    include_master=False,
    fail_fast=FAIL_ON_GATE,
)
CURRENT_RUN_ID = CHILD_RUN_ROOT.relative_to(PROJECT_ROOT / "crawl/runs").as_posix()
failed = [row for row in execution_results if row["status"] != "PASS"]
if FAIL_ON_GATE and failed:
    raise RuntimeError(f"Child Notebook execution failed: {failed[0]}")
execution_results
"""),
        code("a3-master-manifests", """
stage_manifests = bind_current_run_manifests(
    PROJECT_ROOT,
    CHILD_RUN_ROOT,
    execution_results,
    run_id=CURRENT_RUN_ID,
)
parity_rows = source_executed_parity_rows(PROJECT_ROOT, execution_results)
write_csv(MASTER_OUTPUT / "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv", source_blob_rows)
write_csv(MASTER_OUTPUT / "CRAWL_STAGE_DEPENDENCY_GRAPH.csv", dependency_rows)
write_csv(MASTER_OUTPUT / "CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv", stage_manifests)
write_csv(MASTER_OUTPUT / "NOTEBOOK_SOURCE_EXECUTED_PARITY.csv", parity_rows)
manifest_summary = {
    "collected": len(stage_manifests),
    "succeeded": sum(row.get("status") == "SUCCEEDED" for row in stage_manifests),
    "notEvaluated": sum(row.get("status") == "NOT_EVALUATED" for row in stage_manifests),
    "failed": sum(row.get("status") in {"FAILED", "INVALID"} for row in stage_manifests),
    "uniqueCurrentRunStages": len({row["stageId"] for row in stage_manifests}),
    "sourceExecutedParity": f"{sum(row['executedCodeParity'] for row in parity_rows)}/{len(parity_rows)}",
}
manifest_summary
"""),
        code("a3-master-final-qa", """
final_export = PROJECT_ROOT / "crawl/data/exports/observed-dev/OBSERVED_DEV_20260806_01"
required_review_files = [
    "posting_normalized.csv", "posting_tracks.csv", "posting_sections.csv",
    "requirement_facts.csv", "career_access_labels.csv", "posting_ncs_candidates.csv",
    "preprocessed_posting_tracks.csv", "data_quality_summary.csv", "CHECKSUMS.sha256",
]
bundle_qa = {
    "requiredReviewFiles": len(required_review_files),
    "presentReviewFiles": sum((final_export / name).is_file() for name in required_review_files),
    "childExecutionPass": sum(row["status"] == "PASS" for row in execution_results),
    "childExecutionTotal": len(execution_results),
    "sourceOutputCount": sum(int(row.get("sourceOutputs", 0)) for row in source_audit),
    "empiricalAnalysisAllowed": False,
    "promotionAllowed": False,
}
if FAIL_ON_GATE and (
    bundle_qa["presentReviewFiles"] != bundle_qa["requiredReviewFiles"]
    or bundle_qa["childExecutionPass"] != bundle_qa["childExecutionTotal"]
    or bundle_qa["sourceOutputCount"] != 0
):
    raise RuntimeError(f"Master bundle QA failed: {bundle_qa}")
bundle_qa
"""),
        code("a3-master-terminate", """
termination = write_master_stage_artifacts(
    MASTER_OUTPUT,
    PROJECT_ROOT,
    source_audit,
    execution_results,
    stage_manifests,
)
{
    "status": "NOTEBOOK_EXECUTION_READY_OBSERVED_DEV",
    "terminationArtifacts": termination,
    "reviewCsv": str((final_export / "preprocessed_posting_tracks.csv").relative_to(PROJECT_ROOT)),
    "forbidden": ["CRAWL_RELEASE_READY", "DATA_READY_RQ1_RQ2A", "DATA_READY_RQ2B", "ANALYSIS_READY"],
}
"""),
    ]
    return notebook


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="crawl/notebooks/P4_Notebook_First_Master.ipynb")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = Path(args.output)
    rendered = build()
    nbf.validate(rendered)
    if args.check:
        if not destination.is_file():
            raise SystemExit(f"missing: {destination}")
        current = nbf.read(destination, as_version=4)
        if current != rendered:
            raise SystemExit(f"render drift: {destination}")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(rendered, destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
