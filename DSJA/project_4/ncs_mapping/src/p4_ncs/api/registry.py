"""Read-only consumer for Agent 3's API contract registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ApiEndpointContract:
    api_contract_id: str
    provider: str
    base_url: str
    endpoint_path: str
    http_method: str
    semantic_role: str
    expected_content_types: tuple[str, ...]
    credential_env: str
    contract_status: str
    probe_status: str
    required_probe_cases: tuple[str, ...]

    @property
    def url(self) -> str:
        return f"{self.base_url.rstrip('/')}/{self.endpoint_path.lstrip('/')}"

    def as_contract_record(self, *, valid_from: str, parser_version: str) -> dict[str, Any]:
        return {
            "apiContractId": self.api_contract_id,
            "provider": self.provider,
            "baseUrl": self.base_url,
            "endpointPath": self.endpoint_path,
            "httpMethod": self.http_method,
            "contractVersion": "4.0",
            "expectedContentTypesJson": list(self.expected_content_types),
            "parameterSchemaJson": {},
            "contractStatus": self.contract_status,
            "observedSchemaSha256": None,
            "fixtureManifestSha256": None,
            "parserVersion": parser_version,
            "validFrom": valid_from,
            "validTo": None,
        }


@dataclass(frozen=True)
class ApiRegistry:
    registry_version: str
    base_contract_version: str
    semantic_addendum_version: str
    endpoints: tuple[ApiEndpointContract, ...]
    source_path: Path

    def by_id(self, api_contract_id: str) -> ApiEndpointContract:
        matches = [row for row in self.endpoints if row.api_contract_id == api_contract_id]
        if len(matches) != 1:
            raise KeyError(f"unknown or duplicate apiContractId: {api_contract_id}")
        return matches[0]


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[4] / "integration" / "API_CONTRACT_REGISTRY.yaml"


def load_api_registry(path: str | Path | None = None) -> ApiRegistry:
    source = Path(path).resolve() if path else default_registry_path()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    rows = payload.get("endpoints")
    if not isinstance(rows, list) or not rows:
        raise ValueError("API registry endpoints must be a non-empty list")
    endpoints: list[ApiEndpointContract] = []
    seen: set[str] = set()
    for position, row in enumerate(rows):
        required = {
            "apiContractId", "provider", "baseUrl", "endpointPath", "httpMethod",
            "semanticRole", "expectedContentTypes", "credentialEnv", "contractStatus",
            "probeStatus", "requiredProbeCases",
        }
        missing = required.difference(row)
        if missing:
            raise ValueError(f"endpoint {position} missing fields: {', '.join(sorted(missing))}")
        contract_id = str(row["apiContractId"])
        if contract_id in seen:
            raise ValueError(f"duplicate apiContractId: {contract_id}")
        seen.add(contract_id)
        if not str(row["baseUrl"]).startswith("https://"):
            raise ValueError(f"non-HTTPS endpoint: {contract_id}")
        if row["httpMethod"] not in {"GET", "POST"}:
            raise ValueError(f"unsupported method: {contract_id}")
        endpoints.append(ApiEndpointContract(
            api_contract_id=contract_id,
            provider=str(row["provider"]),
            base_url=str(row["baseUrl"]),
            endpoint_path=str(row["endpointPath"]),
            http_method=str(row["httpMethod"]),
            semantic_role=str(row["semanticRole"]),
            expected_content_types=tuple(map(str, row["expectedContentTypes"])),
            credential_env=str(row["credentialEnv"]),
            contract_status=str(row["contractStatus"]),
            probe_status=str(row["probeStatus"]),
            required_probe_cases=tuple(map(str, row["requiredProbeCases"])),
        ))
    return ApiRegistry(
        registry_version=str(payload["registryVersion"]),
        base_contract_version=str(payload["baseContractVersion"]),
        semantic_addendum_version=str(payload["semanticAddendumVersion"]),
        endpoints=tuple(endpoints),
        source_path=source,
    )
