"""Content-addressed and atomic storage helpers."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return
        if immutable:
            raise RuntimeError(f"Immutable path collision: {path}")
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def atomic_write_text(path: Path, text: str, *, immutable: bool = False) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), immutable=immutable)


def atomic_write_json(path: Path, value: Any, *, immutable: bool = False) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", immutable=immutable)


def write_parquet_atomic(frame: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def write_csv_atomic(frame: Any, path: Path, *, encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    frame.to_csv(temporary, index=False, encoding=encoding)
    os.replace(temporary, path)


def write_gzip_content_addressed(raw_root: Path, entity: str, period: str, body: bytes) -> tuple[Path, str]:
    digest = sha256_bytes(body)
    year, month = period.split("-")
    suffix = "json.gz" if entity == "index" else "html.gz"
    path = raw_root / entity / year / month / f"{digest}.{suffix}"
    atomic_write_bytes(path, gzip.compress(body, mtime=0), immutable=True)
    return path, digest
