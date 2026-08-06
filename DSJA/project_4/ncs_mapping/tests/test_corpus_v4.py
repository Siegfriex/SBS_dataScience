import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from p4_ncs.corpus.diff import diff_corpus_nodes
from p4_ncs.corpus.graph import build_ability_units, build_prefix_graph, validate_prefix_graph
from p4_ncs.corpus.release import build_candidate_release_manifest
from p4_ncs.corpus.validators import validate_crosswalk, validate_duty_unit_bridge


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NCS_ROOT = PROJECT_ROOT / "ncs_mapping"
SCHEMA_ROOT = PROJECT_ROOT / "shared" / "contracts" / "semantic_ncs_reference" / "v4.0" / "schemas"
VERSION = "ncs-candidate-2026-02-20-v4.0"


@pytest.fixture(scope="module")
def units():
    return pd.read_parquet(NCS_ROOT / "data" / "processed" / "ncsUnit.parquet")


@pytest.fixture(scope="module")
def graph(units):
    return build_prefix_graph(units, VERSION)


def test_full_official_unit_source_and_level_are_preserved(units):
    ability = build_ability_units(units, VERSION)
    assert len(ability) == ability.ncsUnitCode.nunique() == 13_442
    assert ability.ncsLevel.notna().sum() == 13_442
    assert sorted(ability.ncsLevel.unique()) == list(range(1, 9))
    assert ability.ncsUnitDefinition.isna().all()
    assert ability.dutyCodesJson.map(len).eq(0).all()


def test_prefix_graph_exact_counts_and_no_orphans(graph):
    nodes, edges = graph
    assert nodes.nodeType.value_counts().to_dict() == {
        "UNIT": 13_442, "SUBCATEGORY": 1_109, "SMALL": 274, "MIDDLE": 81, "LARGE": 24
    }
    assert len(nodes) == 14_930
    assert len(edges) == 14_906
    validate_prefix_graph(nodes, edges)


def test_hierarchy_names_are_explicitly_missing_and_unit_metadata_official(graph):
    nodes, _ = graph
    hierarchy = nodes.nodeType.ne("UNIT")
    assert nodes.loc[hierarchy, "officialName"].isna().all()
    assert nodes.loc[hierarchy, "nameSource"].eq("MISSING").all()
    assert nodes.loc[~hierarchy, "nameSource"].eq("OFFICIAL").all()
    assert nodes.loc[~hierarchy, "officialLevel"].notna().all()


def test_node_and_edge_samples_validate_agent3_schemas(graph):
    nodes, edges = graph
    node_schema = json.loads((SCHEMA_ROOT / "ncs_node.schema.json").read_text())
    edge_schema = json.loads((SCHEMA_ROOT / "ncs_edge.schema.json").read_text())
    sample_nodes = pd.concat([nodes.head(5), nodes.tail(5)]).astype(object)
    sample_nodes = sample_nodes.where(pd.notna(sample_nodes), None)
    for row in sample_nodes.to_dict(orient="records"):
        Draft202012Validator(node_schema).validate(row)
    for row in pd.concat([edges.head(5), edges.tail(5)]).to_dict(orient="records"):
        Draft202012Validator(edge_schema).validate(row)


def test_empty_bridge_and_crosswalk_are_not_evaluated(graph):
    nodes, _ = graph
    assert validate_duty_unit_bridge(pd.DataFrame(), nodes) == "NOT_EVALUATED"
    assert validate_crosswalk(pd.DataFrame(), nodes) == "NOT_EVALUATED"


def test_crosswalk_matched_code_must_exist(graph):
    nodes, _ = graph
    row = pd.DataFrame([{
        "provider": "WORK24", "externalCode": "EXT-1", "externalName": "테스트",
        "canonicalNodeCode": "DOES_NOT_EXIST", "canonicalizationStatus": "MATCHED",
        "matchBasis": "exact_code", "sourceResponseSha256": "a" * 64,
        "crosswalkVersion": "test-v1",
    }])
    with pytest.raises(ValueError, match="unknown canonical code"):
        validate_crosswalk(row, nodes)


def test_unmatched_crosswalk_cannot_smuggle_canonical_code(graph):
    nodes, _ = graph
    row = pd.DataFrame([{
        "provider": "WORK24", "externalCode": "EXT-1", "externalName": "테스트",
        "canonicalNodeCode": nodes.iloc[0].nodeCode, "canonicalizationStatus": "UNMATCHED",
        "matchBasis": "none", "sourceResponseSha256": "a" * 64,
        "crosswalkVersion": "test-v1",
    }])
    with pytest.raises(ValueError, match="must not carry"):
        validate_crosswalk(row, nodes)


def test_corpus_diff_is_deterministic_and_detects_level_change(graph):
    nodes, _ = graph
    modified = nodes.copy()
    idx = modified.index[modified.nodeType.eq("UNIT")][0]
    modified.loc[idx, "officialLevel"] = int(modified.loc[idx, "officialLevel"]) - 1
    first = diff_corpus_nodes(nodes, modified, from_version="v1", to_version="v2")
    second = diff_corpus_nodes(nodes, modified, from_version="v1", to_version="v2")
    pd.testing.assert_frame_equal(first, second)
    assert first.changeType.tolist() == ["LEVEL_CHANGED"]


def test_candidate_release_manifest_is_reproducible_and_compact(units):
    source = NCS_ROOT / "data" / "processed" / "ncsUnit.parquet"
    first = build_candidate_release_manifest(units, ncs_corpus_version=VERSION, normalized_path=source)
    second = build_candidate_release_manifest(units, ncs_corpus_version=VERSION, normalized_path=source)
    assert first == second
    assert first["rowCounts"]["ncsNode"] == 14_930
    assert first["rowCounts"]["ncsDutyUnitBridge"] == 0
    assert first["officialFieldCoverage"]["unitLevel"] == 13_442
    assert first["officialFieldCoverage"]["unitDefinition"] == 0
    assert first["promotionAllowed"] is False
