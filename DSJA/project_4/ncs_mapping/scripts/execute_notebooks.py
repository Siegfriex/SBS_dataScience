"""Execute all source notebooks in fresh kernels without saving outputs."""
from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = [
    "00NcsSourceAudit.ipynb",
    "01BuildCoreAiItCodeSet.ipynb",
    "02BuildNcsRetrievalIndex.ipynb",
    "03MapObservedDuties.ipynb",
    "04ExportNcsMappingCsv.ipynb",
]


def main() -> int:
    for name in NOTEBOOKS:
        notebook = nbformat.read(ROOT / "notebooks" / name, as_version=4)
        NotebookClient(
            notebook,
            timeout=180,
            kernel_name="python3",
            resources={"metadata": {"path": str(ROOT)}},
        ).execute(cwd=str(ROOT))
        print(f"PASS {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
