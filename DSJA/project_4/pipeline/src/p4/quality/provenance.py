from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from p4.common.versions import SUPPORTED_CONTRACT_VERSION

CANONICAL_CONTRACT_VERSION = SUPPORTED_CONTRACT_VERSION
PRODUCTION_PROVENANCE_FIELDS = (
    "contractVersion",
    "crawlReleaseId",
    "dataVersion",
    "dataProvenance",
)


class DataProvenance(StrEnum):
    EMPIRICAL = "EMPIRICAL"
    CRAWL_RELEASE = "crawl_release"
    GENERATED_STRUCTURAL_FIXTURE = "generated_structural_fixture"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class ProvenanceContext:
    provenance: DataProvenance
    contract_version: str | None
    crawl_release_id: str | None
    data_version: str

    @property
    def empirical_analysis_allowed(self) -> bool:
        return bool(
            self.provenance == DataProvenance.EMPIRICAL
            and self.contract_version == CANONICAL_CONTRACT_VERSION
            and self.crawl_release_id
            and self.crawl_release_id.startswith("CRAWL_")
            and self.data_version
        )

    def require_empirical(self) -> None:
        if not self.empirical_analysis_allowed:
            raise ValueError(
                "empirical analysis requires contractVersion=2.1.2, an immutable CRAWL_ release, "
                "a non-empty dataVersion, and dataProvenance=EMPIRICAL"
            )


def require_production_provenance(payload: Mapping[str, Any] | ProvenanceContext | None) -> dict[str, str]:
    """Validate the fail-closed provenance envelope used for canonical mart writes."""
    if isinstance(payload, ProvenanceContext):
        values: Mapping[str, Any] = {
            "contractVersion": payload.contract_version,
            "crawlReleaseId": payload.crawl_release_id,
            "dataVersion": payload.data_version,
            "dataProvenance": payload.provenance.value,
        }
    elif isinstance(payload, Mapping):
        values = payload
    else:
        values = {}

    missing = [
        field
        for field in PRODUCTION_PROVENANCE_FIELDS
        if values.get(field) is None or not str(values.get(field)).strip()
    ]
    if missing:
        raise ValueError(f"production mart write missing provenance fields: {', '.join(missing)}")

    normalized = {field: str(values[field]).strip() for field in PRODUCTION_PROVENANCE_FIELDS}
    if normalized["contractVersion"] != CANONICAL_CONTRACT_VERSION:
        raise ValueError(f"production mart write requires contractVersion={CANONICAL_CONTRACT_VERSION}")
    if not normalized["crawlReleaseId"].startswith("CRAWL_"):
        raise ValueError("production mart write requires an immutable CRAWL_ release id")
    if normalized["dataProvenance"] != DataProvenance.EMPIRICAL.value:
        raise ValueError("production mart write requires dataProvenance=EMPIRICAL")
    return normalized
