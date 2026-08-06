from __future__ import annotations

from pathlib import Path

from crawl.control.notebook_bundle import source_blob_provenance


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_all_six_crawl_notebooks_match_tracked_git_blobs() -> None:
    rows = source_blob_provenance(PROJECT_ROOT)
    assert len(rows) == 6
    assert all(row["tracked"] for row in rows)
    assert all(row["gitBlobId"] for row in rows)
    assert all(row["sourceFileSha256"] for row in rows)
    assert all(row["workingTreeMatchesGitBlob"] for row in rows)
