import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd


PIPELINE_ROOT = Path(__file__).resolve().parents[2]


def test_fixture_pipeline_builds_valid_local_artifacts():
    subprocess.run([sys.executable, "scripts/run_fixture_pipeline.py"], cwd=PIPELINE_ROOT, check=True, capture_output=True)
    summary = json.loads((PIPELINE_ROOT / "runs/fixture_pipeline_summary.json").read_text(encoding="utf-8"))
    assert summary["dataProvenance"] == "generated_structural_fixture"
    assert summary["empiricalAnalysisAllowed"] is False
    assert summary["rows"]["raw"] == 6
    assert summary["rows"]["excludedPostings"] == 1
    assert summary["postingMartQuality"]["passed"] is True
    posting = pd.read_parquet(PIPELINE_ROOT / "data/marts/postingAnalysisMart.parquet")
    time_series = pd.read_parquet(PIPELINE_ROOT / "data/marts/timeSeriesMart.parquet")
    assert posting["trackId"].duplicated().sum() == 0
    assert time_series["metricId"].duplicated().sum() == 0
    assert posting["highDemandScore"].isna().all()
    connection = duckdb.connect(str(PIPELINE_ROOT / "data/warehouse/p4.duckdb"), read_only=True)
    try:
        assert connection.execute("SELECT COUNT(*) FROM mart.posting_analysis").fetchone()[0] == len(posting)
    finally:
        connection.close()
