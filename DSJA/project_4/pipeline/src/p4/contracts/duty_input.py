from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from p4.common.hashing import canonical_json_sha256

from jsonschema import Draft202012Validator


REQUIRED_HANDOFF_FIELDS = {
    "agentId",
    "recipientAgentId",
    "handoffType",
    "status",
    "contractVersion",
    "schemaVersion",
    "grain",
    "empiricalUseAllowed",
    "rowSchema",
    "fixtureRows",
}


def validate_duty_input_handoff(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_HANDOFF_FIELDS.difference(payload))
    if missing:
        raise ValueError(f"Agent 4 duty handoff missing fields: {', '.join(missing)}")
    if payload["agentId"] != "P4-A2-PIPELINE" or payload["recipientAgentId"] != "P4-A4-NCS":
        raise ValueError("Agent 4 duty handoff has unexpected sender or recipient")
    if payload["contractVersion"] != "2.1.2":
        raise ValueError("Agent 4 duty handoff requires contractVersion=2.1.2")
    if payload["status"] != "SCHEMA_AND_FIXTURE_ONLY" or payload["empiricalUseAllowed"] is not False:
        raise ValueError("pre-full-crawl duty handoff must remain schema-and-fixture-only")

    row_schema = payload["rowSchema"]
    Draft202012Validator.check_schema(row_schema)
    validator = Draft202012Validator(row_schema)
    rows = payload["fixtureRows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Agent 4 duty handoff requires at least one structural fixture row")
    for row in rows:
        validator.validate(row)
        if row["dataProvenance"] == "EMPIRICAL":
            raise ValueError("fixture duty rows cannot claim EMPIRICAL provenance")
    return payload


OBSERVED_DUTY_REQUIRED_FIELDS = {
    "trackId",
    "sectionId",
    "evidenceText",
    "jobTitle",
    "jobCode",
    "ncsEligibleFlag",
    "parseVersion",
    "inputSha256",
}


def validate_observed_duty_input_handoff(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("agentId") != "P4-A2-PIPELINE" or payload.get("recipientAgentId") != "P4-A4-NCS":
        raise ValueError("observed duty handoff has unexpected sender or recipient")
    if payload.get("contractVersion") != "2.1.2" or payload.get("crawlReleaseId") != "CRAWL_20260806_03":
        raise ValueError("observed duty handoff requires the CRAWL_03/v2.1.2 envelope")
    if payload.get("status") != "OBSERVED_DEVELOPMENT_ONLY" or payload.get("empiricalUseAllowed") is not False:
        raise ValueError("observed duty input cannot be used as empirical evidence")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("observed duty handoff rows must be a list")
    for row in rows:
        missing = OBSERVED_DUTY_REQUIRED_FIELDS.difference(row)
        if missing:
            raise ValueError(f"observed duty row missing fields: {', '.join(sorted(missing))}")
        if len(str(row["inputSha256"])) != 64:
            raise ValueError("observed duty row inputSha256 must be SHA-256")
    if payload.get("rowCount") != len(rows):
        raise ValueError("observed duty rowCount does not match rows")
    if payload.get("rowsSha256") and payload["rowsSha256"] != canonical_json_sha256(rows):
        raise ValueError("observed duty rowsSha256 mismatch")
    if payload.get("promotionAllowed") not in {None, False}:
        raise ValueError("observed duty input cannot allow promotion")
    return payload
