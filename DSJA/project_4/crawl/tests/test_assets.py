import json

import pandas as pd
import pytest

from p4_crawl.assets import build_asset_frontier, collect_pending_assets, is_linkareer_hosted


def test_asset_host_policy() -> None:
    assert is_linkareer_hosted("https://cdn.linkareer.com/a.png")
    assert is_linkareer_hosted("https://linkareer.com/a.png")
    assert not is_linkareer_hosted("https://linkareer.com.evil.example/a.png")
    assert not is_linkareer_hosted("http://linkareer.com/a.png")


def test_asset_frontier_preserves_field_lineage_and_period() -> None:
    posting = pd.DataFrame([{
        "sourcePostingId": "42",
        "recruitStartAt": "2024-05-17T00:00:00Z",
        "assetCandidatesJson": json.dumps([
            {"assetUrl": "https://cdn.linkareer.com/thumb.png", "assetType": "image", "sourceField": "activity.thumbnailImage"},
        ]),
    }])
    row = build_asset_frontier(posting).iloc[0]
    assert row["sourceField"] == "activity.thumbnailImage"
    assert row["periodMonth"] == "2024-05"


def test_asset_collection_rejects_missing_period_before_transport(tmp_path) -> None:
    frontier = pd.DataFrame([{
        "sourcePostingId": "42",
        "assetUrl": "https://cdn.linkareer.com/a.png",
        "assetType": "image",
        "sourceField": "activity.files",
        "periodMonth": None,
        "status": "PENDING",
        "externalAtsAsset": False,
    }])

    class Http:
        def get(self, *_args, **_kwargs):
            raise AssertionError("transport must not run")

    with pytest.raises(ValueError, match="missing periodMonth"):
        collect_pending_assets(frontier, Http(), tmp_path / "asset.jsonl")
