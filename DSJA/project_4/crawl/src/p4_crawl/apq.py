"""Persisted-query request construction with registry-owned hashes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import GRAPHQL_URL
from .policy import PolicyHttpClient
from .query_registry import QueryRegistry
from .storage import canonical_json, sha256_bytes


def apq_params(operation_name: str, query_hash: str, variables: dict) -> dict[str, str]:
    return {
        "operationName": operation_name,
        "variables": canonical_json(variables),
        "extensions": canonical_json({"persistedQuery": {"version": 1, "sha256Hash": query_hash}}),
    }


@dataclass
class APQResult:
    payload: dict[str, Any]
    operation_name: str
    query_hash: str
    variables: dict
    response: Any


class APQClient:
    def __init__(self, http: PolicyHttpClient, registry: QueryRegistry, endpoint: str = GRAPHQL_URL):
        self.http = http
        self.registry = registry
        self.endpoint = endpoint

    def fetch(self, operation_name: str, variables: dict, *, period: str | None = None) -> APQResult:
        definition = self.registry.require(operation_name)
        if definition.transport_type != "apq_get" or definition.http_method != "GET":
            raise RuntimeError(f"Unsupported registered transport for {operation_name}")
        response = self.http.get(
            self.endpoint,
            params=apq_params(operation_name, definition.sha256_hash, variables),
            _p4_context={
                "entityType": "index",
                "period": period,
                "operationName": operation_name,
                "variablesHash": sha256_bytes(canonical_json(variables).encode("utf-8")),
                "expectedContentTypes": ["application/json"],
            } if period else {},
        )
        if response.status_code != 200:
            raise RuntimeError(f"APQ HTTP {response.status_code}")
        try:
            payload = response.json()
        except AttributeError:
            payload = json.loads(response.content)
        if payload.get("errors"):
            raise RuntimeError(f"APQ GraphQL errors: {payload['errors'][:1]}")
        data = payload.get("data")
        required_key = "activityCalendarEntries" if operation_name == "CalendarScreen_ActivityCalendarEntries" else "activities"
        if not isinstance(data, dict) or required_key not in data:
            self.http.health.schema_drift(f"{operation_name} missing data.{required_key}")
            self.http.kill_switch.check()
        return APQResult(payload, operation_name, definition.sha256_hash, variables, response)
