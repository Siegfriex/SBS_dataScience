#!/usr/bin/env python3
"""Execute the Master Notebook without modifying its source outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawl.control.notebook_bundle import execute_notebook, resolve_project_root, write_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default="crawl/runs/notebooks/observed-dev/MASTER_20260806_01")
    args = parser.parse_args()
    root = resolve_project_root(Path.cwd())
    run_root = (root / args.run_root).resolve()
    result = execute_notebook(
        root / "crawl/notebooks/P4_Notebook_First_Master.ipynb",
        root,
        run_root,
        timeout=1800,
    )
    result.update({"agentId": "P4-A3-CONTROL", "stageId": "A3-MASTER"})
    write_csv(run_root / "NOTEBOOK_EXECUTION_RESULTS.csv", [result])
    print(result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
