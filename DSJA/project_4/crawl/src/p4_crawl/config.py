"""Collector configuration and repository path discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

AGENT_ID = "P4-A1-SOURCE"
AGENT_NAME = "P4 Source Acquisition & Coverage Engineer"
CONTRACT_VERSION = "2.1.2"
BASELINE_RELEASE_ID = "CRAWL_20260806_03"
GRAPHQL_URL = "https://api.linkareer.com/graphql"
TARGET_MONTHS = tuple(
    f"{year:04d}-{month:02d}"
    for year in range(2020, 2027)
    for month in range(1, 13)
    if (year, month) <= (2026, 7)
)


def locate_project_root(start: Path | None = None) -> Path:
    """Locate ``DSJA/project_4`` without relying on the notebook cwd."""

    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "crawl").is_dir() and (candidate / "shared").is_dir():
            return candidate
        nested = candidate / "DSJA" / "project_4"
        if (nested / "crawl").is_dir() and (nested / "shared").is_dir():
            return nested
    raise RuntimeError("Could not locate DSJA/project_4 root")


@dataclass(frozen=True)
class RunConfig:
    project_root: Path
    run_id: str = "E2E_20260806_RESUME_01"
    phase: str = "restore"
    run_mode: str = "observed-dev"
    contract_version: str = CONTRACT_VERSION
    crawl_release_id: str = BASELINE_RELEASE_ID
    data_version: str = "observed-dev-20260806.1"
    as_of_date: str = "2026-08-06"
    random_seed: int = 42
    execute_live: bool = False

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "RunConfig":
        return cls(
            project_root=(project_root or locate_project_root()),
            run_id=os.getenv("P4_A1_RUN_ID", "E2E_20260806_RESUME_01"),
            phase=os.getenv("P4_A1_PHASE", "restore").strip().lower(),
            run_mode=os.getenv("P4_RUN_MODE", "observed-dev"),
            crawl_release_id=os.getenv("P4_CRAWL_RELEASE_ID", BASELINE_RELEASE_ID),
            data_version=os.getenv("P4_DATA_VERSION", "observed-dev-20260806.1"),
            as_of_date=os.getenv("P4_AS_OF_DATE", "2026-08-06"),
            random_seed=int(os.getenv("P4_RANDOM_SEED", "42")),
            execute_live=os.getenv("P4_A1_EXECUTE_LIVE", "0") == "1",
        )

    @property
    def crawl_root(self) -> Path:
        return self.project_root / "crawl"

    @property
    def release_root(self) -> Path:
        return self.crawl_root / "releases" / self.crawl_release_id

    @property
    def run_root(self) -> Path:
        return self.crawl_root / "runs" / self.run_id

    @property
    def raw_root(self) -> Path:
        return self.crawl_root / "data" / "raw" / "linkareer"

    def ensure_run_layout(self) -> None:
        for rel in ("coverage", "state", "manifests", "reports"):
            (self.run_root / rel).mkdir(parents=True, exist_ok=True)

    def require_live(self) -> None:
        if not self.execute_live:
            raise RuntimeError("LIVE_COLLECTION_DISABLED: pass --execute-live explicitly")
        if self.run_mode != "production":
            raise RuntimeError("LIVE_COLLECTION_DISABLED: RUN_MODE must be production")


assert len(TARGET_MONTHS) == 79
