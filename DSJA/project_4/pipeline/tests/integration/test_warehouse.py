import pandas as pd
from pathlib import Path

from p4.warehouse.bootstrap import bootstrap_canonical_warehouse, bootstrap_development_warehouse
from p4.warehouse.connection import connect
from p4.warehouse.integrity import null_rate, primary_key_duplicates
from p4.warehouse.loaders import replace_from_frame


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
