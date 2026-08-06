from __future__ import annotations

import json
from pathlib import Path

import pytest

from crawl.control.notebook_bundle import (
    audit_current_run_authority,
    bind_current_run_manifests,
    quarantine_manifest,
    require_current_run_manifest,
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
        "dataVersion": "observed-dev-20260806.2",
    }


def test_current_run_manifest_requires_all_binding_fields() -> None:
    payload = valid_payload()
    payload.pop("parameterSha256")
    errors = validate_current_run_manifest(
        payload,
        expected_stage_id="A1-00-RECOVER",
        expected_run_id="observed-dev/RUN-1",
        expected_source_sha256=SHA,
        expected_data_version="observed-dev-20260806.2",
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
        expected_data_version="observed-dev-20260806.2",
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
    _write_stage_artifacts(stage, {"runId": "STALE"})
    execution = {
        "stageId": "A1-00-RECOVER",
        "stageOutputRoot": "crawl/runs/current/A1-00-RECOVER",
        "sourceSha256": SHA,
    }
    with pytest.raises(ValueError, match="stale manifest runId"):
        bind_current_run_manifests(
            project, project / "crawl/runs/current", [execution],
            run_id="current", data_version="observed-dev-20260806.2",
        )


def test_binding_rejects_duplicate_execution_stage(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = project / "crawl/runs/current/A1-00-RECOVER"
    stage.mkdir(parents=True)
    _write_stage_artifacts(stage, {
        "runId": "current",
        "dataVersion": "observed-dev-20260806.2",
        "parameterSha256": "b" * 64,
        "inputManifestSha256": "c" * 64,
        "status": "SUCCEEDED",
        "completedAt": "2026-08-06T00:00:00Z",
    })
    execution = {
        "stageId": "A1-00-RECOVER",
        "stageOutputRoot": "crawl/runs/current/A1-00-RECOVER",
        "sourceSha256": SHA,
    }
    with pytest.raises(ValueError, match="duplicate execution result"):
        bind_current_run_manifests(
            project, project / "crawl/runs/current", [execution, execution],
            run_id="current", data_version="observed-dev-20260806.2",
        )


def _write_stage_artifacts(stage: Path, payload: dict) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "stage_manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (stage / "stage_metrics.json").write_text("{}\n", encoding="utf-8")
    (stage / "stage_quality.csv").write_text("status\nPASS\n", encoding="utf-8")
    (stage / "CHECKSUMS.sha256").write_text("0" * 64 + "  stage_metrics.json\n", encoding="utf-8")


def _bindable_fixture(tmp_path: Path, *, data_version: str = "observed-dev-20260806.2") -> tuple[Path, Path, dict]:
    project = tmp_path / "project"
    run = project / "crawl/runs/current"
    stage = run / "A1-00-RECOVER"
    _write_stage_artifacts(stage, {
        "runId": "current",
        "dataVersion": data_version,
        "parameterSha256": "b" * 64,
        "inputManifestSha256": "c" * 64,
        "status": "SUCCEEDED",
        "completedAt": "2026-08-06T00:00:00Z",
    })
    execution = {
        "stageId": "A1-00-RECOVER",
        "stageOutputRoot": "crawl/runs/current/A1-00-RECOVER",
        "sourceSha256": SHA,
    }
    return project, run, execution


def test_current_run_manifest_rejects_wrong_notebook_source_sha() -> None:
    errors = validate_current_run_manifest(
        valid_payload(), expected_stage_id="A1-00-RECOVER",
        expected_run_id="observed-dev/RUN-1", expected_source_sha256="d" * 64,
        expected_data_version="observed-dev-20260806.2",
    )
    assert "sourceNotebookSha256:mismatch" in errors


def test_binding_rejects_foreign_data_version(tmp_path: Path) -> None:
    project, run, execution = _bindable_fixture(tmp_path, data_version="foreign-version")
    with pytest.raises(ValueError, match="dataVersion:mismatch"):
        bind_current_run_manifests(
            project, run, [execution], run_id="current", data_version="observed-dev-20260806.2",
        )


def test_binding_rejects_empty_required_artifact(tmp_path: Path) -> None:
    project, run, execution = _bindable_fixture(tmp_path)
    (run / "A1-00-RECOVER/stage_quality.csv").write_bytes(b"")
    with pytest.raises(ValueError, match="requiredArtifact:empty:stage_quality.csv"):
        bind_current_run_manifests(
            project, run, [execution], run_id="current", data_version="observed-dev-20260806.2",
        )


def test_preexisting_stage_artifact_without_current_run_binding_is_rejected(tmp_path: Path) -> None:
    project, run, _ = _bindable_fixture(tmp_path)
    with pytest.raises(FileNotFoundError, match="canonical current-run manifest missing"):
        require_current_run_manifest(
            run, stage_id="A1-00-RECOVER", expected_run_id="current",
            expected_source_sha256=SHA, expected_data_version="observed-dev-20260806.2",
        )


def test_duplicate_canonical_current_run_authority_is_reported(tmp_path: Path) -> None:
    run = tmp_path / "run"
    for suffix in ("A1-00-RECOVER", "duplicate/A1-00-RECOVER"):
        path = run / "current_run_manifests" / suffix / "stage_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(valid_payload()) + "\n", encoding="utf-8")
    rows = audit_current_run_authority(run, ["A1-00-RECOVER"])
    assert rows == [{"stageId": "A1-00-RECOVER", "manifestCount": 2, "status": "FAIL"}]
