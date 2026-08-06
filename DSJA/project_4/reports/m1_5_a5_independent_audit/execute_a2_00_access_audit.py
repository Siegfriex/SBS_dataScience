#!/usr/bin/env python3
"""Execute A2-00 in a fresh kernel while the A5 audit hook records reads."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--kernel", default="project_4_sbs_venv")
    args = parser.parse_args()
    project = args.project_root.resolve()
    report = args.report_root.resolve()
    source = project / "pipeline/notebooks/00ContractAndInputAudit.ipynb"
    release = project / "crawl/observed_inputs/OBSERVED_INPUT_20260806_01"
    runtime = report / "runtime/a2_00"
    runtime.mkdir(parents=True, exist_ok=True)
    access_log = report / "P4_A5_A2_00_FILE_ACCESS.jsonl"
    if access_log.exists():
        access_log.unlink()

    os.environ.update({
        "P4_A5_PROJECT_ROOT": str(project),
        "P4_A5_ACCESS_LOG": str(access_log),
        "P4_A5_AUDIT_HOOK_PATH": str(report / "audit_hook/sitecustomize.py"),
        "P4_NOTEBOOK_RUN_ROOT": str(runtime / "notebook_run"),
        "P4_OBSERVED_DATABASE_PATH": str(runtime / "warehouse/p4.observed-dev.duckdb"),
        "P4_CRAWL_ROOT": str(project / "crawl"),
        "P4_CONTROL_ROOT": str(project / "crawl/control"),
        "P4_NCS_PROJECT_ROOT": str(project),
    })
    hook = report / "audit_hook"
    os.environ["PYTHONPATH"] = os.pathsep.join([
        str(hook), str(project / "pipeline/src"), str(project / "ncs_mapping/src"),
        os.environ.get("PYTHONPATH", ""),
    ])
    notebook = nbformat.read(source, as_version=4)
    notebook.cells.insert(
        1,
        nbformat.v4.new_code_cell(
            "import os, runpy\n"
            "runpy.run_path(os.environ['P4_A5_AUDIT_HOOK_PATH'], run_name='p4_a5_audit_hook')"
        ),
    )
    parameter_index = next(
        index for index, cell in enumerate(notebook.cells)
        if cell.cell_type == "code" and "parameters" in cell.metadata.get("tags", [])
    )
    notebook.cells[parameter_index].source += "\n".join([
        "", f"PROJECT_ROOT = {str(project)!r}", f"RELEASE_ROOT = {str(release)!r}",
        f"OUTPUT_ROOT = {str(runtime / 'output')!r}",
    ])
    client = NotebookClient(
        notebook, timeout=180, kernel_name=args.kernel,
        resources={"metadata": {"path": str(project / "pipeline/notebooks")}},
    )
    client.execute()
    artifact = runtime / "notebook_run/artifacts/00ContractAndInputAudit/stage_manifest.json"
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    print(json.dumps({
        "status": payload["status"],
        "inputManifestSha256": payload["inputManifestSha256"],
        "stageManifest": artifact.relative_to(report).as_posix(),
        "accessLog": access_log.relative_to(report).as_posix(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
