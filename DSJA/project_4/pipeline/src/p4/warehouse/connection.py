from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb


@contextmanager
def connect(path: str | Path, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    target = Path(path)
    if not read_only:
        target.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(target), read_only=read_only)
    try:
        connection.execute("SET TimeZone = 'Asia/Seoul'")
        yield connection
    finally:
        connection.close()

