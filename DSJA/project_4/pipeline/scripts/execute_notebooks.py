from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"


def _parameter_override(args: argparse.Namespace) -> str:
    if args.mode == "fixture":
        return "\nRUN_MODE = 'fixture'"
    required = (args.project_root, args.release_root, args.crawl_root, args.output_root)
    if not all(required):
        raise ValueError("observed-dev execution requires project, release, crawl, and output roots")
    return "\n".join(
        [
            "",
            f"PROJECT_ROOT = {str(args.project_root.resolve())!r}",
            f"RELEASE_ROOT = {str(args.release_root.resolve())!r}",
            f"CRAWL_ROOT = {str(args.crawl_root.resolve())!r}",
            f"OUTPUT_ROOT = {str(args.output_root.resolve())!r}",
            f"CONTROL_ROOT = {str(args.control_root.resolve())!r}" if args.control_root else "",
            f"NCS_HANDOFF_PATH = {str(args.ncs_handoff_path.resolve())!r}" if args.ncs_handoff_path else "",
            f"NCS_PROJECT_ROOT = {str(args.ncs_project_root.resolve())!r}" if args.ncs_project_root else "",
        ]
    )


def execute(args: argparse.Namespace) -> list[Path]:
    root = NOTEBOOK_ROOT / "fixture" if args.mode == "fixture" else NOTEBOOK_ROOT
    names = args.notebook or [path.name for path in sorted(root.glob("*.ipynb"))]
    executed: list[Path] = []
    for name in names:
        source_path = root / name
        notebook = nbformat.read(source_path, as_version=4)
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
            target = PIPELINE_ROOT / "runs/executed-notebooks" / f"{source_path.stem}.executed.ipynb"
            target.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(notebook, target)
            executed.append(target)
        else:
            executed.append(source_path)
        print(source_path.relative_to(PIPELINE_ROOT))
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
    parser.add_argument("--save-executed", action="store_true")
    execute(parser.parse_args())


if __name__ == "__main__":
    main()
