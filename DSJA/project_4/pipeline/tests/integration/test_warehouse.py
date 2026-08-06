import pandas as pd

from p4.warehouse.bootstrap import bootstrap_development_warehouse
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
                "postingRawId": "RAW_1",
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
        assert primary_key_duplicates(connection, "raw.linkareer_posting", ["postingRawId"]) == 0
        assert null_rate(connection, "raw.linkareer_posting", "sourceUrl") == 0.0

