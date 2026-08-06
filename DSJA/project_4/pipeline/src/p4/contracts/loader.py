from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_CONTRACT_FILES = (
    "p4_contract.yaml",
    "warehouse_duckdb.sql",
    "contract.schema.json",
    "CONTRACT_MANIFEST.json",
    "CHECKSUMS.sha256",
)


@dataclass(frozen=True)
class CrawlRelease:
    release_id: str
    contract_version: str
    manifest_paths: list[str]
    coverage_path: str
    checksum_path: str
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
            "source_start": payload.get("source_start", payload.get("sourceStart")),
            "source_end": payload.get("source_end", payload.get("sourceEnd")),
        }
        required = ("release_id", "contract_version", "manifest_paths", "coverage_path", "checksum_path")
        missing = [field for field in required if aliases[field] in (None, "", [])]
        if missing:
            raise ValueError(f"crawl HANDOFF missing required fields: {', '.join(missing)}")
        if not isinstance(aliases["manifest_paths"], list):
            raise TypeError("manifest_paths must be a list")
        return cls(**aliases)


def load_crawl_release(path: str | Path) -> CrawlRelease:
    with Path(path).open(encoding="utf-8") as stream:
        return CrawlRelease.from_dict(json.load(stream))


def find_crawl_releases(project_root: str | Path) -> list[Path]:
    return sorted(Path(project_root).glob("crawl/releases/*/HANDOFF.json"))


def contract_bundle_status(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle)
    missing = [name for name in REQUIRED_CONTRACT_FILES if not (root / name).is_file()]
    return {
        "bundlePath": str(root),
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

