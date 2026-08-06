"""Read-only loader for the Agent 1 NCS unit release artifact.

Raw NCS source files live under Agent 1's `crawl/releases/**` ownership path
and are never copied or modified here -- callers pass the release root and
this module reads directly from it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class NcsUnitSourceMeta:
    release_root: Path
    raw_path: Path
    raw_sha256: str
    checksum_verified: bool
    encoding: str


def _read_listed_sha256(release_root: Path, relative_path: str) -> str | None:
    checksums_path = release_root / "CHECKSUMS.sha256"
    if not checksums_path.exists():
        return None
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1].strip() == relative_path:
            return parts[0].strip()
    return None


def load_raw_ncs_unit(release_root: Path, relative_path: str = "data/ncs/ncsUnit_20260806.utf8.csv", encoding: str = "utf-8-sig") -> tuple[pd.DataFrame, NcsUnitSourceMeta]:
    """Load the NCS unit CSV from an Agent 1 release directory.

    `release_root` must point at an extracted or checked-out copy of a
    `crawl/releases/CRAWL_*` directory (e.g. via `git archive`). This function
    never writes to `release_root`.
    """
    raw_path = release_root / relative_path
    df = pd.read_csv(raw_path, encoding=encoding)
    df.columns = [c.strip() for c in df.columns]

    actual_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    listed_sha256 = _read_listed_sha256(release_root, relative_path)
    checksum_verified = listed_sha256 is not None and listed_sha256 == actual_sha256

    meta = NcsUnitSourceMeta(
        release_root=release_root,
        raw_path=raw_path,
        raw_sha256=actual_sha256,
        checksum_verified=checksum_verified,
        encoding=encoding,
    )
    return df, meta
