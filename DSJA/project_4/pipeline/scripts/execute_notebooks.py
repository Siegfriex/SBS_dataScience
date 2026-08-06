from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient
import yaml

from hashlib import sha256


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"
SPEC_PATH = PIPELINE_ROOT / "notebook_specs/observed_dev.yaml"


def _parameter_override(args: argparse.Namespace) -> str:
    if args.mode == "fixture":
        return "\nRUN_MODE = 'fixture'"
    required = (args.project_root, args.release_root, args.output_root)
    if not all(required):
        raise ValueError("observed-dev execution requires project, release, and output roots")
    return "\n".join(
        [
            "",
            f"PROJECT_ROOT = {str(args.project_root.resolve())!r}",
            f"RELEASE_ROOT = {str(args.release_root.resolve())!r}",
            f"OUTPUT_ROOT = {str(args.output_root.resolve())!r}",
        ]
    )


def execute(args: argparse.Namespace) -> list[Path]:
    root = NOTEBOOK_ROOT / "fixture" if args.mode == "fixture" else NOTEBOOK_ROOT
    if args.mode == "observed-dev":
        spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
        registered = [f"{stage['id']}.ipynb" for stage in spec["stages"]]
    else:
        registered = [path.name for path in sorted(root.glob("*.ipynb"))]
    names = args.notebook or registered
    run_root = PIPELINE_ROOT / "runs/notebooks/observed-dev" / args.run_id
    if args.mode == "observed-dev":
        run_root.mkdir(parents=True, exist_ok=True)
        os.environ["P4_NOTEBOOK_RUN_ROOT"] = str(run_root.resolve())
        if args.crawl_root:
            os.environ["P4_CRAWL_ROOT"] = str(args.crawl_root.resolve())
        if args.control_root:
            os.environ["P4_CONTROL_ROOT"] = str(args.control_root.resolve())
        if args.ncs_project_root:
            os.environ["P4_NCS_PROJECT_ROOT"] = str(args.ncs_project_root.resolve())
        if args.ncs_handoff_path:
            os.environ["P4_NCS_HANDOFF_PATH"] = str(args.ncs_handoff_path.resolve())
    executed: list[Path] = []
    for name in names:
        source_path = root / name
        notebook = nbformat.read(source_path, as_version=4)
        source_parameter_cell = notebook.cells[0].source
        source_output_count = sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code")
        if source_output_count:
            raise ValueError(f"source notebook contains stored outputs: {source_path}")
        notebook.cells[0].source += _parameter_override(args)
        client = NotebookClient(
            notebook,
            timeout=args.timeout,
            kernel_name=args.kernel,
            resources={"metadata": {"path": str(root)}},
        )
        client.execute()
        if args.save_executed:
            # Runtime paths are injected only for execution.  Persist the clean,
            # repository-portable parameter cell with the captured outputs.
            notebook.cells[0].source = source_parameter_cell
            target = run_root / "executed" / f"{source_path.stem}.executed.ipynb"
            target.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(notebook, target)
            executed.append(target)
        else:
            executed.append(source_path)
        print(source_path.relative_to(PIPELINE_ROOT))
    if args.mode == "observed-dev" and args.save_executed:
        records = [
            {
                "path": str(path.relative_to(PIPELINE_ROOT)),
                "sha256": sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
            for path in executed
        ]
        (run_root / "executed_notebooks_manifest.json").write_text(
            json.dumps(
                {
                    "runId": args.run_id,
                    "runMode": "observed-dev",
                    "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
                    "empiricalAnalysisAllowed": False,
                    "promotionAllowed": False,
                    "notebookCount": len(records),
                    "notebooks": records,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        checksum_targets = sorted(
            path for path in run_root.rglob("*")
            if path.is_file() and path.name != "CHECKSUMS.sha256"
        )
        (run_root / "CHECKSUMS.sha256").write_text(
            "".join(
                f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(run_root)}\n"
                for path in checksum_targets
            ),
            encoding="utf-8",
        )
    return executed


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute source notebooks in memory without overwriting them.")
    parser.add_argument("--mode", choices=["fixture", "observed-dev"], required=True)
    parser.add_argument("--notebook", action="append")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--crawl-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--control-root", type=Path)
    parser.add_argument("--ncs-handoff-path", type=Path)
    parser.add_argument("--ncs-project-root", type=Path)
    parser.add_argument("--kernel", default="python3")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--run-id", default="AGENT2_20260806_01")
    parser.add_argument("--save-executed", action="store_true")
    execute(parser.parse_args())


if __name__ == "__main__":
    main()
