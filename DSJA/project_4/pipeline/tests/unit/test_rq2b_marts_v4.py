from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from p4.marts.rq2b import build_rq2b_marts


def _fixture() -> pd.DataFrame:
    common = {"periodMonth": "2025-01-01", "jobCohort": "coreAiIt", "sourceRole": "DUTY", "ncsEligibleFlag": True}
    rows = [
        {**common, "trackId": "T1", "chunkId": "C1", "mappingStatus": "ACCEPTED_SINGLE", "ncsUnitCode": "U1", "ncsLevel": 2, "ncsBand": "level1to2"},
        {**common, "trackId": "T1", "chunkId": "C2", "mappingStatus": "ACCEPTED_SINGLE", "ncsUnitCode": "U1", "ncsLevel": 2, "ncsBand": "level1to2"},
        {**common, "trackId": "T1", "chunkId": "C3", "mappingStatus": "ACCEPTED_MULTI", "ncsUnitCode": "U2", "ncsLevel": 6, "ncsBand": "level5to6"},
        {**common, "trackId": "T1", "chunkId": "C3", "mappingStatus": "ACCEPTED_MULTI", "ncsUnitCode": "U3", "ncsLevel": 8, "ncsBand": "level7to8"},
        {**common, "trackId": "T1", "chunkId": "C4", "mappingStatus": "ABSTAIN", "ncsUnitCode": None, "ncsLevel": None, "ncsBand": None},
        {**common, "trackId": "T1", "chunkId": "C5", "mappingStatus": "UNMAPPED", "ncsUnitCode": None, "ncsLevel": None, "ncsBand": None},
        {**common, "trackId": "T1", "chunkId": "C6", "mappingStatus": "OUT_OF_SCOPE", "ncsUnitCode": None, "ncsLevel": None, "ncsBand": None},
        {**common, "trackId": "T2", "chunkId": "C7", "mappingStatus": "ACCEPTED_SINGLE", "ncsUnitCode": "U4", "ncsLevel": 4, "ncsBand": "level3to4"},
        {**common, "sourceRole": "REQUIRED", "trackId": "T2", "chunkId": "R1", "mappingStatus": "UNMAPPED", "ncsUnitCode": None, "ncsLevel": None, "ncsBand": None},
    ]
    return pd.DataFrame(rows)


def _sort(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame.sort_values(columns).reset_index(drop=True)


def test_rq2b_formulas_role_separation_dedup_and_mentions():
    marts = build_rq2b_marts(_fixture())
    duty = marts["mapping_coverage"].loc[marts["mapping_coverage"]["sourceRole"].eq("DUTY")].iloc[0]
    assert duty["ncsEligibleChunkCount"] == 7
    assert duty["acceptedMappedChunkCount"] == 4
    assert duty["mappingCoverage"] == 4 / 7
    assert duty["acceptedMappedWeight"] == 3.0
    assert duty["advancedDutyShareAccepted"] == 1 / 3
    assert duty["advancedDutyShareEligibleLowerBound"] == 1 / 7
    assert duty["ncsLevelWeightedMedian"] == 4.0
    mention = marts["unit_mention_intensity"]
    assert mention.loc[(mention["trackId"] == "T1") & (mention["ncsUnitCode"] == "U1"), "unitMentionIntensity"].item() == 2
    required = marts["mapping_coverage"].loc[marts["mapping_coverage"]["sourceRole"].eq("REQUIRED")].iloc[0]
    assert required["mappingCoverage"] == 0.0


def test_python_and_sql_rq2b_marts_are_equal():
    marts = build_rq2b_marts(_fixture())
    connection = duckdb.connect(":memory:")
    connection.register("rq2b_mapping_input", marts["prepared"])
    sql_path = Path(__file__).parents[2] / "sql/rq2b_marts.sql"
    connection.execute(sql_path.read_text(encoding="utf-8"))
    sql_coverage = connection.execute("SELECT * FROM rq2b_mapping_coverage_mart").fetchdf()
    sql_bands = connection.execute("SELECT * FROM rq2b_band_distribution_mart").fetchdf()
    sql_mentions = connection.execute("SELECT * FROM rq2b_unit_mention_intensity_mart").fetchdf()
    connection.close()

    pd.testing.assert_frame_equal(
        _sort(marts["mapping_coverage"], ["periodMonth", "jobCohort", "sourceRole"]),
        _sort(sql_coverage, ["periodMonth", "jobCohort", "sourceRole"]),
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        _sort(marts["band_distribution"], ["periodMonth", "jobCohort", "sourceRole", "distributionCategory", "ncsBand"]),
        _sort(sql_bands, ["periodMonth", "jobCohort", "sourceRole", "distributionCategory", "ncsBand"]),
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        _sort(marts["unit_mention_intensity"], ["periodMonth", "jobCohort", "sourceRole", "trackId", "ncsUnitCode"]),
        _sort(sql_mentions, ["periodMonth", "jobCohort", "sourceRole", "trackId", "ncsUnitCode"]),
        check_dtype=False,
    )
