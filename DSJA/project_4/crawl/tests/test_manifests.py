from __future__ import annotations

from p4_crawl.manifests import append_jsonl_once, load_jsonl


def test_manifest_append_is_idempotent(tmp_path) -> None:
    path = tmp_path / "manifest.jsonl"
    row = {"rowId": "stable-1", "value": 1}
    assert append_jsonl_once(path, row)
    assert not append_jsonl_once(path, {**row, "value": 2})
    assert load_jsonl(path) == [row]
