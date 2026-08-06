"""Alias dictionary: job-posting-language terms -> candidate NCS subCode(s).

This is a seed/skeleton, not an exhaustive dictionary -- it exists so the
retrieval/mapping interfaces have something concrete to run against before
real Agent 2 duty input arrives. Every entry must point at an ncsSubCode that
actually exists in data/processed/coreAiItCodeSet.parquet.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


def load_alias_dictionary(config_path: Path) -> pd.DataFrame:
    with open(config_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return pd.DataFrame(doc["aliases"])


def validate_alias_dictionary(alias_df: pd.DataFrame, valid_sub_codes: set[str]) -> list[str]:
    """Return alias rows whose ncsSubCode is not in the known codeset (should be empty)."""
    bad = alias_df.loc[~alias_df["ncsSubCode"].isin(valid_sub_codes), "alias"].tolist()
    return bad
