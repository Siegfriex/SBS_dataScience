#!/usr/bin/env python3
"""Validate all 24 source notebooks and materialize the final audit tables."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

import nbformat
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawl.control.notebook_bundle import (
    NOTEBOOKS,
    audit_source_bundle,
    resolve_project_root,
    sha256_file,
    write_csv,
)


REPORT_FILES = (
    "NOTEBOOK_BUILD_FINAL_REPORT.md",
    "NOTEBOOK_BUILD_FINAL_REPORT.json",
    "NOTEBOOK_FILE_INVENTORY.csv",
    "NOTEBOOK_CELL_INVENTORY.csv",
    "NOTEBOOK_EXECUTION_RESULTS.csv",
    "NOTEBOOK_MODULE_CALL_MATRIX.csv",
    "NOTEBOOK_OUTPUT_ARTIFACTS.csv",
    "NOTEBOOK_GATE_RESULTS.csv",
)


def execution_rows(root: Path) -> list[dict[str, Any]]:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(root.glob("**/runs/notebooks/observed-dev/**/NOTEBOOK_EXECUTION_RESULTS.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        for row in frame.to_dict(orient="records"):
            row["resultFile"] = path.relative_to(root).as_posix()
            notebook = str(row.get("notebook", ""))
            candidates.setdefault(notebook, []).append(row)

    expected = {relative for _, _, relative in NOTEBOOKS}
    rows: list[dict[str, Any]] = []
    for notebook in sorted(expected):
        matches = candidates.get(notebook, [])
        if not matches:
            continue
        # The integrated Master run is the bundle authority. Agent-local runs
        # remain preserved as evidence but must not duplicate final report rows.
        matches.sort(
            key=lambda row: (
                "MASTER_20260806_01" in str(row.get("resultFile", "")),
                row.get("status") == "PASS",
            ),
            reverse=True,
        )
        rows.append(matches[0])
    return rows


def cell_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    lookup = {relative: (agent, stage) for agent, stage, relative in NOTEBOOKS}
    for relative, (agent, stage) in lookup.items():
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            continue
        notebook = nbformat.read(path, as_version=4)
        for index, cell in enumerate(notebook.cells):
            outputs = len(cell.get("outputs", [])) if cell.cell_type == "code" else 0
            syntax = "NOT_APPLICABLE"
            if cell.cell_type == "code":
                try:
                    ast.parse(cell.source)
                    syntax = "PASS"
                except SyntaxError:
                    syntax = "FAIL"
            rows.append({
                "agentId": agent,
                "stageId": stage,
                "notebook": relative,
                "cellIndex": index,
                "cellId": cell.get("id", ""),
                "cellType": cell.cell_type,
                "parametersTag": "parameters" in cell.metadata.get("tags", []),
                "sourceLines": len(cell.source.splitlines()),
                "astParse": syntax,
                "sourceOutputs": outputs,
                "executionCount": cell.get("execution_count") if cell.cell_type == "code" else "",
            })
    return rows


def artifact_rows(root: Path) -> list[dict[str, Any]]:
    patterns = (
        "crawl/runs/notebooks/observed-dev/**/*",
        "pipeline/runs/notebooks/observed-dev/**/*",
        "ncs_mapping/runs/notebooks/observed-dev/**/*",
        "crawl/data/exports/observed-dev/OBSERVED_DEV_20260806_01/*",
    )
    rows = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            if path.suffix.lower() not in {".ipynb", ".json", ".csv", ".parquet", ".sha256", ".jsonl"}:
                continue
            rows.append({
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "format": path.suffix.lstrip(".") or path.name,
                "kind": "executed_notebook" if path.suffix == ".ipynb" else "stage_or_data_artifact",
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", default="crawl/reports/m1_notebook_build")
    args = parser.parse_args()
    root = resolve_project_root(Path.cwd())
    report_root = root / args.report_root
    report_root.mkdir(parents=True, exist_ok=True)

    audits = audit_source_bundle(root)
    executions = execution_rows(root)
    execution_by_notebook: dict[str, list[dict[str, Any]]] = {}
    for row in executions:
        execution_by_notebook.setdefault(str(row.get("notebook", "")), []).append(row)
    for row in audits:
        matches = execution_by_notebook.get(row["notebook"], [])
        row["executionResult"] = "PASS" if any(item.get("status") == "PASS" for item in matches) else "NOT_FOUND"
        row["executedCopies"] = len(matches)

    cells = cell_rows(root)
    artifacts = artifact_rows(root)
    module_rows = [{
        "agentId": row["agentId"], "stageId": row["stageId"], "notebook": row["notebook"],
        "projectImports": row.get("projectImports", ""), "moduleCalls": row.get("moduleCalls", ""),
        "actualModuleCall": row.get("actualModuleCall", False),
    } for row in audits]

    final_path = root / "crawl/data/exports/observed-dev/OBSERVED_DEV_20260806_01/preprocessed_posting_tracks.parquet"
    final = pd.read_parquet(final_path) if final_path.is_file() else pd.DataFrame()
    source_ready = len(audits) == 24 and all(row.get("valid") for row in audits)
    execution_ready = len(audits) == 24 and all(row.get("executionResult") == "PASS" for row in audits)
    bundle_ready = source_ready and execution_ready and len(artifacts) > 0
    invariants = bool(
        not final.empty
        and final["dataProvenance"].eq("OBSERVED_DEVELOPMENT_ONLY").all()
        and not final["empiricalAnalysisAllowed"].any()
        and not final["promotionAllowed"].any()
        and final["highDemandScore"].isna().all()
        and "postingEligibleFlag" in final.columns
        and "validPostingFlag" not in final.columns
    )
    gates = [
        {"gateId": "NOTEBOOK_SOURCE_READY", "status": "PASS" if source_ready else "FAIL", "observed": f"{sum(bool(row.get('valid')) for row in audits)}/24", "required": "24/24", "evidence": "NOTEBOOK_FILE_INVENTORY.csv"},
        {"gateId": "PARAMETER_CELL_READY", "status": "PASS" if all(row.get("parameterTag") and row.get("parameterContractValues") and row.get("titleMarkdownFirst") and row.get("titleSpecificationComplete") and row.get("parameterCellIndex") == 1 for row in audits) else "FAIL", "observed": f"{sum(bool(row.get('parameterTag')) and bool(row.get('parameterContractValues')) and bool(row.get('titleMarkdownFirst')) and bool(row.get('titleSpecificationComplete')) and row.get('parameterCellIndex') == 1 for row in audits)}/24", "required": "24/24", "evidence": "NOTEBOOK_CELL_INVENTORY.csv"},
        {"gateId": "ACTUAL_MODULE_CALL_READY", "status": "PASS" if all(row.get("actualModuleCall") for row in audits) else "FAIL", "observed": f"{sum(bool(row.get('actualModuleCall')) for row in audits)}/24", "required": "24/24", "evidence": "NOTEBOOK_MODULE_CALL_MATRIX.csv"},
        {"gateId": "SOURCE_OUTPUT_ZERO", "status": "PASS" if all(int(row.get("sourceOutputs", 0)) == 0 for row in audits) else "FAIL", "observed": str(sum(int(row.get("sourceOutputs", 0)) for row in audits)), "required": "0", "evidence": "NOTEBOOK_FILE_INVENTORY.csv"},
        {"gateId": "NOTEBOOK_EXECUTION_READY_OBSERVED_DEV", "status": "PASS" if execution_ready else "FAIL", "observed": f"{sum(row.get('executionResult') == 'PASS' for row in audits)}/24", "required": "at least 19; bundle target 24/24", "evidence": "NOTEBOOK_EXECUTION_RESULTS.csv"},
        {"gateId": "OBSERVED_PROVENANCE_INVARIANTS", "status": "PASS" if invariants else "FAIL", "observed": str(invariants), "required": "True", "evidence": "preprocessed_posting_tracks.parquet"},
        {"gateId": "NOTEBOOK_BUNDLE_READY", "status": "PASS" if bundle_ready and invariants else "FAIL", "observed": str(bundle_ready and invariants), "required": "True", "evidence": "NOTEBOOK_OUTPUT_ARTIFACTS.csv"},
    ]

    write_csv(report_root / "NOTEBOOK_FILE_INVENTORY.csv", audits)
    write_csv(report_root / "NOTEBOOK_CELL_INVENTORY.csv", cells)
    write_csv(report_root / "NOTEBOOK_EXECUTION_RESULTS.csv", executions)
    write_csv(report_root / "NOTEBOOK_MODULE_CALL_MATRIX.csv", module_rows)
    write_csv(report_root / "NOTEBOOK_OUTPUT_ARTIFACTS.csv", artifacts)
    write_csv(report_root / "NOTEBOOK_GATE_RESULTS.csv", gates)

    status = {
        "generatedAt": "2026-08-06",
        "notebookCount": len(audits),
        "validSourceCount": sum(bool(row.get("valid")) for row in audits),
        "executedNotebookCount": sum(row.get("executionResult") == "PASS" for row in audits),
        "sourceOutputCount": sum(int(row.get("sourceOutputs", 0)) for row in audits),
        "artifactCount": len(artifacts),
        "states": {
            "OBSERVED_DEV_CSV_READY": invariants,
            "NOTEBOOK_SOURCE_READY": source_ready,
            "NOTEBOOK_EXECUTION_READY_OBSERVED_DEV": execution_ready,
            "NOTEBOOK_BUNDLE_READY": bundle_ready and invariants,
        },
        "forbiddenStates": {
            "CRAWL_RELEASE_READY": False,
            "DATA_READY_RQ1_RQ2A": False,
            "DATA_READY_RQ2B": False,
            "ANALYSIS_READY": False,
        },
        "reports": list(REPORT_FILES),
    }
    (report_root / "NOTEBOOK_BUILD_FINAL_REPORT.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table_lines = [
        "| Agent | Notebook | 파일 존재 | Cells | 실제 module call | source outputs | 실행 결과 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in audits:
        table_lines.append(
            f"| {row['agentId']} | `{row['notebook']}` | {str(row['exists']).upper()} | {row.get('cells', 0)} | {str(bool(row.get('actualModuleCall'))).upper()} | {row.get('sourceOutputs', 0)} | {row['executionResult']} |"
        )
    markdown = "\n".join([
        "# P4 Notebook-First final build report", "",
        f"- Notebook source: `{status['validSourceCount']}/24`",
        f"- Executed Notebook: `{status['executedNotebookCount']}/24`",
        f"- Source output count: `{status['sourceOutputCount']}`",
        f"- Output artifacts inventoried: `{status['artifactCount']}`",
        "- Run mode: `observed-dev`", "- Empirical analysis allowed: `false`",
        "- Promotion allowed: `false`", "", *table_lines, "",
        "## State decision", "",
        *[f"- `{name} = {'READY' if ready else 'NOT_READY'}`" for name, ready in status["states"].items()],
        "", "The bundle does not declare production crawl, RQ data, or analysis readiness.", "",
    ])
    (report_root / "NOTEBOOK_BUILD_FINAL_REPORT.md").write_text(markdown, encoding="utf-8")
    checksum_targets = [report_root / name for name in REPORT_FILES]
    (report_root / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if all(status["states"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
