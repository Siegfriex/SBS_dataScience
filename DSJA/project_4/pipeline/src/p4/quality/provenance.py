from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DataProvenance(StrEnum):
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
            self.provenance == DataProvenance.CRAWL_RELEASE
            and self.contract_version
            and self.crawl_release_id
            and self.crawl_release_id.startswith("CRAWL_")
        )

    def require_empirical(self) -> None:
        if not self.empirical_analysis_allowed:
            raise ValueError("empirical analysis requires a canonical contract and immutable CRAWL_ release provenance")

