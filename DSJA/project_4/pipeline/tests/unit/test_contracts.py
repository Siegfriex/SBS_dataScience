import json

import pytest

from p4.contracts.loader import CrawlRelease, contract_bundle_status, load_crawl_release
from p4.contracts.validators import assert_duckdb_executable_ddl, find_cross_schema_foreign_keys


def test_crawl_release_aliases_and_validation(tmp_path):
    handoff = tmp_path / "HANDOFF.json"
    handoff.write_text(
        json.dumps(
            {
                "releaseId": "REL_1",
                "contractVersion": "2.1.0",
                "manifestPaths": ["manifest.parquet"],
                "coveragePath": "coverage.parquet",
                "checksumPath": "CHECKSUMS.sha256",
                "sourceStart": "2019-01-01",
                "sourceEnd": "2026-08-06",
            }
        ),
        encoding="utf-8",
    )
    release = load_crawl_release(handoff)
    assert isinstance(release, CrawlRelease)
    assert release.release_id == "REL_1"


def test_crawl_release_rejects_missing_fields():
    with pytest.raises(ValueError):
        CrawlRelease.from_dict({"releaseId": "REL_1"})


def test_contract_bundle_status_reports_all_missing(tmp_path):
    status = contract_bundle_status(tmp_path / "missing")
    assert status["ready"] is False
    assert len(status["missingFiles"]) == 5


def test_cross_schema_foreign_keys_are_rejected():
    ddl = "CREATE TABLE core.child(id INT REFERENCES raw.parent(id));"
    assert find_cross_schema_foreign_keys(ddl) == ["raw.parent"]
    with pytest.raises(ValueError, match="CONTRACT_NOT_EXECUTABLE"):
        assert_duckdb_executable_ddl(ddl)
    assert_duckdb_executable_ddl("CREATE TABLE core.child(id INT);")

