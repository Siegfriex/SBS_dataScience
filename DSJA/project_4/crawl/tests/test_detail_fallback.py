from __future__ import annotations

import json

from p4_crawl.detail import extract_detail_record


def _html(cache: dict) -> bytes:
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": cache}}}
    return (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    ).encode()


def _lineage() -> dict:
    return {
        "requestUrl": "https://linkareer.com/activity/42",
        "httpStatus": 200,
        "rawPath": "data/raw/linkareer/detail/2026/08/test.html.gz",
        "contentSha256": "a" * 64,
        "bytes": 1,
        "fetchedAt": "2026-08-06T00:00:00Z",
    }


def test_unambiguous_standalone_activity_text_fallback() -> None:
    cache = {
        "Activity:42": {"__typename": "Activity", "id": "42", "title": "test"},
        "ActivityText:legacy": {"text": "<p>담당업무 데이터 검증</p>"},
    }
    record, _ = extract_detail_record("42", _html(cache), _lineage())
    assert record["activityTextAvailable"] is True
    assert record["activityTextLength"] > 0


def test_ambiguous_standalone_activity_text_is_not_guessed() -> None:
    cache = {
        "Activity:42": {"__typename": "Activity", "id": "42", "title": "test"},
        "ActivityText:one": {"text": "one"},
        "ActivityText:two": {"text": "two"},
    }
    record, _ = extract_detail_record("42", _html(cache), _lineage())
    assert record["activityTextAvailable"] is False


def test_asset_source_field_lineage_is_preserved() -> None:
    cache = {
        "Activity:42": {
            "__typename": "Activity",
            "id": "42",
            "files": [{"__ref": "File:1"}],
            "thumbnailImage": {"__ref": "File:2"},
            "logoImage": {"__ref": "File:3"},
        },
        "File:1": {"url": "https://linkareer.com/files/a.png"},
        "File:2": {"url": "https://linkareer.com/files/b.png"},
        "File:3": {"url": "https://linkareer.com/files/c.png"},
    }
    _, candidates = extract_detail_record("42", _html(cache), _lineage())
    assert {row["sourceField"] for row in candidates} == {
        "activity.files",
        "activity.thumbnailImage",
        "activity.logoImage",
    }
