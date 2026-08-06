"""Build the core AI/IT NCS sub-classification (세분류) codeset draft.

Granularity is ncsSubCode (8-digit major+middle+minor+sub prefix), not the
leaf ncsUnitCode, because the codeset is meant to gate mapping candidates at
the sub-classification level. The source has no official 세분류명 (sub-class
name) column, so `ncsSubName` here is a DERIVED label (the name of the first
constituent unit in that sub-code group, in ncsUnitCode sort order) -- it is
explicitly not the authoritative NCS sub-classification name and is flagged
as such via `subNameIsDerived=True` on every row.
"""
from __future__ import annotations

import pandas as pd

CODESET_VERSION = "core-ai-it-v0.1"

# Empirically identified from the normalized data (see docs/CORE_AI_IT_CODESET_DECISION.md):
# major=20 is 정보통신(ICT); its three middle groups split into 01=정보기술, 02=통신, 03=방송.
_ICT_MAJOR = "20"
_INCLUDED_MIDDLE = {"01": "정보기술 -- SW개발/IT운영/정보보호/AI/블록체인/데이터 핵심 IT 직무"}
_REVIEW_ONLY_MIDDLE = {
    "02": "통신 -- 통신망/설비 구축 인프라 중심, 소프트웨어·AI 직무 매핑과 결이 다름",
    "03": "방송 -- 방송 설비/서비스 기획 중심, 소프트웨어·AI 직무 매핑과 결이 다름",
}

_CROSS_MAJOR_AI_KEYWORDS = [
    "인공지능", "머신러닝", "딥러닝", "빅데이터", "데이터사이언스",
    "데이터 분석", "데이터분석", "챗봇", "자연어처리", "컴퓨터비전",
]


def build_core_ai_it_codeset(ncs_unit_df: pd.DataFrame) -> pd.DataFrame:
    df = ncs_unit_df.copy()
    df["ncsSubCode"] = df["majorCode"] + df["middleCode"] + df["minorCode"] + df["subCode"]

    rows = []
    ict = df[df["majorCode"] == _ICT_MAJOR]
    for middle_code, basis in {**_INCLUDED_MIDDLE, **_REVIEW_ONLY_MIDDLE}.items():
        included = middle_code in _INCLUDED_MIDDLE
        grp = ict[ict["middleCode"] == middle_code].sort_values("ncsUnitCode")
        for sub_code, names in grp.groupby("ncsSubCode")["ncsUnitName"]:
            names_list = names.tolist()
            rows.append({
                "ncsSubCode": sub_code,
                "ncsSubName": names_list[0],
                "subNameIsDerived": True,
                "included": included,
                "inclusionBasis": f"major={_ICT_MAJOR}(정보통신)/middle={middle_code} -- {basis}",
                "inclusionEvidence": f"{len(names_list)} constituent units, e.g. {names_list[:3]}",
                "reviewStatus": "REVIEW_REQUIRED",
                "codeSetVersion": CODESET_VERSION,
            })

    return pd.DataFrame(rows)


def find_cross_major_ai_candidates(ncs_unit_df: pd.DataFrame) -> pd.DataFrame:
    """Units outside major=20 whose name contains an explicit AI/bigdata keyword.

    Returned as unit-level candidates for manual review -- NOT auto-merged
    into the subCode-level codeset table, since including them would pull in
    unrelated sibling units from the same subCode group.
    """
    pattern = "|".join(_CROSS_MAJOR_AI_KEYWORDS)
    mask = ncs_unit_df["ncsUnitName"].str.contains(pattern, na=False) & (ncs_unit_df["majorCode"] != _ICT_MAJOR)
    hits = ncs_unit_df.loc[mask, ["ncsUnitCode", "ncsUnitName", "majorCode", "ncsLevel"]].copy()
    hits["matchedKeyword"] = hits["ncsUnitName"].str.extract(f"({pattern})")
    return hits
