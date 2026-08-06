from __future__ import annotations

import pandas as pd

from p4_crawl.frontier import build_detail_frontier


def test_frontier_resume_recovers_fetching_and_preserves_attempts() -> None:
    previous = pd.DataFrame(
        [
            {
                "sourcePostingId": "10",
                "status": "FETCHING",
                "attempts": 2,
                "lastError": None,
                "updatedAt": "old",
            }
        ]
    )
    frontier = build_detail_frontier({"10", "11"}, {}, previous=previous).set_index("sourcePostingId")
    assert frontier.loc["10", "status"] == "RETRY"
    assert frontier.loc["10", "attempts"] == 2
    assert frontier.loc["11", "status"] == "PENDING"


def test_equal_logical_inputs_produce_equal_frontier_content() -> None:
    raw = {
        "10": {
            "httpStatus": 200,
            "contentSha256": "a" * 64,
            "rawPath": "data/raw/10.html.gz",
            "bytes": 10,
            "fetchedAt": "2026-08-06T00:00:00Z",
        }
    }
    first = build_detail_frontier({"10", "11"}, raw)
    second = build_detail_frontier({"10", "11"}, raw)
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[first["sourcePostingId"] == "11", "updatedAt"].item() == ""
