from pathlib import Path

import pandas as pd
import pytest

from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary, validate_alias_dictionary
from p4_ncs.mapping.mapping_basis import MappingBasis, classify_mapping_basis, is_bare_tool_mention
from p4_ncs.retrieval.candidate_retrieval import TOP_K, alias_lookup, dense_rerank, retrieve_candidates

REPO_ROOT = Path(__file__).parent.parent
ALIAS_CONFIG = REPO_ROOT / "configs" / "ncs_alias_dictionary.yaml"
CODESET_PARQUET = REPO_ROOT / "data" / "processed" / "coreAiItCodeSet.parquet"


@pytest.fixture
def alias_df():
    return load_alias_dictionary(ALIAS_CONFIG)


@pytest.fixture
def codeset_df():
    return pd.read_parquet(CODESET_PARQUET)


def test_alias_dictionary_loads(alias_df):
    assert len(alias_df) >= 5
    assert {"alias", "ncsSubCode", "mappingBasis"}.issubset(alias_df.columns)


def test_alias_dictionary_all_codes_valid(alias_df, codeset_df):
    bad = validate_alias_dictionary(alias_df, set(codeset_df["ncsSubCode"]))
    assert bad == [], f"alias dictionary references unknown ncsSubCode(s): {bad}"


def test_alias_lookup_hit(alias_df):
    hits = alias_lookup("머신러닝 엔지니어 채용", alias_df)
    assert any(h.ncsSubCode == "20010701" for h in hits)


def test_alias_lookup_miss(alias_df):
    hits = alias_lookup("완전히 무관한 문구입니다", alias_df)
    assert hits == []


def test_retrieve_candidates_caps_at_top_k(alias_df, codeset_df):
    candidates = retrieve_candidates("데이터베이스 개발자 채용", alias_df, codeset_df)
    assert len(candidates) <= TOP_K


def test_dense_rerank_is_identity_passthrough(alias_df):
    hits = alias_lookup("머신러닝 엔지니어", alias_df)
    assert dense_rerank(hits) == hits


@pytest.mark.parametrize("text", ["Python", "python 가능", "SQL 사용", "Java 경험", "파이썬"])
def test_bare_tool_mention_detected(text):
    assert is_bare_tool_mention(text) is True


@pytest.mark.parametrize("text", ["Python으로 데이터 파이프라인 구축", "SQL 기반 통계 리포트 작성 업무"])
def test_tool_plus_duty_not_bare_mention(text):
    assert is_bare_tool_mention(text) is False


def test_bare_tool_mention_never_gets_mapped():
    result = classify_mapping_basis("Python 가능", has_dictionary_hit=True, has_semantic_hit=True)
    assert result == MappingBasis.UNMAPPED


def test_dictionary_hit_takes_priority_over_semantic():
    result = classify_mapping_basis("머신러닝 파이프라인 구축", has_dictionary_hit=True, has_semantic_hit=True)
    assert result == MappingBasis.DICTIONARY_RULE


def test_no_hit_is_unmapped():
    result = classify_mapping_basis("전혀 관련 없는 문구", has_dictionary_hit=False, has_semantic_hit=False)
    assert result == MappingBasis.UNMAPPED
