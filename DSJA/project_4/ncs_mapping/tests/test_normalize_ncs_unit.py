from pathlib import Path

import pandas as pd
import pytest

from p4_ncs.ingest.ncs_unit_source import NcsUnitSourceMeta
from p4_ncs.normalize.ncs_unit import normalize_ncs_unit

FIXTURE = Path(__file__).parent / "fixtures" / "ncsUnit_sample.csv"


@pytest.fixture
def raw_df():
    df = pd.read_csv(FIXTURE, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    return df


@pytest.fixture
def meta():
    return NcsUnitSourceMeta(
        release_root=FIXTURE.parent,
        raw_path=FIXTURE,
        raw_sha256="test-sha256",
        checksum_verified=False,
        encoding="utf-8",
    )


def test_row_count_preserved(raw_df, meta):
    out, _ = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    assert len(out) == len(raw_df) == 6


def test_hierarchy_codes_parsed(raw_df, meta):
    out, unparsed = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    row = out[out["ncsUnitCode"] == "1907010101_16v1"].iloc[0]
    assert row["majorCode"] == "19"
    assert row["middleCode"] == "07"
    assert row["minorCode"] == "01"
    assert row["subCode"] == "01"


def test_band_mapping(raw_df, meta):
    out, _ = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    bands = dict(zip(out["ncsUnitCode"], out["ncsBand"]))
    assert bands["0101010101_17v2"] == "level7to8"
    assert bands["0101010102_17v2"] == "level5to6"
    assert bands["1907010101_16v1"] == "level5to6"
    assert bands["1907010102_16v1"] == "level3to4"
    assert bands["2001010101_20v1"] == "level7to8"


def test_malformed_code_flagged_not_dropped(raw_df, meta):
    out, unparsed = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    assert "BADCODE_NOVERSION" in unparsed
    row = out[out["ncsUnitCode"] == "BADCODE_NOVERSION"].iloc[0]
    assert pd.isna(row["majorCode"])
    assert row["ncsUnitName"] == "잘못된 코드 샘플"


def test_hierarchy_names_are_null_not_fabricated(raw_df, meta):
    out, _ = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    for col in ("majorName", "middleName", "minorName", "subName"):
        assert out[col].isna().all()


def test_lineage_fields_populated(raw_df, meta):
    out, _ = normalize_ncs_unit(raw_df, meta, "test-dataset", "2026-08-06", "2.1.2")
    assert (out["rawSha256"] == "test-sha256").all()
    assert (out["contractVersion"] == "2.1.2").all()
    assert (out["sourceDataset"] == "test-dataset").all()
