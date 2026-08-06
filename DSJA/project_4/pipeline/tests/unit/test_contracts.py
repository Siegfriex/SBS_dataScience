import hashlib
import json
from pathlib import Path

import pytest

from p4.contracts.loader import (
    CANONICAL_SCHEMA_FILENAME,
    CrawlRelease,
    contract_bundle_status,
    latest_contract_bundle,
    load_crawl_release,
    assess_crawl_release,
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
    assert len(status["missingFiles"]) == 10


def test_contract_audit_verifies_published_v212_bundle():
    root = Path(__file__).resolve().parents[3] / "shared/contracts/P4_CONTRACT_v2.1.2"
    audit = audit_contract_bundle(root)
    assert audit["passed"] is True
    assert audit["contractVersion"] == "2.1.2"
    assert audit["schemaFilename"] == CANONICAL_SCHEMA_FILENAME
    assert audit["contractSha256"] == "f92380cdfc16967f1e363800cd9a575e44532f18a86b2f28f8c3e2404ed675e9"
    assert audit["ddlSha256"] == "956986874eae5686a20a52721dc303f1913c7391b2ee27da6d582a762f73ad58"
    assert (audit["schemaCount"], audit["tableCount"], audit["viewCount"]) == (5, 26, 6)
    assert audit["ddlStatementCount"] >= 36
    assert audit["crossSchemaForeignKeyCount"] == 0
    assert audit["keyContract"]["algorithm"] == "SHA-256"
    assert audit["metricMetadata"]["metricCount"] == 24
    assert audit["fieldLineageCount"] == 418


def _assessment_release(tmp_path: Path, *, contract_version, status: str, pagination_verified: bool) -> Path:
    root = tmp_path / "CRAWL_TEST"
    root.mkdir()
    files = {
        "manifest.jsonl": json.dumps({"sourceUrl": "https://fixture.invalid/1", "rawPath": "raw/1", "rawSha256": "a" * 64}) + "\n",
        "coverage.csv": "periodMonth,coverageStatus\n2026-01,partial\n",
        "query.yaml": "query: fixture\n",
        "schema.json": "{}\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    handoff = {
        "release_id": "CRAWL_TEST",
        "contract_version": contract_version,
        "manifest_paths": ["manifest.jsonl"],
        "coverage_path": "coverage.csv",
        "checksum_path": "CHECKSUMS.sha256",
        "query_registry_path": "query.yaml",
        "schema_snapshot_path": "schema.json",
        "status": status,
        "pagination_verified": pagination_verified,
    }
    (root / "HANDOFF.json").write_text(json.dumps(handoff), encoding="utf-8")
    checksum_names = [*files, "HANDOFF.json"]
    (root / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha(root / name)}  {name}\n" for name in checksum_names), encoding="utf-8"
    )
    return root / "HANDOFF.json"


def test_partial_release_is_accepted_only_for_source_adapter_conformance(tmp_path):
    result = assess_crawl_release(
        _assessment_release(tmp_path, contract_version=None, status="PARTIALLY_READY", pagination_verified=False)
    )
    assert result["sourceAdapterConformanceStatus"] == "SOURCE_ADAPTER_CONFORMANCE_ACCEPTED"
    assert result["empiricalCorpusStatus"] == "EMPIRICAL_CORPUS_REJECTED"
    assert set(result["empiricalRejectionReasons"]) == {
        "contractVersionMismatchOrMissing",
        "paginationUnverified",
        "releaseStatusNotReady",
    }


def test_full_release_is_accepted_when_contract_and_pagination_are_ready(tmp_path):
    result = assess_crawl_release(
        _assessment_release(tmp_path, contract_version="2.1.2", status="CRAWL_READY", pagination_verified=True)
    )
    assert result["empiricalCorpusStatus"] == "EMPIRICAL_CORPUS_ACCEPTED"


def test_cross_schema_foreign_keys_are_rejected():
    ddl = "CREATE TABLE core.child(id INT REFERENCES raw.parent(id));"
    assert find_cross_schema_foreign_keys(ddl) == ["raw.parent"]
    with pytest.raises(ValueError, match="CONTRACT_NOT_EXECUTABLE"):
        assert_duckdb_executable_ddl(ddl)
    assert_duckdb_executable_ddl("CREATE TABLE core.child(id INT);")
