from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
