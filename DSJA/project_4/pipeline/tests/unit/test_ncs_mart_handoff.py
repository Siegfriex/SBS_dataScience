from __future__ import annotations

import hashlib
import json

import pytest

from p4.contracts.ncs_mart_handoff import load_ncs_mart_handoff


def payload():
    rows = [{
        "trackId": "T1", "sectionId": "S1", "chunkId": "C1",
        "mappingStatus": "REVIEW_REQUIRED", "ncsUnitCode": "U1",
        "ncsCorpusVersion": "V1", "officialLevel": 5, "ncsBand": "level5to6",
        "sourceRole": "DUTY", "evidencePointer": "artifact#row=1",
        "candidatePacketSha256": "a" * 64, "mappingRunId": "RUN-1",
    }]
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "schemaVersion": "p4-ncs-mapping-to-mart-v1", "mappingQualityStatus": "NOT_EVALUATED",
        "goldAuthority": "NONE", "humanGoldRows": 0, "promotionAllowed": False,
        "empiricalAnalysisAllowed": False, "rowCount": 1,
        "rowsSha256": hashlib.sha256(canonical.encode()).hexdigest(), "rows": rows,
    }


def test_load_structural_ncs_mart_handoff(tmp_path):
    target = tmp_path / "handoff.json"; target.write_text(json.dumps(payload()), encoding="utf-8")
    frame, envelope = load_ncs_mart_handoff(target)
    assert len(frame) == 1
    assert envelope["mappingQualityStatus"] == "NOT_EVALUATED"


def test_ncs_mart_handoff_rejects_quality_promotion(tmp_path):
    value = payload(); value["mappingQualityStatus"] = "PASS"
    target = tmp_path / "handoff.json"; target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot claim mapping quality"):
        load_ncs_mart_handoff(target)
