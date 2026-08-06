import hashlib
import json
from pathlib import Path

import pytest
import yaml

from p4.contracts.loader import (
    CANONICAL_SCHEMA_FILENAME,
    CrawlRelease,
    contract_bundle_status,
    latest_contract_bundle,
    load_crawl_release,
    validate_crawl_release,
)
from p4.contracts.validators import audit_contract_bundle, assert_duckdb_executable_ddl, find_cross_schema_foreign_keys


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_crawl_release_aliases_and_validation(tmp_path):
    handoff = tmp_path / "HANDOFF.json"
    handoff.write_text(
        json.dumps(
            {
                "releaseId": "CRAWL_1",
                "contractVersion": "2.1.2",
                "manifestPaths": ["manifest.jsonl"],
                "coveragePath": "coverage.json",
                "checksumPath": "CHECKSUMS.sha256",
                "queryRegistryPath": "query_registry.json",
                "schemaSnapshotPath": "schema.json",
                "sourceStart": "2020-01-01",
                "sourceEnd": "2026-07-31",
            }
        ),
        encoding="utf-8",
    )
    release = load_crawl_release(handoff)
    assert isinstance(release, CrawlRelease)
    assert release.release_id == "CRAWL_1"
    assert release.query_registry_path == "query_registry.json"


def test_crawl_release_rejects_missing_fields_and_recon():
    with pytest.raises(ValueError, match="query_registry_path"):
        CrawlRelease.from_dict(
            {
                "release_id": "CRAWL_1",
                "contract_version": "2.1.2",
                "manifest_paths": ["m.jsonl"],
                "coverage_path": "c.json",
                "checksum_path": "s.sha256",
            }
        )
    with pytest.raises(ValueError, match="RECON"):
        CrawlRelease.from_dict(
            {
                "release_id": "RECON_1",
                "contract_version": "2.1.2",
                "manifest_paths": ["m.jsonl"],
                "coverage_path": "c.json",
                "checksum_path": "s.sha256",
                "query_registry_path": "q.json",
                "schema_snapshot_path": "schema.json",
            }
        )


def test_crawl_release_verifies_checksums_and_raw_lineage(tmp_path):
    release_root = tmp_path / "CRAWL_1"
    release_root.mkdir()
    files = {
        "manifest.jsonl": json.dumps(
            {"sourceUrl": "https://fixture.invalid/1", "rawPath": "raw/1.html", "rawSha256": "a" * 64}
        )
        + "\n",
        "coverage.json": "{}\n",
        "query_registry.json": "{}\n",
        "schema.json": "{}\n",
    }
    for name, content in files.items():
        (release_root / name).write_text(content, encoding="utf-8")
    checksums = "".join(f"{_sha(release_root / name)}  {name}\n" for name in files)
    (release_root / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
    (release_root / "HANDOFF.json").write_text(
        json.dumps(
            {
                "release_id": "CRAWL_1",
                "contract_version": "2.1.2",
                "manifest_paths": ["manifest.jsonl"],
                "coverage_path": "coverage.json",
                "checksum_path": "CHECKSUMS.sha256",
                "query_registry_path": "query_registry.json",
                "schema_snapshot_path": "schema.json",
            }
        ),
        encoding="utf-8",
    )
    audit = validate_crawl_release(release_root / "HANDOFF.json")
    assert audit["rawLineageVerified"] is True
    assert audit["checksumCount"] == 4


def test_contract_bundle_status_and_latest_are_version_agnostic(tmp_path):
    root = tmp_path / "contracts"
    (root / "P4_CONTRACT_v2.1.1").mkdir(parents=True)
    latest = root / "P4_CONTRACT_v2.1.12"
    latest.mkdir()
    assert latest_contract_bundle(root).contract_version == "2.1.12"
    status = contract_bundle_status(latest)
    assert status["ready"] is False
    assert status["contractVersion"] == "2.1.12"
    assert CANONICAL_SCHEMA_FILENAME in status["missingFiles"]
    assert len(status["missingFiles"]) == 6


def test_contract_audit_verifies_version_schema_manifest_ddl_and_reserved_field(tmp_path):
    root = tmp_path / "P4_CONTRACT_v2.1.2"
    root.mkdir()
    contract = {
        "contractVersion": "2.1.2",
        "duckdbVersion": "1.0.0",
        "requiredTables": ["mart.postingAnalysisMart"],
        "requiredFields": {"mart.postingAnalysisMart": ["trackId", "highDemandScore"]},
        "reservedFields": {"highDemandScore": {"mustBeNull": True}},
        "tables": [
            {
                "name": "mart.postingAnalysisMart",
                "columns": [{"name": "trackId"}, {"name": "highDemandScore"}],
            }
        ],
    }
    (root / "p4_contract.yaml").write_text(yaml.safe_dump(contract), encoding="utf-8")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["contractVersion"],
        "properties": {"contractVersion": {"const": "2.1.2"}},
        "additionalProperties": True,
    }
    (root / CANONICAL_SCHEMA_FILENAME).write_text(json.dumps(schema), encoding="utf-8")
    ddl = "CREATE SCHEMA IF NOT EXISTS mart; CREATE TABLE mart.postingAnalysisMart(trackId VARCHAR, highDemandScore DOUBLE);"
    (root / "warehouse_duckdb.sql").write_text(ddl, encoding="utf-8")
    manifest = {"contractVersion": "2.1.2", "ddlSha256": _sha(root / "warehouse_duckdb.sql"), "duckdbVersion": "1.0.0"}
    (root / "CONTRACT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "AGENT3_TO_AGENT2_HANDOFF.json").write_text(json.dumps({"contractVersion": "2.1.2"}), encoding="utf-8")
    checksum_names = [
        "p4_contract.yaml",
        CANONICAL_SCHEMA_FILENAME,
        "warehouse_duckdb.sql",
        "CONTRACT_MANIFEST.json",
        "AGENT3_TO_AGENT2_HANDOFF.json",
    ]
    (root / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha(root / name)}  {name}\n" for name in checksum_names), encoding="utf-8"
    )
    audit = audit_contract_bundle(root)
    assert audit["passed"] is True
    assert audit["contractVersion"] == "2.1.2"
    assert audit["schemaFilename"] == CANONICAL_SCHEMA_FILENAME


def test_cross_schema_foreign_keys_are_rejected():
    ddl = "CREATE TABLE core.child(id INT REFERENCES raw.parent(id));"
    assert find_cross_schema_foreign_keys(ddl) == ["raw.parent"]
    with pytest.raises(ValueError, match="CONTRACT_NOT_EXECUTABLE"):
        assert_duckdb_executable_ddl(ddl)
    assert_duckdb_executable_ddl("CREATE TABLE core.child(id INT);")

