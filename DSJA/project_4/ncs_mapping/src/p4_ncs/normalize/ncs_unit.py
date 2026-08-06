"""Normalize the raw NCS 능력단위 (competency unit) source into the Phase B schema.

Raw source columns: 분류번호 (e.g. "0101010101_17v2"), 명칭, 수준, 훈련시간.
The 10-digit prefix of 분류번호 encodes major/middle/minor/sub codes (2 digits
each) followed by a 2-digit unit sequence, then an underscore-separated
version tag. Only the leaf unit name is present in the source -- there is no
major/middle/minor/sub NAME column, so those name fields stay null until a
separate NCS classification reference table is sourced (see
docs/NCS_HIERARCHY_NAME_GAP.md).
"""
from __future__ import annotations

import re

import pandas as pd

from p4_ncs.ingest.ncs_unit_source import NcsUnitSourceMeta

_CODE_PATTERN = re.compile(r"^(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})_(\w+)$")

_BAND_BY_LEVEL = {
    1: "level1to2", 2: "level1to2",
    3: "level3to4", 4: "level3to4",
    5: "level5to6", 6: "level5to6",
    7: "level7to8", 8: "level7to8",
}


def _split_code(code: str) -> tuple[str | None, str | None, str | None, str | None]:
    m = _CODE_PATTERN.match(code)
    if not m:
        return None, None, None, None
    major, middle, minor, sub, _unit_seq, _version = m.groups()
    return major, middle, minor, sub


def normalize_ncs_unit(
    raw_df: pd.DataFrame,
    meta: NcsUnitSourceMeta,
    source_dataset: str,
    ncs_source_version: str,
    contract_version: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Return (normalized_df, unparsed_codes).

    unparsed_codes lists any ncsUnitCode that did not match the expected
    10-digit + version-tag pattern, for quality review -- they are still
    carried through with null hierarchy codes rather than dropped.
    """
    split = raw_df["분류번호"].map(_split_code)
    major, middle, minor, sub = zip(*split) if len(split) else ((), (), (), ())

    unparsed_codes = raw_df.loc[[m is None for m in major], "분류번호"].tolist()

    out = pd.DataFrame({
        "ncsUnitCode": raw_df["분류번호"],
        "ncsUnitName": raw_df["명칭"],
        "ncsLevel": raw_df["수준"].astype("Int64"),
        "ncsBand": raw_df["수준"].map(_BAND_BY_LEVEL),
        "majorCode": pd.array(major, dtype="string"),
        "majorName": pd.array([pd.NA] * len(raw_df), dtype="string"),
        "middleCode": pd.array(middle, dtype="string"),
        "middleName": pd.array([pd.NA] * len(raw_df), dtype="string"),
        "minorCode": pd.array(minor, dtype="string"),
        "minorName": pd.array([pd.NA] * len(raw_df), dtype="string"),
        "subCode": pd.array(sub, dtype="string"),
        "subName": pd.array([pd.NA] * len(raw_df), dtype="string"),
        "trainingHours": raw_df["훈련시간"].astype("Int64"),
        "sourceDataset": source_dataset,
        "sourceVersion": ncs_source_version,
        "rawSha256": meta.raw_sha256,
        "contractVersion": contract_version,
        "ncsSourceVersion": ncs_source_version,
    })
    return out, unparsed_codes
