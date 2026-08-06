from __future__ import annotations

from dataclasses import dataclass


PIPELINE_VERSION = "0.1.0"
SUPPORTED_CONTRACT_VERSION = "2.1.0"


@dataclass(frozen=True)
class RuntimeVersions:
    pipeline_version: str = PIPELINE_VERSION
    supported_contract_version: str = SUPPORTED_CONTRACT_VERSION

