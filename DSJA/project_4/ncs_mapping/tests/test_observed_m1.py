import json
from pathlib import Path

import pandas as pd
import pytest

from p4_ncs.contracts.observed_duty import canonical_json_sha256, load_and_validate_observed_duties
from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary
from p4_ncs.evaluation.gold_evaluation import GOLD_COLUMNS, evaluate_gold_mapping, load_gold_structure
from p4_ncs.mapping.observed_baseline import map_observed_duties
from p4_ncs.retrieval.lexical_index import LexicalIndex, restrict_units_to_subcategories

NCS_ROOT = Path(__file__).resolve().parents[1]


def _row(**overrides):
    row = {
        "trackId": "TRK_TEST",
        "sectionId": "SEC_TEST",
        "evidenceText": "머신러닝 모델 개발 및 데이터 분석",
        "jobTitle": "개발자",
        "jobCode": None,
        "ncsEligibleFlag": True,
        "parseVersion": "test-parse",
        "inputSha256": "a" * 64,
    }
    row.update(overrides)
    return row


def _handoff(path: Path, rows: list[dict], include_rows_sha: bool = True) -> Path:
    payload = {
        "agentId": "P4-A2-PIPELINE",
        "recipientAgentId": "P4-A4-NCS",
        "handoffType": "DUTY_INPUT_OBSERVED_DEVELOPMENT",
        "status": "OBSERVED_DEVELOPMENT_ONLY",
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": "observed-dev-test",
        "grain": "sectionId",
        "empiricalUseAllowed": False,
        "promotionAllowed": False,
        "rowCount": len(rows),
        "rows": rows,
    }
    if include_rows_sha:
        payload["rowsSha256"] = canonical_json_sha256(rows)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def sources():
    units = pd.read_parquet(NCS_ROOT / "data/processed/ncsUnit.parquet")
    codeset = pd.read_parquet(NCS_ROOT / "data/processed/coreAiItCodeSet.parquet")
    aliases = load_alias_dictionary(NCS_ROOT / "configs/ncs_alias_dictionary.yaml")
    return units, codeset, aliases, LexicalIndex.build(units, codeset)


def test_observed_handoff_recomputes_and_verifies_rows_sha(tmp_path):
    rows = [_row()]
    frame, validation, _ = load_and_validate_observed_duties(_handoff(tmp_path / "handoff.json", rows))
    assert len(frame) == validation.row_count == 1
    assert validation.rows_sha256_verified is True
    assert validation.warning_codes == ()


def test_early_handoff_without_declared_rows_sha_is_warning(tmp_path):
    _, validation, _ = load_and_validate_observed_duties(
        _handoff(tmp_path / "handoff.json", [_row()], include_rows_sha=False)
    )
    assert validation.rows_sha256_verified is False
    assert validation.warning_codes == ("MISSING_DECLARED_ROWS_SHA256",)


def test_rows_sha_mismatch_fails(tmp_path):
    path = _handoff(tmp_path / "handoff.json", [_row()])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rowsSha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="rowsSha256 mismatch"):
        load_and_validate_observed_duties(path)


def test_duplicate_section_fails(tmp_path):
    with pytest.raises(ValueError, match="duplicate sectionId"):
        load_and_validate_observed_duties(_handoff(tmp_path / "handoff.json", [_row(), _row()]))


def test_same_subcategory_restriction(sources):
    units, _, _, _ = sources
    restricted = restrict_units_to_subcategories(units, {"20010701"})
    assert len(restricted) > 0
    assert restricted["ncsUnitCode"].str.startswith("20010701").all()


def test_lexical_index_returns_unique_top5(sources):
    _, _, _, index = sources
    hits = index.search("데이터 분석 모델 개발", top_k=5)
    assert 0 < len(hits) <= 5
    assert len({hit.ncsSubCode for hit in hits}) == len(hits)
    assert all(hit.matchedNcsUnitCode.startswith(hit.ncsSubCode) for hit in hits)


def test_batch_mapping_preserves_unmapped_and_never_dense(sources):
    _, codeset, aliases, index = sources
    duties = pd.DataFrame([
        _row(),
        _row(trackId="TRK_2", sectionId="SEC_2", evidenceText="Python 가능"),
        _row(trackId="TRK_3", sectionId="SEC_3", evidenceText="완전히 무관한 외계문구"),
    ])
    candidates, matches = map_observed_duties(duties, index, aliases, codeset, "observed-dev-test")
    assert len(matches) == 3
    assert candidates.groupby("sectionId").size().max() <= 5
    assert matches["denseScore"].isna().all()
    assert (matches["mappingMode"] == "LEXICAL_BASELINE").all()
    assert (matches["goldValidatedFlag"] == False).all()  # noqa: E712
    bare = matches.loc[matches["sectionId"] == "SEC_2"].iloc[0]
    assert bare["mappingBasis"] == "unmapped"
    assert bare["unmappedReason"] == "BARE_TOOL_MENTION"


def test_alias_anchor_restricts_same_subcategory(sources):
    _, codeset, aliases, index = sources
    duties = pd.DataFrame([_row(evidenceText="머신러닝 엔지니어 모델 개발")])
    candidates, _ = map_observed_duties(duties, index, aliases, codeset, "observed-dev-test")
    assert not candidates.empty
    assert set(candidates["ncsSubCode"]) == {"20010701"}
    assert candidates["sameSubcategoryRestrictedFlag"].all()


def test_empty_gold_is_not_evaluated():
    result = evaluate_gold_mapping(load_gold_structure())
    assert result.goldRows == 0
    assert result.precision is None
    assert result.finalCoverage is None
    assert result.gateStatus == "NOT_EVALUATED"
    assert result.goldValidatedFlag is False


def test_nonempty_gold_is_rejected_in_observed_development():
    row = {column: None for column in GOLD_COLUMNS}
    row["goldSampleId"] = "GOLD_1"
    with pytest.raises(ValueError, match="cannot evaluate non-empty gold"):
        evaluate_gold_mapping(pd.DataFrame([row], columns=GOLD_COLUMNS))
