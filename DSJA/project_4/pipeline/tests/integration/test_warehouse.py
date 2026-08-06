import pandas as pd
import pytest
from pathlib import Path

from p4.warehouse.bootstrap import bootstrap_canonical_warehouse, bootstrap_development_warehouse
from p4.warehouse.connection import connect
from p4.warehouse.integrity import null_rate, primary_key_duplicates
from p4.warehouse.loaders import is_canonical_warehouse, replace_from_frame


def test_development_warehouse_bootstrap_and_load(tmp_path):
    database = tmp_path / "p4.duckdb"
    tables = bootstrap_development_warehouse(database)
    assert "raw.linkareer_posting" in tables
    assert "mart.time_series" in tables
    frame = pd.DataFrame(
        [
            {
                "rawPostingId": "RAW_1",
                "sourcePostingId": "1",
                "sourceUrl": "https://example.test/1",
                "fetchedAt": pd.Timestamp("2026-08-06T12:00:00+09:00"),
                "rawSha256": "a" * 64,
                "titleRaw": "fixture",
                "companyRaw": "fixture",
                "postedAtRaw": "2026-08-01",
                "bodyRaw": "synthetic test fixture",
                "postingKind": "recruit",
            }
        ]
    )
    with connect(database) as connection:
        assert replace_from_frame(connection, "raw.linkareer_posting", frame) == 1
        assert primary_key_duplicates(connection, "raw.linkareer_posting", ["rawPostingId"]) == 0
        assert null_rate(connection, "raw.linkareer_posting", "sourceUrl") == 0.0


def test_canonical_v212_warehouse_is_idempotent_and_empty_is_not_evaluated(tmp_path):
    ddl = Path(__file__).resolve().parents[3] / "shared/contracts/P4_CONTRACT_v2.1.2/warehouse_duckdb.sql"
    result = bootstrap_canonical_warehouse(tmp_path / "p4.duckdb", ddl)
    assert result["ddlStatementCount"] >= 36
    assert result["idempotent"] is True
    assert (result["schemaCount"], result["tableCount"], result["viewCount"]) == (5, 26, 6)
    assert result["analysisReadyGate"] == "NOT_EVALUATED"
    assert result["emptyDatabasePass"] is False
    assert result["crossSchemaForeignKeyCount"] == 0
    with connect(tmp_path / "p4.duckdb", read_only=True) as connection:
        assert is_canonical_warehouse(connection) is True


def test_canonical_mart_write_requires_empirical_provenance(tmp_path):
    ddl = Path(__file__).resolve().parents[3] / "shared/contracts/P4_CONTRACT_v2.1.2/warehouse_duckdb.sql"
    database = tmp_path / "p4.duckdb"
    bootstrap_canonical_warehouse(database, ddl)
    frame = pd.DataFrame(columns=["trackId"])
    with connect(database) as connection:
        with pytest.raises(ValueError, match="missing provenance fields"):
            replace_from_frame(connection, "mart.postingAnalysisMart", frame)
        with pytest.raises(ValueError, match="dataProvenance=EMPIRICAL"):
            replace_from_frame(
                connection,
                "mart.postingAnalysisMart",
                frame,
                provenance={
                    "contractVersion": "2.1.2",
                    "crawlReleaseId": "CRAWL_FIXTURE",
                    "dataVersion": "fixture-v1",
                    "dataProvenance": "SYNTHETIC",
                },
            )
        assert replace_from_frame(
            connection,
            "mart.postingAnalysisMart",
            frame,
            provenance={
                "contractVersion": "2.1.2",
                "crawlReleaseId": "CRAWL_FULL_1",
                "dataVersion": "full-v1",
                "dataProvenance": "EMPIRICAL",
            },
        ) == 0


def test_canonical_bootstrap_rejects_synthetic_database_before_mutation(tmp_path):
    database = tmp_path / "p4.duckdb"
    bootstrap_development_warehouse(database)
    ddl = Path(__file__).resolve().parents[3] / "shared/contracts/P4_CONTRACT_v2.1.2/warehouse_duckdb.sql"
    with pytest.raises(ValueError, match="quarantine"):
        bootstrap_canonical_warehouse(database, ddl)
    with connect(database, read_only=True) as connection:
        assert is_canonical_warehouse(connection) is False
