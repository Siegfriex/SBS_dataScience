from __future__ import annotations

import json
import os
from pathlib import Path

from p4_crawl.config import RunConfig
from p4_crawl.manifests import load_jsonl, verify_checksum_file
from p4_crawl.release import build_observed_input_package
from p4_crawl.observed import _safe_url, classify_agent2_validator_quality


def test_observed_package_recomputes_real_counts(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    runtime_raw = os.getenv("P4_CRAWL_RAW_SOURCE_ROOT")
    if not runtime_raw and not (project_root / "crawl/data/raw").is_dir():
        import pytest
        pytest.skip("29 raw SSR runtime source is not mounted")
    config = RunConfig(project_root=project_root, raw_source_base=Path(runtime_raw) if runtime_raw else None)
    handoff = build_observed_input_package(config, tmp_path / "observed")
    assert handoff["postingRows"] == 137
    assert handoff["rawHtmlRows"] == 29
    assert handoff["assetRows"] == 0
    assert handoff["ncsUnitRows"] == 13442
    assert handoff["fullCorpus"] is False
    assert handoff["empiricalAnalysisAllowed"] is False
    assert handoff["promotionAllowed"] is False
    raw_rows = load_jsonl(tmp_path / "observed" / "raw_detail_manifest.jsonl")
    assert len(raw_rows) == 29
    assert all(not Path(row["rawPath"]).is_absolute() for row in raw_rows)
    assert all(row["rawPath"].startswith("data/raw/linkareer/detail/") for row in raw_rows)
    assert verify_checksum_file(tmp_path / "observed" / "CHECKSUMS.sha256", tmp_path / "observed")["ok"]
    gaps = json.loads((tmp_path / "observed" / "known_gaps.json").read_text())
    assert len(gaps["rejectedNonRawDetailReferences"]) == 3


def test_observed_url_sanitizer_drops_contact_strings_and_queries() -> None:
    assert _safe_url("business@example.com") is None
    assert _safe_url("mailto:person@example.com") is None
    assert _safe_url("https://jobs.example.com/apply?token=secret#section") == "https://jobs.example.com/apply"


def test_agent2_validator_quality_is_fail_closed() -> None:
    assert classify_agent2_validator_quality({"executed": False, "status": "MISSING"}) == "NOT_EVALUATED"
    assert classify_agent2_validator_quality({"executed": True, "status": "EXECUTED"}) == "PASS"
    assert classify_agent2_validator_quality({"executed": True, "status": "EXECUTION_FAILED"}) == "FAIL"
