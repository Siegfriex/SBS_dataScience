from __future__ import annotations

from p4_crawl.detail import select_activity_text


def test_explicit_apollo_reference_has_priority() -> None:
    cache = {
        "ActivityText:one": {"text": "chosen"},
        "ActivityText:two": {"text": "other"},
    }
    selected, evidence = select_activity_text(cache, {"detailText": {"__ref": "ActivityText:one"}}, "42")
    assert selected == {"text": "chosen"}
    assert evidence["fallbackStatus"] == "EXPLICIT_ACTIVITY_REFERENCE"
    assert evidence["candidateCount"] == 2


def test_source_id_matching_standalone_entity_has_priority() -> None:
    cache = {
        "ActivityText:42": {"text": "chosen"},
        "ActivityText:99": {"text": "other"},
    }
    selected, evidence = select_activity_text(cache, {}, "42")
    assert selected == {"text": "chosen"}
    assert evidence["fallbackStatus"] == "STANDALONE_SOURCE_ID_MATCH"


def test_single_standalone_entity_is_unambiguous() -> None:
    selected, evidence = select_activity_text({"ActivityText:legacy": {"text": "legacy"}}, {}, "42")
    assert selected == {"text": "legacy"}
    assert evidence["fallbackStatus"] == "STANDALONE_UNAMBIGUOUS"


def test_ambiguous_standalone_entities_are_never_auto_selected() -> None:
    selected, evidence = select_activity_text(
        {"ActivityText:a": {"text": "a"}, "ActivityText:b": {"text": "b"}}, {}, "42",
    )
    assert selected is None
    assert evidence["fallbackStatus"] == "AMBIGUOUS_STANDALONE"
    assert evidence["selectionBasis"] == "NO_AUTO_SELECTION"
    assert evidence["candidateCount"] == 2
