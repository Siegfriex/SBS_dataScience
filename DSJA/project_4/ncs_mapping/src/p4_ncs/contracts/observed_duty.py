"""Validate the Agent 2 observed-development duty handoff."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"
REQUIRED_ROW_FIELDS = {
    "trackId", "sectionId", "evidenceText", "jobTitle", "jobCode",
    "ncsEligibleFlag", "parseVersion", "inputSha256",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DutyInputValidation:
    path: Path
    row_count: int
    rows_sha256: str
    rows_sha256_declared: str | None
    rows_sha256_verified: bool
    warning_codes: tuple[str, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_and_validate_observed_duties(
    path: str | Path,
) -> tuple[pd.DataFrame, DutyInputValidation, dict[str, Any]]:
    """Return validated rows and provenance metadata.

    An early Agent 2 handoff omitted ``rowsSha256``. It remains usable only
    for M1: the digest is recomputed and the missing declaration is reported
    as a warning. A present but incorrect digest is fatal.
    """
    source_path = Path(path).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    _require(payload.get("agentId") == "P4-A2-PIPELINE", "unexpected duty handoff sender")
    _require(payload.get("recipientAgentId") == "P4-A4-NCS", "unexpected duty handoff recipient")
    _require(payload.get("handoffType") == "DUTY_INPUT_OBSERVED_DEVELOPMENT", "unexpected handoff type")
    _require(payload.get("status") == "OBSERVED_DEVELOPMENT_ONLY", "observed-only status required")
    _require(payload.get("contractVersion") == CONTRACT_VERSION, "contractVersion must be 2.1.2")
    _require(payload.get("crawlReleaseId") == CRAWL_RELEASE_ID, "crawlReleaseId mismatch")
    _require(payload.get("empiricalUseAllowed") is False, "empirical use must be disabled")
    _require(payload.get("promotionAllowed") in (None, False), "promotion must not be allowed")

    rows = payload.get("rows")
    _require(isinstance(rows, list), "rows must be a list")
    _require(payload.get("rowCount") == len(rows), "declared rowCount does not match rows")
    seen_section_ids: set[str] = set()
    for position, row in enumerate(rows):
        _require(isinstance(row, dict), f"row {position} is not an object")
        missing = REQUIRED_ROW_FIELDS.difference(row)
        _require(not missing, f"row {position} missing fields: {', '.join(sorted(missing))}")
        _require(bool(str(row["trackId"]).strip()), f"row {position} has empty trackId")
        section_id = str(row["sectionId"]).strip()
        _require(bool(section_id), f"row {position} has empty sectionId")
        _require(section_id not in seen_section_ids, f"duplicate sectionId: {section_id}")
        seen_section_ids.add(section_id)
        _require(bool(str(row["evidenceText"]).strip()), f"row {position} has empty evidenceText")
        _require(isinstance(row["ncsEligibleFlag"], bool), f"row {position} ncsEligibleFlag must be boolean")
        _require(bool(_SHA256.fullmatch(str(row["inputSha256"]))), f"row {position} inputSha256 is invalid")

    computed_sha = canonical_json_sha256(rows)
    declared_sha = payload.get("rowsSha256")
    warnings: list[str] = []
    if declared_sha is None:
        warnings.append("MISSING_DECLARED_ROWS_SHA256")
        verified = False
    else:
        _require(bool(_SHA256.fullmatch(str(declared_sha))), "rowsSha256 is invalid")
        _require(declared_sha == computed_sha, "rowsSha256 mismatch")
        verified = True

    frame = pd.DataFrame(rows)
    validation = DutyInputValidation(
        path=source_path,
        row_count=len(frame),
        rows_sha256=computed_sha,
        rows_sha256_declared=declared_sha,
        rows_sha256_verified=verified,
        warning_codes=tuple(warnings),
    )
    return frame, validation, payload
