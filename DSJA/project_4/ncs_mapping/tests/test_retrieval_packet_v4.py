import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from p4_ncs.retrieval.dense import DenseRetrievalAdapter
from p4_ncs.retrieval.hybrid import (
    OUT_OF_SCOPE_CODE, BM25Index, HybridRetriever, RetrievalDocument,
    char_ngrams, word_ngrams,
)
from p4_ncs.retrieval.packet import build_candidate_packet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((PROJECT_ROOT / "shared/contracts/semantic_ncs_reference/v4.0/schemas/candidate_packet.schema.json").read_text())


@pytest.fixture
def documents():
    return [
        RetrievalDocument("U1", "머신러닝 모델 개발", "학습 데이터를 전처리하고 모델을 개발한다", "20010701", ("모델 설계", "모델 평가", "배포")),
        RetrievalDocument("U2", "데이터베이스 설계", "논리 데이터 모델과 SQL을 설계한다", "20010204"),
        RetrievalDocument("U3", "네트워크 운영", "네트워크 장애를 분석한다", "20010301"),
        RetrievalDocument("U4", "정보보안 분석", "보안 취약점을 분석한다", "20010601"),
    ]


def test_feature_contract_is_char_3_to_5_and_word_1_to_2():
    assert set(map(len, char_ngrams("데이터분석"))) == {3, 4, 5}
    assert set(word_ngrams("데이터 분석 모델")) == {"데이터", "분석", "모델", "데이터 분석", "분석 모델"}


def test_bm25_is_pure_python_and_ranks_matching_document(documents):
    results = BM25Index(documents).search("머신러닝 모델", top_k=3)
    assert results[0][0].code == "U1"
    assert results[0][1] > 0


def test_top10_union_includes_alias_hierarchy_and_out_of_scope(documents):
    results = HybridRetriever(documents).retrieve(
        "머신러닝 엔지니어 모델 개발", top_k=10,
        aliases={"머신러닝 엔지니어": "U1"}, hierarchy_backoff=["U4"],
    )
    assert len(results) <= 10
    assert results[0].code == "U1"
    assert "aliasExact" in results[0].match_bases
    assert any(row.code == "U4" and "hierarchyBackoff" in row.match_bases for row in results)
    assert results[-1].code == OUT_OF_SCOPE_CODE


def test_dense_adapter_is_explicitly_not_evaluated_without_model():
    result = DenseRetrievalAdapter().retrieve("데이터 분석")
    assert result.status == "NOT_EVALUATED"
    assert result.reason == "DENSE_MODEL_OR_REVISION_UNAVAILABLE"
    assert result.candidates == ()


def test_dense_adapter_with_unimplemented_pinned_model_fails_closed():
    with pytest.raises(NotImplementedError):
        DenseRetrievalAdapter(model_id="model", model_revision="sha").retrieve("데이터")


def test_candidate_packet_is_bounded_hashed_and_schema_valid(documents):
    candidates = HybridRetriever(documents).retrieve("머신러닝 모델 개발", top_k=10)
    packet = build_candidate_packet(
        annotation_task_id="TASK_1", target_text="머신러닝 모델 개발",
        source_role="DUTY", candidates=candidates, adjacent_context=["앞 문맥", "뒤 문맥"],
    )
    Draft202012Validator(SCHEMA).validate(packet.contract_record)
    assert packet.contract_record["candidateCodesJson"][-1] == OUT_OF_SCOPE_CODE
    assert len(packet.contract_record["packetSha256"]) == 64
    assert packet.detail["candidates"][0]["performanceCriteria"] == ["모델 설계", "모델 평가"]


def test_candidate_packet_reports_truncation_without_silent_loss(documents):
    candidates = HybridRetriever(documents).retrieve("모델 개발", top_k=10)
    packet = build_candidate_packet(
        annotation_task_id="TASK_LONG", target_text="가나다라 " * 700,
        source_role="OTHER", candidates=candidates, adjacent_context=["문맥" * 1000],
    )
    assert packet.contract_record["targetCharCount"] <= 1200
    assert packet.contract_record["targetTokenCount"] <= 600
    assert packet.detail["targetTruncation"]["truncatedFlag"] is True
    assert packet.detail["targetTruncation"]["removedCharCount"] > 0
    assert packet.detail["contextTruncation"]["truncatedFlag"] is True


def test_candidate_packet_rejects_empty_target(documents):
    candidates = HybridRetriever(documents).retrieve("모델", top_k=10)
    with pytest.raises(ValueError, match="non-empty"):
        build_candidate_packet(annotation_task_id="T", target_text=" ", source_role="DUTY", candidates=candidates)
