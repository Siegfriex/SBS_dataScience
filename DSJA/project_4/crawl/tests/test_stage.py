from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from p4_crawl.stage import write_stage_artifacts


@dataclass
class Config:
    project_root: Path
    run_id: str = "RUN-1"
    run_mode: str = "observed-dev"
    contract_version: str = "2.1.2"
    crawl_release_id: str = "CRAWL_20260806_03"
    data_version: str = "observed-dev-20260806.1"


def test_release_can_terminate_as_not_evaluated(tmp_path: Path, monkeypatch) -> None:
    input_manifest = tmp_path / "HANDOFF.json"
    input_manifest.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("p4_crawl.stage.git_head", lambda _root: "a" * 40)
    manifest = write_stage_artifacts(
        config=Config(tmp_path),
        stage_id="A1-04-RELEASE",
        schema_version="crawl-release-v1",
        started_at="2026-08-06T00:00:00Z",
        parameters={"RUN_MODE": "observed-dev"},
        input_manifest_path=input_manifest,
        stage_root=tmp_path / "stage",
        metric_values={"crawlReleaseReady": False},
        quality_rows=[{
            "gateId": "AGENT2_VALIDATOR",
            "ruleId": "CROSS_AGENT_VALIDATION",
            "severity": "ERROR",
            "status": "NOT_EVALUATED",
            "observedValue": "VALIDATOR_ARTIFACT_MISSING",
            "threshold": "PASS",
            "evidencePath": "agent2_validator_result.json",
        }],
        persisted_files=[],
        branch="test",
        status_override="NOT_EVALUATED",
    )
    assert manifest["status"] == "NOT_EVALUATED"
