"""Fail-closed request redaction and canonical hashing."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

_SECRET_KEY = re.compile(r"(?i)(?:auth|credential|key|password|secret|token)")
REDACTED = "[REDACTED]"


def redact_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(parameters):
        value = parameters[key]
        if _SECRET_KEY.search(str(key)):
            result[str(key)] = REDACTED
        elif isinstance(value, Mapping):
            result[str(key)] = redact_parameters(value)
        else:
            result[str(key)] = value
    return result


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redacted_request_manifest(
    *, api_contract_id: str, method: str, url: str, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    redacted = redact_parameters(parameters)
    canonical = {
        "apiContractId": api_contract_id,
        "httpMethod": method,
        "url": url,
        "parameters": redacted,
    }
    return {**canonical, "requestSha256": canonical_json_sha256(canonical)}


def assert_no_secret_value(payload: Any, secret_values: list[str]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    leaked = [secret for secret in secret_values if secret and secret in serialized]
    if leaked:
        raise ValueError("secret value leaked into request artifact")
