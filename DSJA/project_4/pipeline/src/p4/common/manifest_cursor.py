from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ManifestCursor:
    lastProcessedManifestOffset: int
    lastProcessedRawSha256: str
    inputReleaseId: str
    parseVersion: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def should_process_raw(
    raw_sha256: str,
    parse_version: str,
    processed: Iterable[Mapping[str, object]],
) -> bool:
    """Skip the same raw bytes unless parser semantics changed."""
    return not any(
        str(row.get("lastProcessedRawSha256")) == raw_sha256
        and str(row.get("parseVersion")) == parse_version
        for row in processed
    )


def advance_cursor(offset: int, raw_sha256: str, release_id: str, parse_version: str) -> ManifestCursor:
    if offset < 0 or not raw_sha256 or not release_id.startswith("CRAWL_") or not parse_version:
        raise ValueError("manifest cursor requires a nonnegative offset, raw SHA, CRAWL_ release, and parse version")
    return ManifestCursor(offset, raw_sha256, release_id, parse_version)


def plan_manifest_work(
    manifest_rows: Iterable[Mapping[str, Any]],
    processed: Iterable[Mapping[str, object]],
    parse_version: str,
) -> list[dict[str, Any]]:
    processed_rows = list(processed)
    plan: list[dict[str, Any]] = []
    for offset, row in enumerate(manifest_rows):
        raw_sha = str(row.get("contentSha256") or row.get("rawSha256") or "")
        if not raw_sha:
            continue
        process = should_process_raw(raw_sha, parse_version, processed_rows)
        plan.append(
            {
                "manifestOffset": offset,
                "rawSha256": raw_sha,
                "parseVersion": parse_version,
                "action": "PROCESS" if process else "SKIP_IDENTICAL_RAW_AND_PARSE_VERSION",
            }
        )
    return plan
