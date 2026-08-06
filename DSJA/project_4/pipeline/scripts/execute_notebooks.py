from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = PIPELINE_ROOT / "notebooks"


def execute_all() -> list[Path]:
    executed: list[Path] = []
    for path in sorted(NOTEBOOK_ROOT.glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        client = NotebookClient(
            notebook,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(NOTEBOOK_ROOT)}},
        )
        client.execute()
        nbformat.write(notebook, path)
        executed.append(path)
        print(path)
    return executed


if __name__ == "__main__":
    execute_all()

