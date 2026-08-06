import pandas as pd

from p4.dedup.reposts import assign_repost_groups, title_similarity


def _frame():
    return pd.DataFrame(
        [
            {
                "postingId": "P1",
                "companyKey": "C1",
                "titleText": "데이터 분석 인턴 채용",
                "postedAt": "2026-01-01T00:00:00+09:00",
                "postingEligibleFlag": True,
            },
            {
                "postingId": "P2",
                "companyKey": "C1",
                "titleText": "데이터 분석 인턴 채용",
                "postedAt": "2026-02-15T00:00:00+09:00",
                "postingEligibleFlag": True,
            },
            {
                "postingId": "P3",
                "companyKey": "C1",
                "titleText": "데이터 분석 인턴 채용",
                "postedAt": "2026-05-01T00:00:00+09:00",
                "postingEligibleFlag": True,
            },
            {
                "postingId": "P4",
                "companyKey": "C2",
                "titleText": "데이터 분석 인턴 채용",
                "postedAt": "2026-02-01T00:00:00+09:00",
                "postingEligibleFlag": True,
            },
        ]
    )


def test_90_day_grouping_and_canonical_record_are_separate():
    result = assign_repost_groups(_frame()).set_index("postingId")
    assert result.loc["P1", "postingEligibleFlag"]
    assert result.loc["P2", "postingEligibleFlag"]
    assert result.loc["P1", "canonicalRecordFlag"]
    assert not result.loc["P2", "canonicalRecordFlag"]
    assert result.loc["P2", "canonicalPostingId"] == "P1"
    assert result.loc["P3", "canonicalPostingId"] == "P3"
    assert result.loc["P4", "canonicalPostingId"] == "P4"


def test_similarity_is_deterministic():
    assert title_similarity("AI 개발자", "AI 개발자") == 1.0
    assert title_similarity("AI 개발자", "재무 담당") < 0.5

