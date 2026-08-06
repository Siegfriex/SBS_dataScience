from __future__ import annotations

from dataclasses import dataclass


PIPELINE_VERSION = "0.1.0"
TARGET_CONTRACT_VERSION = "2.1.2"
SUPPORTED_CONTRACT_VERSION = None


@dataclass(frozen=True)
class RuntimeVersions:
    pipeline_version: str = PIPELINE_VERSION
    target_contract_version: str = TARGET_CONTRACT_VERSION
    supported_contract_version: str | None = SUPPORTED_CONTRACT_VERSION
