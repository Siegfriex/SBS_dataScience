#!/usr/bin/env python3
"""Read-only validation for the P4 Notebook control layer."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


CONTROL_DIR = Path(__file__).resolve().parent

EXPECTED_STAGE_IDS = [
    "A1-00-RECOVER",
    "A1-01-INDEX",
    "A1-02-DETAIL",
    "A1-03-ASSET",
    "A1-04-RELEASE",
    "A2-00-CONTRACT-AUDIT",
    "A2-01-LOAD",
    "A2-02-PARSE",
    "A2-03-OCR",
    "A2-04-TRACK",
    "A2-05-REQUIREMENT",
    "A2-06-DEDUP",
    "A2-07-LABEL",
    "A2-08-NCS-LOAD",
    "A2-09-NCS-MAP",
    "A4-00-NCS-SOURCE",
    "A4-01-CODESET",
    "A4-02-RETRIEVAL",
    "A4-03-MAP-OBSERVED",
    "A4-04-EXPORT",
    "A4-05-EVALUATE",
    "A2-10-EXPORT",
    "A2-11-EXPORT-QA",
    "A2-12-POSTING-MART",
    "A2-13-TIME-SERIES",
    "A2-14-ANALYSIS",
    "A2-15-FIGURES",
    "A3-MASTER",
]

EXPECTED_GATE_IDS = [
    "SOURCE_POLICY_READY",
    "CRAWL_OBSERVED_INPUT_READY",
    "CRAWL_RELEASE_READY",
    "PARSE_READY",
    "TRACK_READY",
    "REQUIREMENT_READY",
    "DEDUP_READY",
    "LABEL_DEV_READY",
    "LABEL_GOLD_READY",
    "NCS_BASE_READY",
    "NCS_MAPPING_DEV_READY",
    "NCS_GOLD_SAMPLE_READY",
    "NCS_MAPPING_GOLD_READY",
    "PREPROCESSED_CSV_READY",
    "ANALYSIS_READY",
    "NOTEBOOK_SOURCE_READY",
    "NOTEBOOK_EXECUTION_READY_OBSERVED_DEV",
    "NOTEBOOK_BUNDLE_READY",
]

EXPECTED_TERMINATION_ARTIFACTS = [
    "stage_manifest.json",
    "stage_metrics.json",
    "stage_quality.csv",
    "CHECKSUMS.sha256",
]

EXPECTED_RUNTIME_PACKAGES = {
    "beautifulsoup4", "ipykernel", "jsonschema", "jupyter_client", "nbclient",
    "nbformat", "pandas", "pyarrow", "PyYAML",
}

GATE_COLUMNS = [
    "gateId",
    "producer",
    "requiredEvidence",
    "fixture",
    "observed-dev",
    "production",
    "failureMeaning",
]

MANUAL_GATE_PRODUCERS = {"CONTROLLED-MANUAL-A4-GOLD"}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _load_registry(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a YAML mapping")
    return value


def _load_gates(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _is_relative_repo_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and not value.startswith("~")


def deterministic_topological_order(stages: list[dict[str, Any]]) -> list[str]:
    by_id = {str(stage.get("stageId", "")): stage for stage in stages}
    if "" in by_id or len(by_id) != len(stages):
        raise ValueError("stageId values must be non-empty and unique")
    remaining = {stage_id: set(stage.get("upstreamStages", [])) for stage_id, stage in by_id.items()}
    unknown = sorted({item for upstream in remaining.values() for item in upstream if item not in by_id})
    if unknown:
        raise ValueError("unknown upstream stages: " + ",".join(unknown))
    ordered: list[str] = []
    while remaining:
        ready = sorted(stage_id for stage_id, upstream in remaining.items() if not upstream)
        if not ready:
            raise ValueError("dependency cycle: " + ",".join(sorted(remaining)))
        ordered.extend(ready)
        for stage_id in ready:
            remaining.pop(stage_id)
        for upstream in remaining.values():
            upstream.difference_update(ready)
    return ordered


def observed_execution_example() -> dict[str, Any]:
    """Return a minimal valid M1 execution document for schema checks/tests."""
    return {
        "agentId": "P4-A2-PIPELINE",
        "branch": "agent/p4-pipeline-v2",
        "gitHead": "0" * 40,
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": "OBSERVED_DEV_20260806_01",
        "runMode": "observed-dev",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "asOfDate": "2026-08-06",
        "randomSeed": 20260806,
        "startedAt": "2026-08-06T16:00:00+09:00",
        "inputManifestPath": "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/HANDOFF.json",
        "outputRoot": "crawl/data/exports/observed-dev/OBSERVED_DEV_20260806_01",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "storagePolicy": {
            "canonical": "DUCKDB_PARQUET",
            "inspectionExport": "CSV_UTF8_SIG",
        },
        "eligibilityColumns": [
            "postingEligibleFlag",
            "rq1EligibleFlag",
            "rq2EligibleFlag",
            "ncsEligibleFlag",
        ],
        "highDemandScorePolicy": "ALL_NULL",
        "ksaPolicy": {
            "decisionId": "D-023",
            "status": "PROVISIONAL",
            "mode": "OPTIONAL_ENRICHMENT",
            "blocksM1": False,
        },
        "mappingPolicy": {
            "mappingMode": "LEXICAL_BASELINE",
            "codeSetStatus": "REVIEW_REQUIRED",
            "goldValidatedFlag": False,
            "denseScore": None,
        },
    }


def observed_manifest_example() -> dict[str, Any]:
    """Return a minimal valid observed stage manifest."""
    return {
        "manifestVersion": "stage-manifest-v1",
        "runId": "OBSERVED_DEV_20260806_01-A2-00",
        "runMode": "observed-dev",
        "stageId": "A2-00-CONTRACT-AUDIT",
        "status": "SUCCEEDED",
        "agentId": "P4-A2-PIPELINE",
        "branch": "agent/p4-pipeline-v2",
        "gitHead": "0" * 40,
        "contractVersion": "2.1.2",
        "schemaVersion": "agent2-audit-v1",
        "dataVersion": "OBSERVED_DEV_20260806_01",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "startedAt": "2026-08-06T16:00:00+09:00",
        "completedAt": "2026-08-06T16:01:00+09:00",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "inputManifestSha256": "1" * 64,
        "parameterSha256": "2" * 64,
        "rowCounts": {"input": 137},
        "gateResults": [{"gateId": "CRAWL_OBSERVED_INPUT_READY", "status": "PASS"}],
        "warnings": ["partial observed-development corpus"],
        "errors": [],
        "files": [],
        "terminationArtifacts": EXPECTED_TERMINATION_ARTIFACTS,
        "dataPolicies": {
            "canonicalStorage": "DUCKDB_PARQUET",
            "csvPurpose": "HUMAN_INSPECTION_EXPORT",
            "eligibilityColumns": [
                "postingEligibleFlag",
                "rq1EligibleFlag",
                "rq2EligibleFlag",
                "ncsEligibleFlag",
            ],
            "highDemandScore": "ALL_NULL",
        },
    }


def observed_metrics_example() -> dict[str, Any]:
    """Return a minimal valid observed metrics document."""
    return {
        "metricsVersion": "stage-metrics-v1",
        "runId": "OBSERVED_DEV_20260806_01-A2-00",
        "runMode": "observed-dev",
        "stageId": "A2-00-CONTRACT-AUDIT",
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": "OBSERVED_DEV_20260806_01",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "generatedAt": "2026-08-06T16:01:00+09:00",
        "metrics": [
            {
                "metricId": "postingRows",
                "value": 137,
                "numerator": 137,
                "denominator": 137,
                "unit": "rows",
                "grain": "posting",
                "unknownHandling": "preserve",
                "status": "INFORMATIONAL",
            }
        ],
    }


def validate_control(control_dir: Path = CONTROL_DIR) -> list[str]:
    """Return validation errors without modifying the filesystem."""
    errors: list[str] = []

    schema_names = [
        "NOTEBOOK_EXECUTION_CONTRACT.schema.json",
        "STAGE_MANIFEST.schema.json",
        "STAGE_METRICS.schema.json",
        "CURRENT_RUN_MANIFEST.schema.json",
    ]
    schemas: dict[str, dict[str, Any]] = {}
    for name in schema_names:
        try:
            schema = _load_json(control_dir / name)
            Draft202012Validator.check_schema(schema)
            schemas[name] = schema
        except Exception as exc:  # report all control errors in one run
            errors.append(f"{name}: {exc}")

    examples = {
        "NOTEBOOK_EXECUTION_CONTRACT.schema.json": observed_execution_example(),
        "STAGE_MANIFEST.schema.json": observed_manifest_example(),
        "STAGE_METRICS.schema.json": observed_metrics_example(),
        "CURRENT_RUN_MANIFEST.schema.json": {
            "manifestVersion": "current-run-manifest-v1",
            "currentRunId": "MASTER_20260806_01",
            "stageId": "A2-00-CONTRACT-AUDIT",
            "agentId": "P4-A2-PIPELINE",
            "status": "PASS",
            "sourceNotebookPath": "pipeline/notebooks/00ContractAndInputAudit.ipynb",
            "sourceNotebookSha256": "1" * 64,
            "sourceGitRef": "HEAD",
            "sourceGitBlobSha": "2" * 40,
            "parameterSha256": "3" * 64,
            "artifactRoot": "crawl/runs/notebooks/current/A2-00",
            "executedNotebookPath": "crawl/runs/notebooks/current/executed/A2-00.ipynb",
            "executedNotebookSha256": "4" * 64,
            "nativeStageManifestPath": "crawl/runs/notebooks/current/A2-00/stage_manifest.json",
            "nativeStageManifestSha256": "5" * 64,
            "createdAt": "2026-08-06T16:01:00+09:00",
            "errors": [],
        },
    }
    for name, instance in examples.items():
        if name not in schemas:
            continue
        validator = Draft202012Validator(schemas[name], format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
            errors.append(f"{name} example: {error.message}")

    try:
        registry = _load_registry(control_dir / "NOTEBOOK_STAGE_REGISTRY.yaml")
    except Exception as exc:
        errors.append(f"NOTEBOOK_STAGE_REGISTRY.yaml: {exc}")
        registry = {}

    stages = registry.get("stages", [])
    if not isinstance(stages, list):
        errors.append("registry stages must be a list")
        stages = []
    stage_ids = [stage.get("stageId") for stage in stages if isinstance(stage, dict)]
    if set(stage_ids) != set(EXPECTED_STAGE_IDS) or len(stage_ids) != len(EXPECTED_STAGE_IDS):
        errors.append(f"stage ID set mismatch: expected 28, got {len(stage_ids)}")
    if len(stage_ids) != len(set(stage_ids)):
        errors.append("stage IDs are not unique")

    if registry.get("requiredTerminationArtifacts") != EXPECTED_TERMINATION_ARTIFACTS:
        errors.append("required termination artifacts mismatch")

    expected_defaults = {
        "runMode": "observed-dev",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "randomSeed": 20260806,
    }
    if registry.get("m1ObservedDefaults") != expected_defaults:
        errors.append("M1 observed defaults mismatch")

    data_policy = registry.get("dataPolicy", {})
    if data_policy.get("canonicalStorage") != "DUCKDB_PARQUET":
        errors.append("DuckDB/Parquet must be canonical")
    if data_policy.get("csvPurpose") != "HUMAN_INSPECTION_EXPORT":
        errors.append("CSV must be an inspection export")
    if data_policy.get("eligibilityColumns") != observed_execution_example()["eligibilityColumns"]:
        errors.append("canonical eligibility columns mismatch")
    if data_policy.get("highDemandScore") != "ALL_NULL":
        errors.append("highDemandScore policy must be ALL_NULL")

    ksa = registry.get("ncsM1Policy", {}).get("ksaDecision", {})
    if ksa != {
        "decisionId": "D-023",
        "status": "PROVISIONAL",
        "mode": "OPTIONAL_ENRICHMENT",
        "blocksM1": False,
    }:
        errors.append("D-023 provisional KSA policy mismatch")

    generation = registry.get("notebookGeneration", {})
    expected_generation_flags = {
        "registryDriven": True,
        "topologicalOrderFromUpstream": True,
        "deterministicCellIds": True,
        "parameterCellFirst": True,
        "sourceOutputCount": 0,
    }
    for key, value in expected_generation_flags.items():
        if generation.get(key) != value:
            errors.append(f"notebook generation rule mismatch: {key}")

    stage_set = set(stage_ids)
    notebook_paths: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict):
            errors.append("stage entry must be a mapping")
            continue
        stage_id = stage.get("stageId", "<missing>")
        path = stage.get("notebookPath")
        if not isinstance(path, str) or not _is_relative_repo_path(path) or not path.endswith(".ipynb"):
            errors.append(f"{stage_id}: invalid relative Notebook path")
        else:
            notebook_paths.append(path)
        upstream = stage.get("upstreamStages")
        if not isinstance(upstream, list) or any(item not in stage_set for item in upstream):
            errors.append(f"{stage_id}: unknown upstream stage")
        modes = stage.get("allowedRunModes")
        if not isinstance(modes, list) or not modes or any(
            mode not in {"fixture", "observed-dev", "production"} for mode in modes
        ):
            errors.append(f"{stage_id}: invalid allowed run modes")
        for required in ("ownerAgent", "inputArtifacts", "outputArtifacts", "requiredGate", "producedGate", "schemaVersion"):
            if required not in stage:
                errors.append(f"{stage_id}: missing {required}")
    if len(notebook_paths) != len(set(notebook_paths)):
        errors.append("Notebook paths are not unique")
    try:
        topological = deterministic_topological_order(stages)
        position = {stage_id: index for index, stage_id in enumerate(topological)}
        for producer in ("A4-00-NCS-SOURCE", "A4-01-CODESET"):
            if position[producer] >= position["A2-08-NCS-LOAD"]:
                errors.append(f"topological order does not place {producer} before A2-08-NCS-LOAD")
        for producer in ("A4-03-MAP-OBSERVED", "A4-04-EXPORT"):
            if position[producer] >= position["A2-09-NCS-MAP"]:
                errors.append(f"topological order does not place {producer} before A2-09-NCS-MAP")
    except ValueError as exc:
        errors.append(f"stage dependency graph: {exc}")

    try:
        runtime = _load_json(control_dir / "NOTEBOOK_RUNTIME_LOCK.json")
        packages = runtime.get("packages", {})
        if runtime.get("lockVersion") != "p4-notebook-runtime-lock-v1":
            errors.append("runtime lock version mismatch")
        if runtime.get("executionEngine") != "nbclient":
            errors.append("runtime execution engine must be nbclient")
        if set(packages) != EXPECTED_RUNTIME_PACKAGES or any(not str(value).startswith("==") for value in packages.values()):
            errors.append("runtime package lock must declare exact required versions")
        papermill = runtime.get("papermill", {})
        if papermill != {"status": "NOT_REQUIRED", "reason": "execution-engine-is-nbclient"}:
            errors.append("papermill must be explicitly NOT_REQUIRED")
    except Exception as exc:
        errors.append(f"NOTEBOOK_RUNTIME_LOCK.json: {exc}")

    try:
        gate_columns, gates = _load_gates(control_dir / "NOTEBOOK_GATE_MATRIX.csv")
    except Exception as exc:
        errors.append(f"NOTEBOOK_GATE_MATRIX.csv: {exc}")
        gate_columns, gates = [], []
    if gate_columns != GATE_COLUMNS:
        errors.append("gate matrix columns mismatch")
    gate_ids = [row.get("gateId") for row in gates]
    if gate_ids != EXPECTED_GATE_IDS:
        errors.append(f"gate IDs/order mismatch: expected 18, got {len(gate_ids)}")
    if len(gate_ids) != len(set(gate_ids)):
        errors.append("gate IDs are not unique")
    for row in gates:
        producer = row.get("producer", "")
        if producer not in stage_set and producer not in MANUAL_GATE_PRODUCERS:
            errors.append(f"{row.get('gateId')}: unknown producer {producer}")
        if any(row.get(column, "") == "" for column in GATE_COLUMNS):
            errors.append(f"{row.get('gateId')}: empty required field")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--control-dir",
        type=Path,
        default=CONTROL_DIR,
        help="directory containing the control artifacts (read-only)",
    )
    args = parser.parse_args()
    errors = validate_control(args.control_dir)
    if errors:
        print("CONTROL_VALIDATION_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("CONTROL_VALIDATION_PASS stages=28 gates=18 schemas=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
