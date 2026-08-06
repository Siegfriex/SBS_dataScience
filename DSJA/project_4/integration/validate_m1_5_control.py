#!/usr/bin/env python3
"""Fail-closed validation for the P4 M1.5 v4.0 control plane."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from jsonschema import Draft202012Validator


ALLOWED_STATUSES = (
    "PASS",
    "PASS_WITH_FINDINGS",
    "PARTIAL",
    "BLOCKED",
    "NOT_STARTED",
    "NOT_EVALUATED",
    "FAIL",
)
SUCCESS_STATUSES = frozenset({"PASS", "PASS_WITH_FINDINGS"})
EXPECTED_STAGE_IDS = frozenset({"M1.5-P", "M1.5-0", "M1.5-A", "M1.5-B", "M1.5-C", "M1.5-D"})
EXPECTED_SCHEMA_FILES = frozenset(
    {
        "api_endpoint_contract.schema.json",
        "api_probe_run.schema.json",
        "source_block.schema.json",
        "ocr_quality.schema.json",
        "semantic_chunk.schema.json",
        "ncs_node.schema.json",
        "ncs_edge.schema.json",
        "ncs_duty_unit_bridge.schema.json",
        "ncs_external_code_crosswalk.schema.json",
        "candidate_packet.schema.json",
        "reference_label.schema.json",
        "calibration_model.schema.json",
    }
)


class ControlValidationError(ValueError):
    """Raised when the control plane cannot be trusted."""


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ControlValidationError(f"YAML root must be an object: {path}")
    return payload


def _require_exact_status_vocabulary(payload: Mapping[str, Any], label: str) -> None:
    observed = payload.get("statusVocabulary")
    if not isinstance(observed, list) or tuple(observed) != ALLOWED_STATUSES:
        raise ControlValidationError(f"{label} status vocabulary must be exactly {ALLOWED_STATUSES}")


def validate_api_registry(payload: Mapping[str, Any]) -> dict[str, int]:
    _require_exact_status_vocabulary(payload, "API registry")
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ControlValidationError("API registry requires endpoint rows")
    identifiers: set[str] = set()
    required_cases = {
        "SUCCESS_MINIMAL",
        "SUCCESS_PAGINATED",
        "EMPTY_VALID",
        "INVALID_PARAMETER",
        "AUTH_MISSING",
        "AUTH_INVALID",
        "FORMAT_VARIANT",
    }
    for endpoint in endpoints:
        identifier = str(endpoint.get("apiContractId") or "")
        if not identifier or identifier in identifiers:
            raise ControlValidationError(f"duplicate or empty apiContractId: {identifier!r}")
        identifiers.add(identifier)
        if endpoint.get("probeStatus") not in ALLOWED_STATUSES:
            raise ControlValidationError(f"invalid probeStatus for {identifier}")
        if endpoint.get("contractStatus") not in {"PROVISIONAL", "PROBED", "FROZEN", "DRIFTED", "RETIRED"}:
            raise ControlValidationError(f"invalid contractStatus for {identifier}")
        if set(endpoint.get("requiredProbeCases") or []) != required_cases:
            raise ControlValidationError(f"incomplete requiredProbeCases for {identifier}")
        credential = str(endpoint.get("credentialEnv") or "")
        if not credential or any(token in credential.casefold() for token in ("=", "bearer ", "secret:")):
            raise ControlValidationError(f"credentialEnv must name an environment variable only: {identifier}")
    return {"endpointCount": len(endpoints)}


def _stage_index(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stages = payload.get("stages")
    if not isinstance(stages, list):
        raise ControlValidationError("stage registry requires a stages list")
    result: dict[str, dict[str, Any]] = {}
    for stage in stages:
        stage_id = str(stage.get("stageId") or "")
        if not stage_id or stage_id in result:
            raise ControlValidationError(f"duplicate or empty stageId: {stage_id!r}")
        result[stage_id] = stage
    if set(result) != EXPECTED_STAGE_IDS:
        raise ControlValidationError(f"stage IDs must be exactly {sorted(EXPECTED_STAGE_IDS)}")
    return result


def _topological_order(stages: Mapping[str, Mapping[str, Any]]) -> list[str]:
    indegree = {stage_id: 0 for stage_id in stages}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for stage_id, stage in stages.items():
        dependencies = stage.get("dependencies") or []
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)):
            raise ControlValidationError(f"dependencies must be a unique list: {stage_id}")
        for dependency in dependencies:
            if dependency not in stages:
                raise ControlValidationError(f"unknown dependency {dependency!r} for {stage_id}")
            indegree[stage_id] += 1
            outgoing[dependency].append(stage_id)
    queue = deque(sorted(stage_id for stage_id, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in sorted(outgoing[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(ordered) != len(stages):
        raise ControlValidationError("dependency cycle detected")
    return ordered


def validate_stage_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_status_vocabulary(payload, "stage registry")
    rules = payload.get("failClosedRules") or {}
    expected_rules = {
        "unknownDependency": "FAIL",
        "dependencyCycle": "FAIL",
        "dependencyUnmet": "BLOCKED",
        "validationError": "FAIL",
        "emptyEvidence": "NOT_EVALUATED",
    }
    for key, expected in expected_rules.items():
        if rules.get(key) != expected:
            raise ControlValidationError(f"fail-closed rule {key} must be {expected}")
    if set(rules.get("successStatuses") or []) != SUCCESS_STATUSES:
        raise ControlValidationError("successStatuses must be PASS and PASS_WITH_FINDINGS")
    stages = _stage_index(payload)
    gates: set[str] = set()
    for stage_id, stage in stages.items():
        if stage.get("initialStatus") not in ALLOWED_STATUSES:
            raise ControlValidationError(f"invalid initialStatus for {stage_id}")
        stage_gates = stage.get("gates")
        if not isinstance(stage_gates, list) or not stage_gates:
            raise ControlValidationError(f"stage has no gates: {stage_id}")
        duplicates = gates.intersection(stage_gates)
        if duplicates:
            raise ControlValidationError(f"gate IDs must be globally unique: {sorted(duplicates)}")
        gates.update(stage_gates)
    order = _topological_order(stages)
    return {"stageCount": len(stages), "gateCount": len(gates), "topologicalOrder": order}


def validate_dependency_graph(payload: Mapping[str, Any], stage_payload: Mapping[str, Any]) -> dict[str, int]:
    stages = _stage_index(stage_payload)
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or set(nodes) != set(stages) or len(nodes) != len(set(nodes)):
        raise ControlValidationError("dependency graph nodes do not match stage registry")
    declared_edges = {
        (dependency, stage_id)
        for stage_id, stage in stages.items()
        for dependency in stage.get("dependencies") or []
    }
    graph_edges: set[tuple[str, str]] = set()
    for edge in payload.get("edges") or []:
        pair = (edge.get("from"), edge.get("to"))
        if pair[0] not in stages or pair[1] not in stages or pair in graph_edges:
            raise ControlValidationError(f"invalid dependency graph edge: {pair}")
        graph_edges.add(pair)
    if graph_edges != declared_edges:
        raise ControlValidationError("dependency graph edges do not match stage registry")
    flattened = [stage for group in payload.get("evaluationOrder") or [] for stage in group]
    if set(flattened) != set(stages) or len(flattened) != len(set(flattened)):
        raise ControlValidationError("evaluationOrder must contain every stage exactly once")
    positions = {stage: index for index, group in enumerate(payload["evaluationOrder"]) for stage in group}
    if any(positions[source] >= positions[target] for source, target in graph_edges):
        raise ControlValidationError("evaluationOrder violates a dependency")
    return {"nodeCount": len(nodes), "edgeCount": len(graph_edges)}


def _read_gate_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_gate_matrix(rows: Sequence[Mapping[str, str]], stage_payload: Mapping[str, Any]) -> dict[str, int]:
    stages = _stage_index(stage_payload)
    expected = {(stage_id, gate) for stage_id, stage in stages.items() for gate in stage["gates"]}
    observed: set[tuple[str, str]] = set()
    status_columns = ("emptyEvidenceStatus", "dependencyUnmetStatus", "validationErrorStatus", "initialStatus")
    for row in rows:
        key = (str(row.get("stageId") or ""), str(row.get("gateId") or ""))
        if key in observed:
            raise ControlValidationError(f"duplicate gate matrix row: {key}")
        observed.add(key)
        if key not in expected:
            raise ControlValidationError(f"unknown stage/gate pair: {key}")
        if any(row.get(column) not in ALLOWED_STATUSES for column in status_columns):
            raise ControlValidationError(f"invalid gate status for {key}")
        if row.get("emptyEvidenceStatus") != "NOT_EVALUATED":
            raise ControlValidationError(f"empty evidence must be NOT_EVALUATED: {key}")
        if row.get("dependencyUnmetStatus") != "BLOCKED" or row.get("validationErrorStatus") != "FAIL":
            raise ControlValidationError(f"fail-closed status mismatch: {key}")
        if int(row.get("minEvidenceCount") or 0) < 1:
            raise ControlValidationError(f"gate must require evidence: {key}")
    if observed != expected:
        raise ControlValidationError(f"gate matrix coverage mismatch: missing={sorted(expected - observed)}")
    return {"gateRowCount": len(rows)}


def validate_schemas(contract_root: Path) -> dict[str, int]:
    manifest_path = contract_root / "AUTHORITY_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("baseContractVersion") != "2.1.2" or manifest.get("baseContractMutationAllowed") is not False:
        raise ControlValidationError("semantic addendum must not mutate P4_CONTRACT_v2.1.2")
    declared = {Path(path).name for path in manifest.get("schemas") or []}
    if declared != EXPECTED_SCHEMA_FILES:
        raise ControlValidationError("authority manifest schema inventory mismatch")
    schema_root = contract_root / "schemas"
    actual = {path.name for path in schema_root.glob("*.schema.json")}
    if actual != EXPECTED_SCHEMA_FILES:
        raise ControlValidationError(f"schema file inventory mismatch: {sorted(actual)}")
    for path in sorted(schema_root.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ControlValidationError(f"schema is not Draft 2020-12: {path.name}")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise ControlValidationError(f"invalid JSON Schema {path.name}: {exc}") from exc
    return {"schemaCount": len(actual)}


def evaluate_gate_status(
    claimed_status: str,
    evidence_count: int,
    dependency_statuses: Mapping[str, str],
    required_dependencies: Sequence[str] = (),
    validation_errors: Sequence[str] = (),
) -> str:
    """Apply deterministic runtime precedence without manufacturing PASS."""

    if validation_errors:
        return "FAIL"
    if any(dependency not in dependency_statuses for dependency in required_dependencies):
        return "FAIL"
    if any(status not in ALLOWED_STATUSES for status in dependency_statuses.values()):
        return "FAIL"
    if any(dependency_statuses[dependency] not in SUCCESS_STATUSES for dependency in required_dependencies):
        return "BLOCKED"
    if evidence_count <= 0:
        return "NOT_EVALUATED"
    if claimed_status not in ALLOWED_STATUSES:
        return "FAIL"
    return claimed_status


def validate_control_root(project_root: Path) -> dict[str, Any]:
    integration = project_root / "integration"
    contract_root = project_root / "shared/contracts/semantic_ncs_reference/v4.0"
    stage_path = integration / "SEMANTIC_STAGE_REGISTRY.yaml"
    report_copy = project_root / "reports/m1_5_v4_implementation/P4_M1_5_STAGE_REGISTRY.yaml"
    stage_payload = _load_yaml(stage_path)
    results = {
        "schemas": validate_schemas(contract_root),
        "apiRegistry": validate_api_registry(_load_yaml(integration / "API_CONTRACT_REGISTRY.yaml")),
        "stageRegistry": validate_stage_registry(stage_payload),
        "dependencyGraph": validate_dependency_graph(_load_yaml(integration / "STAGE_DEPENDENCY_GRAPH.yaml"), stage_payload),
        "gateMatrix": validate_gate_matrix(_read_gate_rows(integration / "GATE_MATRIX.csv"), stage_payload),
    }
    if stage_path.read_bytes() != report_copy.read_bytes():
        raise ControlValidationError("reported stage registry is not byte-synchronized")
    results["reportedRegistry"] = {"byteSynchronized": True}
    return {"status": "PASS", "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = validate_control_root(args.project_root.resolve())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
