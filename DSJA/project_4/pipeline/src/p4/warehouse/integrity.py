from __future__ import annotations

import re
from typing import Iterable

import duckdb


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def _safe_table(value: str) -> str:
    if not _TABLE.fullmatch(value):
        raise ValueError(f"unsafe table: {value}")
    return value


def _safe_column(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsafe column: {value}")
    return value


def primary_key_duplicates(connection: duckdb.DuckDBPyConnection, table: str, columns: Iterable[str]) -> int:
    table = _safe_table(table)
    keys = [_safe_column(column) for column in columns]
    if not keys:
        raise ValueError("at least one key column is required")
    group = ", ".join(keys)
    query = f"SELECT COUNT(*) FROM (SELECT {group}, COUNT(*) n FROM {table} GROUP BY {group} HAVING n > 1)"
    return connection.execute(query).fetchone()[0]


def null_rate(connection: duckdb.DuckDBPyConnection, table: str, column: str) -> float:
    table = _safe_table(table)
    column = _safe_column(column)
    value = connection.execute(
        f"SELECT CASE WHEN COUNT(*)=0 THEN 0 ELSE AVG(CASE WHEN {column} IS NULL THEN 1.0 ELSE 0.0 END) END FROM {table}"
    ).fetchone()[0]
    return float(value)


def orphan_count(
    connection: duckdb.DuckDBPyConnection,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> int:
    child_table = _safe_table(child_table)
    child_column = _safe_column(child_column)
    parent_table = _safe_table(parent_table)
    parent_column = _safe_column(parent_column)
    query = f"""
        SELECT COUNT(*)
        FROM {child_table} child
        LEFT JOIN {parent_table} parent ON child.{child_column} = parent.{parent_column}
        WHERE child.{child_column} IS NOT NULL AND parent.{parent_column} IS NULL
    """
    return connection.execute(query).fetchone()[0]

