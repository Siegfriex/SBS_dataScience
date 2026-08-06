"""JSONL manifests and checksum validation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .storage import atomic_write_bytes, canonical_json, sha256_bytes, sha256_file, write_gzip_content_addressed


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def append_jsonl_once(path: Path, row: dict, key_field: str = "rowId") -> bool:
    """Append one durable row unless its stable key is already present."""

    if key_field not in row:
        raise KeyError(f"manifest row missing {key_field}")
    key = row[key_field]
    if any(old.get(key_field) == key for old in load_jsonl(path)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def stable_row_id(row: dict, fields: tuple[str, ...]) -> str:
    return sha256_bytes(canonical_json({key: row.get(key) for key in fields}).encode("utf-8"))


def verify_checksum_file(checksum_path: Path, base: Path) -> dict:
    result: dict[str, object] = {"passed": [], "failed": []}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(None, 1)
        relative = relative.strip().lstrip("*")
        target = base / relative
        if not target.is_file():
            result["failed"].append({"path": relative, "reason": "missing"})
        elif sha256_file(target) != expected:
            result["failed"].append({"path": relative, "reason": "sha256Mismatch"})
        else:
            result["passed"].append(relative)
    result["ok"] = not result["failed"]
    return result


def write_checksums(base: Path, relative_paths: list[str], output: Path | None = None) -> Path:
    output = output or base / "CHECKSUMS.sha256"
    lines = [f"{sha256_file(base / relative)}  {relative}" for relative in sorted(relative_paths)]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


class RawResponseRecorder:
    """Persist accepted Linkareer bytes and one idempotent fetch lineage row."""

    def __init__(self, crawl_root: Path, run_id: str, manifest_path: Path, collector_version: str = "1.0.0"):
        self.crawl_root = crawl_root
        self.raw_root = crawl_root / "data" / "raw" / "linkareer"
        self.run_id = run_id
        self.manifest_path = manifest_path
        self.collector_version = collector_version

    def __call__(self, url: str, response, context: dict) -> dict:
        entity = context.get("entityType")
        period = context.get("period")
        if entity not in {"index", "detail", "asset"} or not period:
            raise ValueError("response capture requires entityType and period")
        body = response.content
        if entity in {"index", "detail"}:
            raw_path, digest = write_gzip_content_addressed(self.raw_root, entity, period, body)
        else:
            digest = sha256_bytes(body)
            year, month = period.split("-")
            raw_path = self.raw_root / entity / year / month / f"{digest}.bin"
            atomic_write_bytes(raw_path, body, immutable=True)
        request = getattr(response, "request", None)
        request_url = str(getattr(request, "url", url))
        row = {
            "crawlRunId": self.run_id,
            "entityType": entity,
            "requestUrl": request_url,
            "operationName": context.get("operationName"),
            "variablesHash": context.get("variablesHash"),
            "httpStatus": response.status_code,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "contentSha256": digest,
            "rawPath": str(raw_path.relative_to(self.crawl_root)),
            "bytes": len(body),
            "collectorVersion": self.collector_version,
        }
        row["rowId"] = stable_row_id(row, ("requestUrl", "httpStatus", "contentSha256"))
        append_jsonl_once(self.manifest_path, row)
        return row
