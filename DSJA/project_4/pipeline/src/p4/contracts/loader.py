from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from p4.common.hashing import sha256_file


CANONICAL_SCHEMA_FILENAME = "p4_contract.schema.json"
REQUIRED_CONTRACT_FILES = (
    "p4_contract.yaml",
    CANONICAL_SCHEMA_FILENAME,
    "warehouse_duckdb.sql",
    "CONTRACT_MANIFEST.json",
    "CHECKSUMS.sha256",
    "AGENT3_TO_AGENT2_HANDOFF.json",
)
REQUIRED_CRAWL_FIELDS = (
    "release_id",
    "contract_version",
    "manifest_paths",
    "coverage_path",
    "checksum_path",
    "query_registry_path",
    "schema_snapshot_path",
)
_VERSION = re.compile(r"P4_CONTRACT_v(?P<version>\d+(?:\.\d+)+)$")


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", value)
    if not match:
        return ()
    return tuple(int(part) for part in match.group().split("."))


@dataclass(frozen=True)
class ContractBundle:
    root: Path
    contract_version: str

    @property
    def schema_path(self) -> Path:
        return self.root / CANONICAL_SCHEMA_FILENAME

    @classmethod
    def from_path(cls, path: str | Path) -> "ContractBundle":
        root = Path(path)
        match = _VERSION.fullmatch(root.name)
        if not match:
            raise ValueError(f"contract bundle directory must be P4_CONTRACT_vX.Y.Z: {root.name}")
        return cls(root=root, contract_version=match.group("version"))


@dataclass(frozen=True)
class CrawlRelease:
    release_id: str
    contract_version: str
    manifest_paths: list[str]
    coverage_path: str
    checksum_path: str
    query_registry_path: str
    schema_snapshot_path: str
    source_start: str | None = None
    source_end: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CrawlRelease":
        aliases = {
            "release_id": payload.get("release_id", payload.get("releaseId")),
            "contract_version": payload.get("contract_version", payload.get("contractVersion")),
            "manifest_paths": payload.get("manifest_paths", payload.get("manifestPaths")),
            "coverage_path": payload.get("coverage_path", payload.get("coveragePath")),
            "checksum_path": payload.get("checksum_path", payload.get("checksumPath")),
            "query_registry_path": payload.get("query_registry_path", payload.get("queryRegistryPath")),
            "schema_snapshot_path": payload.get("schema_snapshot_path", payload.get("schemaSnapshotPath")),
            "source_start": payload.get("source_start", payload.get("sourceStart")),
            "source_end": payload.get("source_end", payload.get("sourceEnd")),
        }
        missing = [field for field in REQUIRED_CRAWL_FIELDS if aliases[field] in (None, "", [])]
        if missing:
            raise ValueError(f"crawl HANDOFF missing required fields: {', '.join(missing)}")
        if not isinstance(aliases["manifest_paths"], list):
            raise TypeError("manifest_paths must be a list")
        release_id = str(aliases["release_id"])
        if release_id.upper().startswith("RECON"):
            raise ValueError("RECON packages are audit evidence, not immutable crawl releases")
        if not release_id.upper().startswith("CRAWL_"):
            raise ValueError("release_id must use the CRAWL_ prefix")
        return cls(**aliases)


def discover_contract_bundles(contracts_root: str | Path) -> list[ContractBundle]:
    root = Path(contracts_root)
    bundles: list[ContractBundle] = []
    if not root.is_dir():
        return bundles
    for path in root.iterdir():
        if path.is_dir() and _VERSION.fullmatch(path.name):
            bundles.append(ContractBundle.from_path(path))
    return sorted(bundles, key=lambda item: _version_tuple(item.contract_version))


def latest_contract_bundle(contracts_root: str | Path) -> ContractBundle | None:
    bundles = discover_contract_bundles(contracts_root)
    return bundles[-1] if bundles else None


def load_crawl_release(path: str | Path) -> CrawlRelease:
    with Path(path).open(encoding="utf-8") as stream:
        return CrawlRelease.from_dict(json.load(stream))


def find_crawl_releases(project_root: str | Path) -> list[Path]:
    return sorted(Path(project_root).glob("crawl/releases/CRAWL_*/HANDOFF.json"))


def contract_bundle_status(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle)
    missing = [name for name in REQUIRED_CONTRACT_FILES if not (root / name).is_file()]
    version = None
    match = _VERSION.fullmatch(root.name)
    if match:
        version = match.group("version")
    return {
        "bundlePath": str(root),
        "contractVersion": version,
        "exists": root.is_dir(),
        "missingFiles": missing,
        "ready": root.is_dir() and not missing,
    }


def load_contract_yaml(bundle: str | Path) -> dict[str, Any]:
    with (Path(bundle) / "p4_contract.yaml").open(encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise TypeError("p4_contract.yaml must contain a mapping")
    return payload


def _resolve_release_path(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise ValueError(f"release path escapes release directory: {relative}")
    return target


def _manifest_rows(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix == ".parquet":
        yield from pd.read_parquet(path).to_dict(orient="records")
    elif path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as stream:
            yield from csv.DictReader(stream)
    else:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            for line in text.splitlines():
                if line.strip():
                    yield json.loads(line)
        else:
            payload = json.loads(text)
            if isinstance(payload, list):
                yield from payload
            elif isinstance(payload, dict):
                rows = payload.get("rows", payload.get("artifacts", [payload]))
                yield from rows


def manifest_has_raw_lineage(path: Path) -> bool:
    required = {"sourceUrl", "rawPath", "rawSha256"}
    try:
        return any(required.issubset(row) and all(row.get(field) for field in required) for row in _manifest_rows(path))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def validate_crawl_release(path: str | Path) -> dict[str, Any]:
    handoff_path = Path(path)
    release_root = handoff_path.parent.resolve()
    release = load_crawl_release(handoff_path)
    targets = {
        "manifests": [_resolve_release_path(release_root, value) for value in release.manifest_paths],
        "coverage": _resolve_release_path(release_root, release.coverage_path),
        "checksums": _resolve_release_path(release_root, release.checksum_path),
        "queryRegistry": _resolve_release_path(release_root, release.query_registry_path),
        "schemaSnapshot": _resolve_release_path(release_root, release.schema_snapshot_path),
    }
    missing = [str(path) for key, value in targets.items() for path in (value if isinstance(value, list) else [value]) if not path.is_file()]
    if missing:
        raise ValueError(f"crawl release references missing files: {missing}")
    lineage = [manifest_has_raw_lineage(path) for path in targets["manifests"]]
    if not lineage or not all(lineage):
        raise ValueError("crawl release manifest lacks sourceUrl/rawPath/rawSha256 lineage")

    checksum_lines = targets["checksums"].read_text(encoding="utf-8").splitlines()
    failures: list[str] = []
    checked = 0
    for line in checksum_lines:
        if not line.strip():
            continue
        digest, relative = line.strip().split(maxsplit=1)
        target = _resolve_release_path(release_root, relative.lstrip("*"))
        checked += 1
        if not target.is_file() or sha256_file(target) != digest:
            failures.append(relative)
    if not checked or failures:
        raise ValueError(f"crawl release checksum failure: {failures or ['empty checksum file']}")
    return {
        "release": release,
        "releaseRoot": str(release_root),
        "checksumCount": checked,
        "rawLineageVerified": True,
        "paths": {key: [str(item) for item in value] if isinstance(value, list) else str(value) for key, value in targets.items()},
    }

