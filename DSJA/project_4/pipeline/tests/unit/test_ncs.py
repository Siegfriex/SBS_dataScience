import pytest

from p4.ncs.bands import ncs_band
from p4.ncs.mapping import dictionary_candidates, rank_candidates


@pytest.mark.parametrize(
    "level,expected",
    [
        (1, "level1to2"),
        (2, "level1to2"),
        (3, "level3to4"),
        (4, "level3to4"),
        (5, "level5to6"),
        (6, "level5to6"),
        (7, "level7to8"),
        (8, "level7to8"),
    ],
)
def test_ncs_bands(level, expected):
    assert ncs_band(level) == expected


def test_ncs_band_rejects_out_of_range():
    with pytest.raises(ValueError):
        ncs_band(0)
    with pytest.raises(ValueError):
        ncs_band(9)


def test_mapping_priority_precedes_score():
    rows = rank_candidates(
        "SEC_1",
        [
            {
                "ncsUnitCode": "U2",
                "evidenceText": "문장 근거 2",
                "mappingBasis": "semanticMatch",
                "matchScore": 0.99,
            },
            {
                "ncsUnitCode": "U1",
                "evidenceText": "문장 근거 1",
                "mappingBasis": "ncsPerformanceCriteria",
                "matchScore": 0.80,
            },
        ],
        "map-v1",
    )
    assert rows[0]["ncsUnitCode"] == "U1"
    assert rows[0]["selectedFlag"] is True
    assert rows[1]["selectedFlag"] is False


def test_tool_name_only_mapping_is_rejected():
    with pytest.raises(ValueError, match="tool-name-only"):
        rank_candidates(
            "SEC_1",
            [
                {
                    "ncsUnitCode": "U1",
                    "evidenceText": "Python",
                    "mappingBasis": "dictionaryRule",
                    "matchScore": 0.8,
                    "toolNameOnly": True,
                }
            ],
            "map-v1",
        )


def test_dictionary_mapping_preserves_evidence_and_version():
    rows = dictionary_candidates(
        "SEC_1",
        "데이터 품질을 점검하고 분석 보고서를 작성한다",
        [
            {
                "ncsUnitCode": "200101",
                "phrases": ["데이터 품질", "분석 보고서"],
                "matchScore": 0.75,
            }
        ],
        "map-v1",
    )
    assert rows[0]["mappingBasis"] == "dictionaryRule"
    assert rows[0]["mappingVersion"] == "map-v1"
    assert "데이터 품질" in rows[0]["evidenceText"]

