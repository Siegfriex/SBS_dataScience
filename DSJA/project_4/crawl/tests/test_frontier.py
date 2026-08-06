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
