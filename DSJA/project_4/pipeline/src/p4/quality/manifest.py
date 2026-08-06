from __future__ import annotations

from pathlib import Path

import pandas as pd

from p4.common.hashing import sha256_file


def artifact_record(path: str | Path, schema_version: str, rows: int | None = None) -> dict[str, object]:
    target = Path(path)
    if rows is None and target.suffix == ".parquet":
        rows = len(pd.read_parquet(target))
    return {
        "path": str(target),
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "rows": rows if rows is not None else 0,
        "schemaVersion": schema_version,
    }

