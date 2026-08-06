"""Minimal probe client with network disabled unless explicitly injected."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from p4_ncs.api.parsers import ParsedApiResponse, parse_ncs_xml, parse_work24
from p4_ncs.api.redaction import assert_no_secret_value, canonical_json_sha256, redacted_request_manifest
from p4_ncs.api.registry import ApiEndpointContract


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProbeOutcome:
    manifest: dict[str, Any]
    parsed: ParsedApiResponse | None


class MinimalProbeClient:
    """A guarded client. Network execution requires an explicit audited transport."""

    def __init__(self, *, network_enabled: bool = False, transport: Any | None = None):
        self.network_enabled = network_enabled
        self.transport = transport

    def probe(
        self,
        contract: ApiEndpointContract,
        *,
        probe_case: str,
        parameters: Mapping[str, Any],
        credential: str | None = None,
    ) -> ProbeOutcome:
        started = _now()
        injected = credential if credential is not None else os.environ.get(contract.credential_env)
        runtime_params = dict(parameters)
        if injected:
            runtime_params["serviceKey" if contract.provider == "NCS_OPENAPI" else "authKey"] = injected
        request = redacted_request_manifest(
            api_contract_id=contract.api_contract_id,
            method=contract.http_method,
            url=contract.url,
            parameters=runtime_params,
        )
        assert_no_secret_value(request, [injected or ""])
        base = {
            "apiProbeRunId": f"APR_{request['requestSha256'][:20]}",
            "apiContractId": contract.api_contract_id,
            "probeCase": probe_case,
            "requestSha256": request["requestSha256"],
            "requestParametersRedactedJson": request["parameters"],
            "httpStatus": None,
            "contentType": None,
            "responseClass": "AUTH_ERROR" if not injected else "SERVER_ERROR",
            "rawResponsePath": None,
            "rawResponseSha256": None,
            "observedSchemaSha256": None,
            "startedAt": started,
            "completedAt": _now(),
            "status": "NOT_EVALUATED",
        }
        if not injected or not self.network_enabled:
            return ProbeOutcome(base, None)
        if self.transport is None:
            raise RuntimeError("network_enabled requires an explicit audited transport")
        response = self.transport.request(
            contract.http_method, contract.url, params=runtime_params, timeout=15.0
        )
        body = response.text
        content_type = response.headers.get("content-type", "")
        parsed = parse_ncs_xml(body) if contract.provider == "NCS_OPENAPI" else parse_work24(body, content_type)
        manifest = {
            **base,
            "httpStatus": int(response.status_code),
            "contentType": content_type,
            "responseClass": parsed.response_class,
            "rawResponseSha256": canonical_json_sha256({"body": body}),
            "observedSchemaSha256": parsed.observed_schema_sha256,
            "completedAt": _now(),
            "status": "PASS" if parsed.response_class in {"SUCCESS", "EMPTY_VALID"} else "PASS_WITH_FINDINGS",
        }
        assert_no_secret_value(manifest, [injected])
        return ProbeOutcome(manifest, parsed)
