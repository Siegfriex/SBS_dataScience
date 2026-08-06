"""Portable external authority and fail-closed validation for raw SSR objects.

Raw bytes deliberately remain outside Git.  A consumer must supply the mount
identified by ``storageRootId`` and every object must match both its compressed
and decompressed digests before it can be consumed.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import pandas as pd


AVAILABLE = "AVAILABLE"
RAW_ROOT_UNMOUNTED = "RAW_ROOT_UNMOUNTED"
RAW_OBJECT_MISSING = "RAW_OBJECT_MISSING"
COMPRESSED_SHA_MISMATCH = "COMPRESSED_SHA_MISMATCH"
CONTENT_SHA_MISMATCH = "CONTENT_SHA_MISMATCH"
BYTE_COUNT_MISMATCH = "BYTE_COUNT_MISMATCH"


class RawAuthorityBlocked(RuntimeError):
    """Raised when an external raw authority cannot be verified."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _relative_locator(value: str) -> str:
    locator = PurePosixPath(str(value))
    if locator.is_absolute() or ".." in locator.parts or not locator.parts:
        raise ValueError(f"portable object locator required: {value!r}")
    return locator.as_posix()


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("retrievedAtUtc must include an offset")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def source_url_fingerprint(value: str) -> str:
    """Hash a URL without persisting the potentially identifying source URL."""

    return sha256_bytes(str(value).encode("utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_raw_object_manifest(
    raw_detail_rows: Iterable[Mapping[str, Any]],
    raw_root: Path | None,
    *,
    storage_root_id: str,
    mount_policy_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build a portable manifest and a validation audit from a mounted root.

    ``raw_root`` is runtime-only and is never returned.  The manifest contains
    only a stable root identifier and a repository-shaped relative locator.
    """

    source_rows = list(raw_detail_rows)
    mounted = raw_root is not None and raw_root.is_dir()
    manifest: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for source in source_rows:
        posting_id = str(source["sourcePostingId"])
        locator = _relative_locator(str(source["rawPath"]))
        expected_content_sha = str(source["rawSha256"])
        expected_content_bytes = int(source["bytes"])
        status = AVAILABLE
        compressed_sha = ""
        compressed_bytes = 0
        content_sha = ""
        content_bytes = 0
        if not mounted:
            status = RAW_ROOT_UNMOUNTED
        else:
            object_path = raw_root / Path(locator)
            if not object_path.is_file():
                status = RAW_OBJECT_MISSING
            else:
                raw_bytes = object_path.read_bytes()
                compressed_sha = sha256_bytes(raw_bytes)
                compressed_bytes = len(raw_bytes)
                try:
                    content = gzip.decompress(raw_bytes)
                except Exception:
                    content = b""
                    status = CONTENT_SHA_MISMATCH
                content_sha = sha256_bytes(content)
                content_bytes = len(content)
                if status == AVAILABLE and content_sha != expected_content_sha:
                    status = CONTENT_SHA_MISMATCH
                elif status == AVAILABLE and content_bytes != expected_content_bytes:
                    status = BYTE_COUNT_MISMATCH
        row = {
            "rawPostingId": posting_id,
            "sourceMode": "observed-dev",
            "storageRootId": storage_root_id,
            "objectLocatorRelative": locator,
            "compressedSha256": compressed_sha,
            "contentSha256": content_sha or expected_content_sha,
            "byteCount": compressed_bytes,
            "contentByteCount": content_bytes or expected_content_bytes,
            "retrievedAtUtc": _utc(str(source["fetchedAt"])),
            "sourceUrlFingerprint": source_url_fingerprint(str(source["sourceUrl"])),
            "mountPolicyVersion": mount_policy_version,
            "availabilityStatus": status,
        }
        manifest.append(row)
        audit.append({
            "rawPostingId": posting_id,
            "storageRootId": storage_root_id,
            "objectLocatorRelative": locator,
            "expectedContentSha256": expected_content_sha,
            "observedCompressedSha256": compressed_sha,
            "observedContentSha256": content_sha,
            "expectedContentByteCount": expected_content_bytes,
            "observedContentByteCount": content_bytes,
            "availabilityStatus": status,
            "downstreamConsumable": status == AVAILABLE,
        })
    return manifest, audit


def require_complete_raw_authority(audit_rows: Iterable[Mapping[str, Any]]) -> None:
    failures = [str(row.get("availabilityStatus")) for row in audit_rows if row.get("availabilityStatus") != AVAILABLE]
    if failures:
        raise RawAuthorityBlocked("RAW_AUTHORITY_BLOCKED: " + ",".join(sorted(set(failures))))


def validate_manifest_against_mount(
    manifest_rows: Iterable[Mapping[str, Any]], raw_root: Path | None
) -> list[dict[str, Any]]:
    """Revalidate a committed manifest without mutating or replacing objects."""

    mounted = raw_root is not None and raw_root.is_dir()
    rows: list[dict[str, Any]] = []
    for item in manifest_rows:
        locator = _relative_locator(str(item["objectLocatorRelative"]))
        status = AVAILABLE
        if not mounted:
            status = RAW_ROOT_UNMOUNTED
        else:
            path = raw_root / Path(locator)
            if not path.is_file():
                status = RAW_OBJECT_MISSING
            else:
                compressed = path.read_bytes()
                if sha256_bytes(compressed) != item["compressedSha256"]:
                    status = COMPRESSED_SHA_MISMATCH
                else:
                    try:
                        content = gzip.decompress(compressed)
                    except Exception:
                        content = b""
                        status = CONTENT_SHA_MISMATCH
                    if status == AVAILABLE and sha256_bytes(content) != item["contentSha256"]:
                        status = CONTENT_SHA_MISMATCH
                    elif status == AVAILABLE and len(compressed) != int(item["byteCount"]):
                        status = BYTE_COUNT_MISMATCH
        rows.append({
            "rawPostingId": str(item["rawPostingId"]),
            "storageRootId": str(item["storageRootId"]),
            "objectLocatorRelative": locator,
            "availabilityStatus": status,
            "bindingStatus": "MATCHED" if status == AVAILABLE else "QUARANTINED",
            "downstreamConsumable": status == AVAILABLE,
        })
    return rows


def audit_raw_posting_binding(
    raw_object_rows: Iterable[Mapping[str, Any]],
    raw_detail_rows: Iterable[Mapping[str, Any]],
    posting: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Bind raw objects, crawl lineage, and posting flags at ID grain."""

    objects = {str(row["rawPostingId"]): row for row in raw_object_rows}
    detail = {str(row["sourcePostingId"]): row for row in raw_detail_rows}
    posting_id_column = "sourcePostingId" if "sourcePostingId" in posting.columns else "postingId"
    flags = {
        str(row[posting_id_column]): bool(row.get("hasDetailRawHtml", False))
        for row in posting.to_dict("records")
    }
    all_ids = sorted(set(objects) | set(detail))
    rows: list[dict[str, Any]] = []
    for posting_id in all_ids:
        obj = objects.get(posting_id)
        lineage = detail.get(posting_id)
        raw_present = bool(obj and obj.get("availabilityStatus") == AVAILABLE)
        raw_sha = str(lineage.get("rawSha256", "")) if lineage else ""
        content_sha = str(obj.get("contentSha256", "")) if obj else ""
        posting_flag = flags.get(posting_id, False)
        reasons: list[str] = []
        if obj is None:
            reasons.append("RAW_OBJECT_MANIFEST_ROW_MISSING")
        elif not raw_present:
            reasons.append(str(obj.get("availabilityStatus") or "RAW_OBJECT_UNAVAILABLE"))
        if lineage is None:
            reasons.append("RAW_DETAIL_MANIFEST_ROW_MISSING")
        elif content_sha and raw_sha != content_sha:
            reasons.append("RAW_DETAIL_CONTENT_SHA_MISMATCH")
        if posting_id not in flags:
            reasons.append("POSTING_ROW_MISSING")
        elif not posting_flag:
            reasons.append("POSTING_FLAG_FALSE_FOR_RESOLVED_RAW")
        matched = not reasons
        status = "MATCHED" if matched else "QUARANTINED"
        rows.append({
            "postingId": posting_id,
            "rawPostingId": posting_id,
            "rawObjectPresent": raw_present,
            "rawSha256": raw_sha,
            "contentSha256": content_sha,
            "postingHasDetailRawHtml": posting_flag,
            "bindingStatus": status,
            "mismatchReason": "" if matched else ";".join(reasons),
            "quarantinePointer": "" if matched else f"quarantine://{obj.get('storageRootId', 'UNKNOWN')}/{posting_id}",
        })
    return rows
