from __future__ import annotations

import pandas as pd
import pytest

from p4_ncs.marts.handoff import build_mapping_to_mart_handoff, validate_mapping_to_mart_handoff


def fixtures():
    matches = pd.DataFrame([
        {"trackId": "T1", "sectionId": "S1", "matchedNcsUnitCode": "U1", "unmappedReason": None},
        {"trackId": "T2", "sectionId": "S2", "matchedNcsUnitCode": None, "unmappedReason": "NO_CANDIDATE"},
    ])
    candidates = pd.DataFrame([
        {"trackId": "T1", "sectionId": "S1", "candidateRank": 1, "matchedNcsUnitCode": "U1"},
        {"trackId": "T2", "sectionId": "S2", "candidateRank": 1, "matchedNcsUnitCode": None},
    ])
    units = pd.DataFrame([
        {"ncsUnitCode": "U1", "ncsLevel": 5, "ncsBand": "level5to6", "ncsSourceVersion": "2026-02-20"},
    ])
    chunks = pd.DataFrame([
        {"chunkId": "C1", "sectionId": "S1", "ncsMappableFlag": True},
        {"chunkId": "C2", "sectionId": "S2", "ncsMappableFlag": True},
    ])
    roles = pd.DataFrame([{"chunkId": "C1", "sourceRole": "DUTY"}, {"chunkId": "C2", "sourceRole": "DUTY"}])
    return matches, candidates, units, chunks, roles


def test_structural_handoff_preserves_gold_boundary():
    frame = build_mapping_to_mart_handoff(*fixtures(), mapping_run_id="RUN-1")
    assert len(frame) == 2
    assert frame["mappingStatus"].tolist() == ["REVIEW_REQUIRED", "UNMAPPED"]
    assert frame["mappingQualityEvaluated"].eq(False).all()
    assert frame["goldAuthority"].eq("NONE").all()
    assert frame["promotionAllowed"].eq(False).all()
    assert frame.loc[frame.mappingStatus.eq("REVIEW_REQUIRED"), "officialLevel"].tolist() == [5.0]


def test_unsupported_official_code_fails_closed():
    matches, candidates, units, chunks, roles = fixtures()
    matches.loc[0, "matchedNcsUnitCode"] = "UNKNOWN"
    with pytest.raises(ValueError, match="unsupported official NCS code"):
        build_mapping_to_mart_handoff(matches, candidates, units, chunks, roles, mapping_run_id="RUN-1")


def test_quality_claim_injection_is_rejected():
    frame = build_mapping_to_mart_handoff(*fixtures(), mapping_run_id="RUN-1")
    frame["mappingQualityEvaluated"] = True
    with pytest.raises(ValueError, match="quality evaluation"):
        validate_mapping_to_mart_handoff(frame)
