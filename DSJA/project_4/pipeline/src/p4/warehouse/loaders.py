from __future__ import annotations

import re
from typing import Any, Mapping

import duckdb
import pandas as pd

from p4.quality.provenance import ProvenanceContext, require_production_provenance


_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def is_canonical_warehouse(connection: duckdb.DuckDBPyConnection) -> bool:
    """Identify the v2.1.2 canonical warehouse by its contract QA gate."""
    return bool(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'qa'
              AND table_name = 'vAnalysisReadyGate'
              AND table_type = 'VIEW'
            """
        ).fetchone()[0]
    )


def _validate_frame_lineage(frame: pd.DataFrame, provenance: Mapping[str, str]) -> None:
    for column in ("contractVersion", "crawlReleaseId", "dataVersion"):
        if column not in frame.columns:
            continue
        observed = {str(value) for value in frame[column].dropna().unique()}
        if observed != {provenance[column]}:
            raise ValueError(
                f"production mart frame {column} does not match provenance: "
                f"observed={sorted(observed)}, expected={provenance[column]}"
            )


def replace_from_frame(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    frame: pd.DataFrame,
    *,
    provenance: Mapping[str, Any] | ProvenanceContext | None = None,
) -> int:
    if not _TABLE_NAME.fullmatch(table):
        raise ValueError(f"unsafe table name: {table}")
    if table.startswith("mart.") and is_canonical_warehouse(connection):
        validated = require_production_provenance(provenance)
        _validate_frame_lineage(frame, validated)
    connection.register("_p4_frame", frame)
    try:
        connection.execute(f"DELETE FROM {table}")
        if len(frame):
            columns = list(frame.columns)
            quoted = ", ".join(f'"{column}"' for column in columns)
            connection.execute(f"INSERT INTO {table} ({quoted}) SELECT {quoted} FROM _p4_frame")
    finally:
        connection.unregister("_p4_frame")
    return len(frame)


def table_to_frame(connection: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    if not _TABLE_NAME.fullmatch(table):
        raise ValueError(f"unsafe table name: {table}")
    return connection.execute(f"SELECT * FROM {table}").fetchdf()
