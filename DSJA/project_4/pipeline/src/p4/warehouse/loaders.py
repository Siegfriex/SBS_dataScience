from __future__ import annotations

import re

import duckdb
import pandas as pd


_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def replace_from_frame(connection: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame) -> int:
    if not _TABLE_NAME.fullmatch(table):
        raise ValueError(f"unsafe table name: {table}")
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

