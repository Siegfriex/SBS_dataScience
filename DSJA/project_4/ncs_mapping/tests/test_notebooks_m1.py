import ast
import json
from pathlib import Path

import nbformat

NCS_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    "00NcsSourceAudit.ipynb",
    "01BuildCoreAiItCodeSet.ipynb",
    "02BuildNcsRetrievalIndex.ipynb",
    "03MapObservedDuties.ipynb",
    "04ExportNcsMappingCsv.ipynb",
]


def test_notebooks_are_thin_clean_and_parseable():
    for name in EXPECTED:
        notebook = nbformat.read(NCS_ROOT / "notebooks" / name, as_version=4)
        nbformat.validate(notebook)
        assert notebook.cells[0].cell_type == "code"
        assert "parameters" in notebook.cells[0].metadata.get("tags", [])
        assert 'RUN_MODE = "observed-dev"' in notebook.cells[0].source
        assert 'DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"' in notebook.cells[0].source
        assert "EMPIRICAL_ANALYSIS_ALLOWED = False" in notebook.cells[0].source
        assert "PROMOTION_ALLOWED = False" in notebook.cells[0].source
        assert all(cell.get("execution_count") is None for cell in notebook.cells if cell.cell_type == "code")
        assert all(not cell.get("outputs") for cell in notebook.cells if cell.cell_type == "code")
        for cell in notebook.cells:
            if cell.cell_type == "code":
                ast.parse(cell.source)


def test_notebook_sources_do_not_embed_dense_or_absolute_temp_path():
    for name in EXPECTED:
        raw = (NCS_ROOT / "notebooks" / name).read_text(encoding="utf-8")
        assert "dense_rerank(" not in raw
        assert "/tmp/p4-agent2-observed" not in raw
