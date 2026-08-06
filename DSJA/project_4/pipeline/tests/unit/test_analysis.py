import pandas as pd
import pytest

from p4.analysis.segmented import AnalysisSpec, fit_monthly_hac, prepare_segmented_design
from p4.quality.provenance import DataProvenance, ProvenanceContext


def test_segmented_design_uses_2023_level_and_slope_terms():
    frame = pd.DataFrame(
        {
            "periodMonth": ["2022-12-01", "2023-01-01", "2023-02-01"],
            "outcome": [0.1, 0.2, 0.3],
        }
    )
    design = prepare_segmented_design(frame)
    assert design["Post2023"].tolist() == [0, 1, 1]
    assert design["TimeAfter2023"].tolist() == [0, 0, 1]
    assert design["monthOfYear"].tolist() == ["12", "1", "2"]


def test_empirical_fit_rejects_fixture_provenance():
    frame = pd.DataFrame(
        {
            "periodMonth": pd.date_range("2020-01-01", periods=36, freq="MS"),
            "outcome": [0.1] * 36,
        }
    )
    provenance = ProvenanceContext(DataProvenance.SYNTHETIC, None, None, "fixture-v1")
    with pytest.raises(ValueError, match="requires contractVersion"):
        fit_monthly_hac(frame, AnalysisSpec("outcome"), provenance=provenance)


def test_empirical_fit_rejects_unstructured_provenance_string():
    frame = pd.DataFrame(
        {"periodMonth": pd.date_range("2020-01-01", periods=36, freq="MS"), "outcome": [0.1] * 36}
    )
    with pytest.raises(TypeError, match="ProvenanceContext"):
        fit_monthly_hac(frame, AnalysisSpec("outcome"), provenance="crawl_release")
