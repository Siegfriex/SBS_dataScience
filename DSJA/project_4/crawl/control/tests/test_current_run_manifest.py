from __future__ import annotations

import json
from pathlib import Path

import pytest

from crawl.control.notebook_bundle import (
    bind_current_run_manifests,
    quarantine_manifest,
    validate_current_run_manifest,
)


SHA = "a" * 64


def valid_payload() -> dict:
    return {
        "stageId": "A1-00-RECOVER",
        "runId": "observed-dev/RUN-1",
        "sourceNotebookSha256": SHA,
        "parameterSha256": "b" * 64,
        "inputManifestSha256": "c" * 64,
        "outputRoot": "crawl/runs/RUN-1/A1-00-RECOVER",
        "status": "SUCCEEDED",
        "createdAt": "2026-08-06T00:00:00Z",
    }


def test_current_run_manifest_requires_all_binding_fields() -> None:
    payload = valid_payload()
    payload.pop("parameterSha256")
    errors = validate_current_run_manifest(
        payload,
        expected_stage_id="A1-00-RECOVER",
        expected_run_id="observed-dev/RUN-1",
        expected_source_sha256=SHA,
    )
    assert "missing:parameterSha256" in errors


def test_current_run_manifest_rejects_stale_run_and_absolute_path() -> None:
    payload = valid_payload()
    payload["runId"] = "STALE"
    payload["outputRoot"] = "/tmp/leak"
    errors = validate_current_run_manifest(
        payload,
        expected_stage_id="A1-00-RECOVER",
        expected_run_id="observed-dev/RUN-1",
        expected_source_sha256=SHA,
    )
    assert "runId:mismatch" in errors
    assert "outputRoot:not-portable" in errors


def test_quarantine_preserves_stale_manifest_bytes(tmp_path: Path) -> None:
    stale = tmp_path / "stage_manifest.json"
    stale.write_text('{"status":"FAILED"}\n', encoding="utf-8")
    expected = stale.read_bytes()
    destination = quarantine_manifest(stale, tmp_path / "superseded", reason="stale")
    assert not stale.exists()
    assert destination.read_bytes() == expected


def test_binding_rejects_stale_underlying_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = project / "crawl/runs/current/A1-00-RECOVER"
    stage.mkdir(parents=True)
    (stage / "stage_manifest.json").write_text(json.dumps({"runId": "STALE"}), encoding="utf-8")
    execution = {
        "stageId": "A1-00-RECOVER",
        "stageOutputRoot": "crawl/runs/current/A1-00-RECOVER",
        "sourceSha256": SHA,
    }
    with pytest.raises(ValueError, match="stale manifest runId"):
        bind_current_run_manifests(project, project / "crawl/runs/current", [execution], run_id="current")


def test_binding_rejects_duplicate_execution_stage(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = project / "crawl/runs/current/A1-00-RECOVER"
    stage.mkdir(parents=True)
    (stage / "stage_manifest.json").write_text(json.dumps({
        "runId": "current",
        "parameterSha256": "b" * 64,
        "inputManifestSha256": "c" * 64,
        "status": "SUCCEEDED",
        "completedAt": "2026-08-06T00:00:00Z",
    }), encoding="utf-8")
    execution = {
        "stageId": "A1-00-RECOVER",
        "stageOutputRoot": "crawl/runs/current/A1-00-RECOVER",
        "sourceSha256": SHA,
    }
    with pytest.raises(ValueError, match="duplicate execution result"):
        bind_current_run_manifests(project, project / "crawl/runs/current", [execution, execution], run_id="current")
