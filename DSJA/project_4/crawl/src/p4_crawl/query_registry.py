"""Validated loading of APQ operation hashes from the registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class QueryDefinition:
    operation_name: str
    sha256_hash: str
    transport_type: str
    http_method: str
    verification_status: str


class QueryRegistry:
    def __init__(self, definitions: dict[str, QueryDefinition]):
        self._definitions = definitions

    @classmethod
    def load(cls, path: Path) -> "QueryRegistry":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        definitions: dict[str, QueryDefinition] = {}
        for row in payload.get("queries", []):
            name = str(row.get("operationName") or "")
            digest = str(row.get("sha256Hash") or "")
            if not name or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                raise ValueError(f"Invalid APQ registry row for {name or '<missing>'}")
            if name in definitions:
                raise ValueError(f"Duplicate APQ operation: {name}")
            if not row.get("activeFlag"):
                continue
            definitions[name] = QueryDefinition(
                operation_name=name,
                sha256_hash=digest.lower(),
                transport_type=str(row.get("transportType") or ""),
                http_method=str(row.get("httpMethod") or "").upper(),
                verification_status=str(row.get("verificationStatus") or ""),
            )
        if not definitions:
            raise ValueError("No active APQ query definitions")
        return cls(definitions)

    def require(self, operation_name: str) -> QueryDefinition:
        try:
            definition = self._definitions[operation_name]
        except KeyError as exc:
            raise KeyError(f"APQ operation not registered: {operation_name}") from exc
        if definition.verification_status != "verified":
            raise RuntimeError(f"APQ operation is not verified: {operation_name}")
        return definition

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))
