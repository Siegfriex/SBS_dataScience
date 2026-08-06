from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest

from p4_crawl.raw_authority import (
    AVAILABLE,
    COMPRESSED_SHA_MISMATCH,
    RAW_ROOT_UNMOUNTED,
    RawAuthorityBlocked,
    audit_raw_posting_binding,
    build_raw_object_manifest,
    load_jsonl,
    require_complete_raw_authority,
    validate_manifest_against_mount,
)


CRAWL_ROOT = Path(__file__).resolve().parents[1]
OBSERVED = CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01"


def _raw_mount() -> Path | None:
    candidates = [
        CRAWL_ROOT,
        Path("/home/sieg/projects-wsl/worktrees/p4-agent1/DSJA/project_4/crawl"),
    ]
    for candidate in candidates:
        if (candidate / "data/raw/linkareer/detail").is_dir():
            return candidate
    return None


def _manifest() -> tuple[list[dict], list[dict]]:
    root = _raw_mount()
    if root is None:
        pytest.skip("external observed raw mount unavailable")
    return build_raw_object_manifest(
        load_jsonl(OBSERVED / "raw_detail_manifest.jsonl"),
        root,
        storage_root_id="P4_RAW_OBSERVED_20260806_01",
        mount_policy_version="p4-raw-mount-v1",
    )


def test_mounted_raw_authority_resolves_29_of_29() -> None:
    manifest, audit = _manifest()
    assert len(manifest) == len(audit) == 29
    assert {row["availabilityStatus"] for row in audit} == {AVAILABLE}
    assert all(not Path(row["objectLocatorRelative"]).is_absolute() for row in manifest)
    assert all("/home/" not in str(row) for row in manifest)


def test_unmounted_raw_root_fails_closed() -> None:
    source = load_jsonl(OBSERVED / "raw_detail_manifest.jsonl")[:1]
    _manifest_rows, audit = build_raw_object_manifest(
        source,
        CRAWL_ROOT / "definitely-unmounted-raw-root",
        storage_root_id="P4_RAW_OBSERVED_20260806_01",
        mount_policy_version="p4-raw-mount-v1",
    )
    assert audit[0]["availabilityStatus"] == RAW_ROOT_UNMOUNTED
    with pytest.raises(RawAuthorityBlocked, match="RAW_ROOT_UNMOUNTED"):
        require_complete_raw_authority(audit)


def test_wrong_compressed_sha_quarantines_without_fallback() -> None:
    manifest, _audit = _manifest()
    tampered = copy.deepcopy(manifest)
    tampered[0]["compressedSha256"] = "0" * 64
    result = validate_manifest_against_mount(tampered, _raw_mount())
    assert result[0]["availabilityStatus"] == COMPRESSED_SHA_MISMATCH
    assert result[0]["bindingStatus"] == "QUARANTINED"
    assert result[0]["downstreamConsumable"] is False


def test_observed_raw_posting_binding_is_explicit() -> None:
    manifest, _audit = _manifest()
    detail = load_jsonl(OBSERVED / "raw_detail_manifest.jsonl")
    posting = pd.read_parquet(OBSERVED / "posting_manifest.parquet")
    rows = audit_raw_posting_binding(manifest, detail, posting)
    assert len(rows) == 29
    assert sum(row["bindingStatus"] == "MATCHED" for row in rows) == 11
    assert sum(row["bindingStatus"] == "QUARANTINED" for row in rows) == 18
    assert all(row["bindingStatus"] != "UNRESOLVED" for row in rows)
