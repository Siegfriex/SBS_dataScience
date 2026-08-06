from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

from p4.common.keys import normalize, normalize_company


class KeyStrategy(ABC):
    strategy_name: str
    contract_version: str

    @abstractmethod
    def make(self, object_type: str, *parts: Any) -> str:
        raise NotImplementedError


class Sha1LegacyStrategy(KeyStrategy):
    strategy_name = "sha1Legacy"
    contract_version = "dataset-spec-v2.0.0"

    @staticmethod
    def _digest(*parts: Any, length: int) -> str:
        payload = "|".join(normalize(part) for part in parts).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:length]

    def make(self, object_type: str, *parts: Any) -> str:
        if object_type == "postingId":
            return "lk_" + self._digest(*parts[:2], length=16)
        if object_type == "rawPostingId":
            return self._digest(*parts[:3], length=20)
        if object_type == "trackId":
            return f"{parts[0]}#t{int(parts[1]):02d}"
        if object_type == "sectionId":
            return f"{parts[0]}#s{int(parts[1]):02d}"
        if object_type == "requirementId":
            return self._digest(*parts[:3], length=20)
        if object_type == "assetId":
            return self._digest(parts[0], length=20)
        if object_type == "ocrId":
            return self._digest(*parts[:4], length=20)
        if object_type == "matchId":
            evidence_hash = self._digest(parts[3], length=8)
            return self._digest(*parts[:3], evidence_hash, length=20)
        if object_type == "duplicateGroupId":
            posting_ids = sorted(str(value) for value in parts[0])
            return "dg_" + self._digest(posting_ids[0], length=16)
        if object_type == "companyKey":
            return "co_" + self._digest(normalize_company(parts[0]), length=12)
        if object_type == "metricId":
            return self._digest(*parts, length=20)
        raise KeyError(f"unsupported legacy key type: {object_type}")


@dataclass(frozen=True)
class CanonicalContractStrategy(KeyStrategy):
    contract_version: str
    key_contract: dict[str, Any]
    strategy_name: str = "canonicalContract"

    def __post_init__(self) -> None:
        if not self.contract_version:
            raise ValueError("canonical strategy requires contract_version")
        if not self.key_contract.get("algorithm"):
            raise ValueError("canonical strategy requires algorithm from the contract")
        if self.key_contract["algorithm"].casefold().replace("-", "") not in {"sha1", "sha256"}:
            raise ValueError("contract key algorithm must be sha1 or sha256")
        if not self.key_contract.get("rules") and not self.key_contract.get("truncationHexChars"):
            raise ValueError("canonical strategy requires rules or canonical truncation metadata")

    @classmethod
    def from_contract(cls, contract: dict[str, Any]) -> "CanonicalContractStrategy":
        version = str(contract.get("contractVersion") or "")
        key_contract = contract.get("rules", {}).get("keyContract", {})
        return cls(contract_version=version, key_contract=key_contract)

    def make(self, object_type: str, *parts: Any) -> str:
        rules = self.key_contract.get("rules")
        if rules:
            if object_type not in rules:
                raise KeyError(f"contract has no key rule for {object_type}")
            rule = rules[object_type]
        else:
            prefixes = {
                "postingId": "PST_",
                "rawPostingId": "RAW_",
                "trackId": "TRK_",
                "sectionId": "SEC_",
                "requirementId": "REQ_",
                "matchId": "NMT_",
            }
            expected_parts = {
                "postingId": 2,
                "rawPostingId": 3,
                "trackId": 2,
                "sectionId": 2,
                "requirementId": 3,
                "matchId": 4,
            }
            if object_type not in prefixes:
                raise KeyError(f"contract has no key rule for {object_type}")
            if len(parts) != expected_parts[object_type]:
                raise ValueError(f"{object_type} requires {expected_parts[object_type]} ordered inputs")
            rule = {"prefix": prefixes[object_type], "length": self.key_contract["truncationHexChars"]}
        algorithm = self.key_contract["algorithm"].casefold().replace("-", "")
        separator = str(self.key_contract.get("separator", "|"))
        encoding = str(self.key_contract.get("encoding", "UTF-8"))
        payload = separator.join(str(value) for value in parts).encode(encoding)
        digest = getattr(hashlib, algorithm)(payload).hexdigest()
        length = int(rule.get("length", len(digest)))
        prefix = str(rule.get("prefix", ""))
        return f"{prefix}{digest[:length]}"


def build_migration_map(
    object_type: str,
    samples: Iterable[tuple[Any, ...]],
    legacy: KeyStrategy,
    canonical: KeyStrategy,
) -> list[dict[str, str]]:
    rows = []
    seen: dict[str, tuple[Any, ...]] = {}
    for parts in samples:
        canonical_key = canonical.make(object_type, *parts)
        if canonical_key in seen and seen[canonical_key] != parts:
            raise ValueError(f"canonical key collision in migration sample: {canonical_key}")
        seen[canonical_key] = parts
        rows.append(
            {
                "objectType": object_type,
                "legacyKey": legacy.make(object_type, *parts),
                "canonicalKey": canonical_key,
                "contractVersion": canonical.contract_version,
            }
        )
    return rows
