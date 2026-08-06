from __future__ import annotations

from pathlib import Path

from p4_crawl.query_registry import QueryRegistry


def test_query_registry_loads_verified_apq_hashes() -> None:
    path = Path(__file__).resolve().parents[1] / "configs" / "queryRegistry.yaml"
    registry = QueryRegistry.load(path)
    entries = registry.require("CalendarScreen_ActivityCalendarEntries")
    total = registry.require("CalendarScreen_Activities")
    assert len(entries.sha256_hash) == 64
    assert len(total.sha256_hash) == 64
    assert entries.sha256_hash != total.sha256_hash
