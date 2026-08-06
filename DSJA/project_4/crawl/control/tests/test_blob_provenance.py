from __future__ import annotations

from pathlib import Path

import nbformat

from crawl.control.notebook_bundle import _normalized_code_cells, source_blob_provenance


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_all_six_crawl_notebooks_match_tracked_git_blobs() -> None:
    rows = source_blob_provenance(PROJECT_ROOT)
    assert len(rows) == 6
    assert all(row["tracked"] for row in rows)
    assert all(row["gitBlobId"] for row in rows)
    assert all(row["sourceFileSha256"] for row in rows)
    assert all(row["workingTreeMatchesGitBlob"] for row in rows)


def test_parameter_injection_is_the_only_allowed_code_difference(tmp_path) -> None:
    source = tmp_path / "source.ipynb"
    executed = tmp_path / "executed.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("VALUE = 1", id="cell-1")])
    nbformat.write(notebook, source)
    notebook.cells[0].source += (
        "\n# Injected into the executed copy by crawl.control.notebook_bundle\n"
        "OUTPUT_ROOT = 'crawl/runs/test'"
    )
    nbformat.write(notebook, executed)
    assert _normalized_code_cells(source, executed=False) == _normalized_code_cells(executed, executed=True)
