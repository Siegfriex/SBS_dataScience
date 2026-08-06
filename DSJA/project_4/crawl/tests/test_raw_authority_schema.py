from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from p4_crawl.raw_authority import build_raw_object_manifest, load_jsonl


CRAWL_ROOT = Path(__file__).resolve().parents[1]


def test_raw_object_manifest_schema_accepts_verified_objects() -> None:
    raw_mount = Path("/home/sieg/projects-wsl/worktrees/p4-agent1/DSJA/project_4/crawl")
    if not (raw_mount / "data/raw/linkareer/detail").is_dir():
        pytest.skip("external observed raw mount unavailable")
    source = load_jsonl(
        CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01/raw_detail_manifest.jsonl"
    )
    rows, audit = build_raw_object_manifest(
        source,
        raw_mount,
        storage_root_id="P4_RAW_OBSERVED_20260806_01",
        mount_policy_version="p4-raw-mount-v1",
    )
    schema = json.loads((CRAWL_ROOT / "control/A1_RAW_OBJECT_MANIFEST.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    assert len(rows) == len(audit) == 29
    for row in rows:
        validator.validate(row)
