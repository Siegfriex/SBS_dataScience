from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from p4.warehouse.connection import connect


OBSERVED_PROVENANCE = {
    "contractVersion": "2.1.2",
    "crawlReleaseId": "CRAWL_20260806_03",
    "dataVersion": "observed-dev-20260806.1",
    "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
    "empiricalAnalysisAllowed": False,
}

OBSERVED_DDL = """
CREATE SCHEMA IF NOT EXISTS observed;
CREATE TABLE IF NOT EXISTS observed.batch_metadata (
    contractVersion VARCHAR NOT NULL,
    crawlReleaseId VARCHAR NOT NULL,
    dataVersion VARCHAR NOT NULL,
    dataProvenance VARCHAR NOT NULL,
    empiricalAnalysisAllowed BOOLEAN NOT NULL,
    parseVersion VARCHAR NOT NULL,
    createdAt TIMESTAMPTZ DEFAULT TIMESTAMPTZ '2026-08-06 00:00:00+09:00'
);
CREATE TABLE IF NOT EXISTS observed.manifest_cursor (
    lastProcessedManifestOffset BIGINT NOT NULL,
    lastProcessedRawSha256 VARCHAR NOT NULL,
    inputReleaseId VARCHAR NOT NULL,
    parseVersion VARCHAR NOT NULL,
    processedAt TIMESTAMPTZ DEFAULT TIMESTAMPTZ '2026-08-06 00:00:00+09:00',
    PRIMARY KEY (lastProcessedRawSha256, parseVersion)
);
"""


def _assert_observed_path(path: Path) -> None:
    if path.name != "p4.observed-dev.duckdb":
        raise ValueError("observed-development warehouse must use p4.observed-dev.duckdb")


def bootstrap_observed_warehouse(
    path: str | Path,
    parse_version: str,
    provenance: Mapping[str, Any] = OBSERVED_PROVENANCE,
) -> dict[str, Any]:
    database = Path(path)
    _assert_observed_path(database)
    if dict(provenance) != OBSERVED_PROVENANCE:
        raise ValueError("observed-development warehouse requires the fixed non-empirical provenance envelope")
    with connect(database) as connection:
        connection.execute(OBSERVED_DDL)
        existing = connection.execute("SELECT * EXCLUDE(createdAt) FROM observed.batch_metadata").fetchall()
        expected = (*OBSERVED_PROVENANCE.values(), parse_version)
        if existing and any(tuple(row) != expected for row in existing):
            raise ValueError("observed warehouse contains incompatible provenance")
        if not existing:
            connection.execute(
                "INSERT INTO observed.batch_metadata "
                "(contractVersion,crawlReleaseId,dataVersion,dataProvenance,empiricalAnalysisAllowed,parseVersion) "
                "VALUES (?,?,?,?,?,?)",
                list(expected),
            )
        canonical_objects = connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw','core','ncs','mart','qa')"
        ).fetchone()[0]
    if canonical_objects:
        raise ValueError("observed-development warehouse must not contain canonical schemas")
    return {**OBSERVED_PROVENANCE, "parseVersion": parse_version, "canonicalObjectCount": 0}


def replace_observed_table(path: str | Path, table_name: str, frame: pd.DataFrame) -> None:
    database = Path(path)
    _assert_observed_path(database)
    if not table_name.replace("_", "").isalnum():
        raise ValueError("unsafe observed table name")
    with connect(database) as connection:
        connection.register("observed_frame", frame)
        connection.execute(f"CREATE OR REPLACE TABLE observed.{table_name} AS SELECT * FROM observed_frame")
        connection.unregister("observed_frame")


def observed_inventory(path: str | Path) -> dict[str, int]:
    with connect(path, read_only=True) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='observed' ORDER BY table_name"
            ).fetchall()
        ]
        return {name: int(connection.execute(f"SELECT COUNT(*) FROM observed.{name}").fetchone()[0]) for name in names}
