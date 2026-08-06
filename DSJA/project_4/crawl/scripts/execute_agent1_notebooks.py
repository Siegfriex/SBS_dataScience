"""Execute each Agent 1 source notebook in a fresh kernel and save copies."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
SOURCE_ROOT = CRAWL_ROOT / "notebooks"
RUN_ROOT = CRAWL_ROOT / "runs" / "notebooks" / "observed-dev" / "AGENT1_20260806_01"
EXECUTED_ROOT = RUN_ROOT / "executed"
NAMES = [
    "00RecoverSourceState", "01CollectLinkareerIndex", "02CollectPostingDetail",
    "03CollectPostingAssets", "04BuildCrawlRelease",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(path: Path) -> tuple[int, int]:
    notebook = nbformat.read(path, 4)
    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells or "parameters" not in code_cells[0].metadata.get("tags", []):
        raise ValueError(f"first code cell is not tagged parameters: {path}")
    ids = [cell.id for cell in notebook.cells]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate cell IDs: {path}")
    outputs = 0
    for cell in code_cells:
        ast.parse(cell.source)
        outputs += len(cell.get("outputs", []))
    if outputs:
        raise ValueError(f"source notebook contains outputs: {path}")
    return len(notebook.cells), len(code_cells)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if RUN_ROOT.exists():
        raise RuntimeError(f"run root already exists; refusing overwrite: {RUN_ROOT}")
    EXECUTED_ROOT.mkdir(parents=True)
    results = []
    for name in NAMES:
        source = SOURCE_ROOT / f"{name}.ipynb"
        cell_count, code_count = validate_source(source)
        notebook = nbformat.read(source, 4)
        started = time.monotonic()
        client = NotebookClient(
            notebook, timeout=args.timeout, kernel_name="python3",
            resources={"metadata": {"path": str(PROJECT_ROOT)}},
        )
        executed = client.execute()
        elapsed = round(time.monotonic() - started, 3)
        destination = EXECUTED_ROOT / source.name
        nbformat.write(executed, destination)
        results.append({
            "notebook": f"crawl/notebooks/{source.name}", "status": "PASS",
            "cells": cell_count, "codeCells": code_count,
            "sourceOutputCount": 0, "executedOutputCount": sum(len(cell.get("outputs", [])) for cell in executed.cells if cell.cell_type == "code"),
            "elapsedSeconds": elapsed, "sourceSha256": sha256(source), "executedSha256": sha256(destination),
            "executedPath": destination.relative_to(PROJECT_ROOT).as_posix(),
        })
    with (RUN_ROOT / "NOTEBOOK_EXECUTION_RESULTS.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
