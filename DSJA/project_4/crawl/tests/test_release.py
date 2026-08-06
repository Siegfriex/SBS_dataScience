from __future__ import annotations

import json
from pathlib import Path

from p4_crawl.config import RunConfig
from p4_crawl.manifests import load_jsonl, verify_checksum_file
from p4_crawl.release import build_observed_input_package


def test_observed_package_recomputes_real_counts(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = RunConfig(project_root=project_root)
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
