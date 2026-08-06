"""Single authority for the unified 23-stage DAG and runtime evidence rules."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "A1-00-RECOVER": (),
    "A1-01-INDEX": ("A1-00-RECOVER",),
    "A1-02-DETAIL": ("A1-01-INDEX",),
    "A1-03-ASSET": ("A1-02-DETAIL",),
    "A1-04-RELEASE": ("A1-03-ASSET",),
    "A2-00-CONTRACT": ("A1-04-RELEASE",),
    "A2-01-LOAD": ("A2-00-CONTRACT",),
    "A2-02-NORMALIZE": ("A2-01-LOAD",),
    "A2-03-OCR": ("A2-02-NORMALIZE",),
    "A2-04-TRACK": ("A2-03-OCR",),
    "A2-05-REQUIREMENT": ("A2-04-TRACK",),
    "A2-06-DEDUP": ("A2-02-NORMALIZE",),
    "A2-07-LABEL": ("A2-05-REQUIREMENT",),
    "A4-00-NCS-SOURCE": ("A2-00-CONTRACT",),
    "A4-01-CODESET": ("A4-00-NCS-SOURCE",),
    "A4-02-RETRIEVAL": ("A4-01-CODESET",),
    "A4-03-MAP-OBSERVED": ("A2-05-REQUIREMENT", "A4-02-RETRIEVAL"),
    "A4-04-EXPORT": ("A4-03-MAP-OBSERVED",),
    "A2-08-NCS-LOAD": ("A4-00-NCS-SOURCE", "A4-01-CODESET"),
    "A2-09-NCS-MAP": ("A2-08-NCS-LOAD", "A4-03-MAP-OBSERVED", "A4-04-EXPORT"),
    "A2-10-EXPORT": ("A2-05-REQUIREMENT", "A2-06-DEDUP", "A2-07-LABEL", "A2-09-NCS-MAP"),
    "A2-11-QA": ("A2-10-EXPORT",),
    "A4-05-EVALUATE": ("A4-04-EXPORT",),
}

# One valid deterministic schedule. Dependencies, not adjacency, define the DAG.
EXECUTION_ORDER: tuple[str, ...] = (
    "A1-00-RECOVER", "A1-01-INDEX", "A1-02-DETAIL", "A1-03-ASSET", "A1-04-RELEASE",
    "A2-00-CONTRACT", "A2-01-LOAD", "A2-02-NORMALIZE",
    "A4-00-NCS-SOURCE", "A4-01-CODESET", "A4-02-RETRIEVAL",
    "A2-03-OCR", "A2-04-TRACK", "A2-05-REQUIREMENT", "A2-06-DEDUP", "A2-07-LABEL",
    "A4-03-MAP-OBSERVED", "A4-04-EXPORT", "A2-08-NCS-LOAD", "A2-09-NCS-MAP",
    "A4-05-EVALUATE", "A2-10-EXPORT", "A2-11-QA",
)

PLACEHOLDER_TIMESTAMPS = {
    "1970-01-01T00:00:00Z",
    "2000-01-01T00:00:00Z",
    "2026-08-06T00:00:00+09:00",
    "2026-08-05T15:00:00Z",
}

RUNTIME_REQUIRED_FIELDS = (
    "startedAtUtc", "completedAtUtc", "executionHostOrRunnerId", "executionCommandSha256",
    "sourceNotebookSha256", "moduleBlobSha256", "inputManifestSha256", "outputManifestSha256",
    "executionOrder", "dependencyStageIds",
)


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def validate_registry_dependencies(registry_stages: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    rows = {str(row.get("stageId")): row for row in registry_stages}
    if set(rows) != set(STAGE_DEPENDENCIES):
        errors.append("DAG_STAGE_SET_MISMATCH")
    for stage_id, expected in STAGE_DEPENDENCIES.items():
        actual = tuple(rows.get(stage_id, {}).get("dependencyStageIds") or ())
        if actual != expected:
            errors.append(f"DAG_DEPENDENCY_MISMATCH:{stage_id}")
    return errors


def validate_topology_and_runtime(manifests: Mapping[str, Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    if set(manifests) != set(STAGE_DEPENDENCIES):
        errors.append("RUNTIME_STAGE_SET_MISMATCH")
        return errors
    for stage_id, manifest in manifests.items():
        for field in RUNTIME_REQUIRED_FIELDS:
            if field not in manifest or manifest[field] in (None, ""):
                errors.append(f"RUNTIME_FIELD_MISSING:{stage_id}:{field}")
        dependencies = tuple(manifest.get("dependencyStageIds") or ())
        if dependencies != STAGE_DEPENDENCIES[stage_id]:
            errors.append(f"RUNTIME_DEPENDENCY_MISMATCH:{stage_id}")
        try:
            started = parse_timestamp(manifest.get("startedAtUtc"))
            completed = parse_timestamp(manifest.get("completedAtUtc"))
        except (TypeError, ValueError):
            errors.append(f"RUNTIME_TIMESTAMP_INVALID:{stage_id}")
            continue
        if manifest.get("startedAtUtc") in PLACEHOLDER_TIMESTAMPS or manifest.get("completedAtUtc") in PLACEHOLDER_TIMESTAMPS:
            errors.append(f"FIXED_TIMESTAMP:{stage_id}")
        if completed < started:
            errors.append(f"RUNTIME_TIMESTAMP_REVERSED:{stage_id}")
        if manifest.get("timestampSource") != "EXECUTION_WRAPPER_CAPTURED":
            errors.append(f"TIMESTAMP_SOURCE_INVALID:{stage_id}")

    for consumer, producers in STAGE_DEPENDENCIES.items():
        consumer_manifest = manifests[consumer]
        consumer_order = int(consumer_manifest.get("executionOrder") or -1)
        try:
            consumer_started = parse_timestamp(consumer_manifest.get("startedAtUtc"))
        except (TypeError, ValueError):
            continue
        for producer in producers:
            producer_manifest = manifests[producer]
            producer_order = int(producer_manifest.get("executionOrder") or -1)
            if producer_order >= consumer_order:
                errors.append(f"TOPOLOGICAL_ORDER_VIOLATION:{producer}->{consumer}")
            try:
                producer_completed = parse_timestamp(producer_manifest.get("completedAtUtc"))
            except (TypeError, ValueError):
                continue
            if producer_completed > consumer_started:
                errors.append(f"RUNTIME_ORDER_VIOLATION:{producer}->{consumer}")
    return errors


def ncs_binding_errors(manifests: Mapping[str, Mapping[str, Any]]) -> list[str]:
    expected = {
        "A2-08-NCS-LOAD": ("A4-00-NCS-SOURCE", "A4-01-CODESET"),
        "A2-09-NCS-MAP": ("A2-08-NCS-LOAD", "A4-03-MAP-OBSERVED", "A4-04-EXPORT"),
    }
    return [
        f"NCS_CONSUMER_PRODUCER_MISMATCH:{stage_id}"
        for stage_id, dependencies in expected.items()
        if tuple(manifests.get(stage_id, {}).get("dependencyStageIds") or ()) != dependencies
    ]


if len(EXECUTION_ORDER) != 23 or set(EXECUTION_ORDER) != set(STAGE_DEPENDENCIES):
    raise AssertionError("unified reconciliation execution order must cover exactly 23 stages")
