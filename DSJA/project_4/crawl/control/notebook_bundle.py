"""Build, execute, and audit the P4 Notebook-First observed-development bundle."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import nbformat
from nbclient import NotebookClient


CONTRACT_VERSION = "2.1.2"
DATA_VERSION = "observed-dev-20260806.1"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"
MASTER_RUN_ID = "MASTER_20260806_01"

NOTEBOOK_INDEX: tuple[tuple[str, str, str], ...] = (
    ("P4-A1-SOURCE", "A1-00-RECOVER", "crawl/notebooks/00RecoverSourceState.ipynb"),
    ("P4-A1-SOURCE", "A1-01-INDEX", "crawl/notebooks/01CollectLinkareerIndex.ipynb"),
    ("P4-A1-SOURCE", "A1-02-DETAIL", "crawl/notebooks/02CollectPostingDetail.ipynb"),
    ("P4-A1-SOURCE", "A1-03-ASSET", "crawl/notebooks/03CollectPostingAssets.ipynb"),
    ("P4-A1-SOURCE", "A1-04-RELEASE", "crawl/notebooks/04BuildCrawlRelease.ipynb"),
    ("P4-A2-PIPELINE", "A2-00-CONTRACT-AUDIT", "pipeline/notebooks/00ContractAndInputAudit.ipynb"),
    ("P4-A2-PIPELINE", "A2-01-LOAD", "pipeline/notebooks/01LoadCrawlRelease.ipynb"),
    ("P4-A2-PIPELINE", "A2-02-PARSE", "pipeline/notebooks/02ParseAndNormalize.ipynb"),
    ("P4-A2-PIPELINE", "A2-03-OCR", "pipeline/notebooks/03OcrAndSectionRecovery.ipynb"),
    ("P4-A2-PIPELINE", "A2-04-TRACK", "pipeline/notebooks/04SplitTracks.ipynb"),
    ("P4-A2-PIPELINE", "A2-05-REQUIREMENT", "pipeline/notebooks/05ExtractRequirements.ipynb"),
    ("P4-A2-PIPELINE", "A2-06-DEDUP", "pipeline/notebooks/06Deduplicate90Days.ipynb"),
    ("P4-A2-PIPELINE", "A2-07-LABEL", "pipeline/notebooks/07LabelCareerAccess.ipynb"),
    ("P4-A4-NCS", "A4-00-NCS-SOURCE", "ncs_mapping/notebooks/00NcsSourceAudit.ipynb"),
    ("P4-A4-NCS", "A4-01-CODESET", "ncs_mapping/notebooks/01BuildCoreAiItCodeSet.ipynb"),
    ("P4-A4-NCS", "A4-02-RETRIEVAL", "ncs_mapping/notebooks/02BuildNcsRetrievalIndex.ipynb"),
    ("P4-A4-NCS", "A4-03-MAP-OBSERVED", "ncs_mapping/notebooks/03MapObservedDuties.ipynb"),
    ("P4-A4-NCS", "A4-04-EXPORT", "ncs_mapping/notebooks/04ExportNcsMappingCsv.ipynb"),
    ("P4-A4-NCS", "A4-05-EVALUATE", "ncs_mapping/notebooks/05EvaluateNcsMapping.ipynb"),
    ("P4-A2-PIPELINE", "A2-08-NCS-LOAD", "pipeline/notebooks/08LoadAndPrepareNcs.ipynb"),
    ("P4-A2-PIPELINE", "A2-09-NCS-MAP", "pipeline/notebooks/09MapPostingToNcs.ipynb"),
    ("P4-A2-PIPELINE", "A2-10-EXPORT", "pipeline/notebooks/10ExportPreprocessedCsv.ipynb"),
    ("P4-A2-PIPELINE", "A2-11-EXPORT-QA", "pipeline/notebooks/11PreprocessedDataQa.ipynb"),
    ("P4-A3-CONTROL", "A3-MASTER", "crawl/notebooks/P4_Notebook_First_Master.ipynb"),
)

# Public compatibility name. Execution order is validated against the registry
# by ``notebook_plan`` before any child kernel starts.
NOTEBOOKS = NOTEBOOK_INDEX

PARAMETER_NAMES = (
    "RUN_MODE", "AGENT_ID", "STAGE_ID", "CONTRACT_VERSION", "SCHEMA_VERSION",
    "DATA_VERSION", "CRAWL_RELEASE_ID", "AS_OF_DATE", "INPUT_MANIFEST_PATH",
    "OUTPUT_ROOT", "RANDOM_SEED", "FAIL_ON_GATE", "EMPIRICAL_ANALYSIS_ALLOWED",
)

TITLE_SPEC_FIELDS = ("목적", "담당 Agent", "Stage ID", "입력", "처리", "출력", "선행 Gate", "후속 활용")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_project_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml").is_file():
            return candidate
        nested = candidate / "DSJA/project_4"
        if (nested / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml").is_file():
            return nested.resolve()
    raise FileNotFoundError("P4 project root with crawl/control registry was not found")


def git_head(project_root: str | Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(project_root), check=True,
        text=True, capture_output=True,
    )
    return result.stdout.strip()


def git_branch(project_root: str | Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=Path(project_root), check=True,
        text=True, capture_output=True,
    )
    return result.stdout.strip() or "DETACHED"


def source_blob_provenance(
    project_root: str | Path,
    notebook_paths: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Bind every crawl source Notebook byte stream to a tracked Git blob."""

    root = Path(project_root).resolve()
    paths = list(notebook_paths or [
        relative for _, _, relative in NOTEBOOK_INDEX if relative.startswith("crawl/notebooks/")
    ])
    rows: list[dict[str, Any]] = []
    branch = git_branch(root)
    head = git_head(root)
    git_prefix = subprocess.run(
        ["git", "rev-parse", "--show-prefix"], cwd=root, check=True,
        text=True, capture_output=True,
    ).stdout.strip()
    for relative in paths:
        path = root / relative
        repo_relative = f"{git_prefix}{relative}"
        exists = path.is_file()
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=root,
            text=True,
            capture_output=True,
        ).returncode == 0
        git_blob_id = ""
        working_blob_id = ""
        source_commit = ""
        if exists:
            working_blob_id = subprocess.run(
                ["git", "hash-object", "--", relative], cwd=root, check=True,
                text=True, capture_output=True,
            ).stdout.strip()
        if tracked:
            result = subprocess.run(
                ["git", "rev-parse", f"HEAD:{repo_relative}"], cwd=root,
                text=True, capture_output=True,
            )
            if result.returncode == 0:
                git_blob_id = result.stdout.strip()
            source_commit = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", relative], cwd=root,
                check=True, text=True, capture_output=True,
            ).stdout.strip()
        rows.append({
            "sourcePath": relative,
            "sourceFileSha256": sha256_file(path) if exists else "",
            "gitBlobId": git_blob_id,
            "workingTreeBlobId": working_blob_id,
            "sourceBranch": branch,
            "sourceCommit": source_commit or head,
            "tracked": tracked,
            "workingTreeMatchesGitBlob": bool(tracked and git_blob_id == working_blob_id),
        })
    return rows


def load_stage_registry(project_root: str | Path) -> dict[str, Any]:
    import yaml

    path = Path(project_root) / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def notebook_plan(
    project_root: str | Path,
    *,
    include_master: bool = False,
) -> tuple[tuple[str, str, str], ...]:
    """Return a stable topological plan for the implemented Notebook bundle."""

    registry = load_stage_registry(project_root)
    selected = {
        stage_id: (owner, stage_id, path)
        for owner, stage_id, path in NOTEBOOK_INDEX
        if include_master or stage_id != "A3-MASTER"
    }
    registered = {stage["stageId"]: stage for stage in registry["stages"]}
    missing = sorted(set(selected).difference(registered).difference({"A3-MASTER"}))
    if missing:
        raise ValueError(f"planned stages absent from registry: {missing}")

    dependencies: dict[str, set[str]] = {}
    for stage_id in selected:
        if stage_id == "A3-MASTER":
            dependencies[stage_id] = set(selected).difference({stage_id})
        else:
            dependencies[stage_id] = {
                upstream
                for upstream in registered[stage_id].get("upstreamStages", [])
                if upstream in selected
            }

    rank = {stage_id: index for index, (_, stage_id, _) in enumerate(NOTEBOOK_INDEX)}
    ordered: list[tuple[str, str, str]] = []
    remaining = set(selected)
    completed: set[str] = set()
    while remaining:
        ready = sorted(
            (stage_id for stage_id in remaining if dependencies[stage_id] <= completed),
            key=lambda stage_id: (rank[stage_id], stage_id),
        )
        if not ready:
            unresolved = {stage_id: sorted(dependencies[stage_id] - completed) for stage_id in sorted(remaining)}
            raise ValueError(f"cyclic or unresolved Notebook dependencies: {unresolved}")
        for stage_id in ready:
            ordered.append(selected[stage_id])
            completed.add(stage_id)
            remaining.remove(stage_id)
    return tuple(ordered)


def dependency_order_audit(
    project_root: str | Path,
    plan: Sequence[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Report every current plan edge and whether producer precedes consumer."""

    actual = tuple(plan or notebook_plan(project_root))
    positions = {stage_id: index for index, (_, stage_id, _) in enumerate(actual)}
    registry = load_stage_registry(project_root)
    rows: list[dict[str, Any]] = []
    for stage in registry["stages"]:
        consumer = stage["stageId"]
        if consumer not in positions:
            continue
        for producer in stage.get("upstreamStages", []):
            if producer not in positions:
                continue
            rows.append({
                "producerStageId": producer,
                "consumerStageId": consumer,
                "producerOrder": positions[producer],
                "consumerOrder": positions[consumer],
                "status": "PASS" if positions[producer] < positions[consumer] else "FAIL",
            })
    return rows


def repository_architecture(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root)
    rows = []
    for owner, stage_id, relative in NOTEBOOK_INDEX:
        path = root / relative
        rows.append({
            "agentId": owner,
            "stageId": stage_id,
            "notebook": relative,
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
        })
    return rows


def _code_tree(notebook: Any) -> tuple[list[ast.AST], list[str]]:
    trees: list[ast.AST] = []
    errors: list[str] = []
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        try:
            trees.append(ast.parse(cell.source))
        except SyntaxError as exc:
            errors.append(f"cell {index}: {exc}")
    return trees, errors


def _module_calls(trees: Iterable[ast.AST]) -> tuple[list[str], list[str]]:
    imports: set[str] = set()
    calls: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Name):
                    calls.add(target.id)
                elif isinstance(target, ast.Attribute):
                    parts = [target.attr]
                    value = target.value
                    while isinstance(value, ast.Attribute):
                        parts.append(value.attr)
                        value = value.value
                    if isinstance(value, ast.Name):
                        parts.append(value.id)
                    calls.add(".".join(reversed(parts)))
    project_imports = sorted(
        name for name in imports
        if name == "p4" or name.startswith("p4.") or name == "p4_crawl" or name.startswith("p4_crawl.")
        or name == "p4_ncs" or name.startswith("p4_ncs.")
        or name.startswith("ncs_mapping") or name.startswith("crawl.control")
    )
    return project_imports, sorted(calls)


def _literal_assignments(source: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return values
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def audit_notebook(path: str | Path, project_root: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    relative = source_path.resolve().relative_to(Path(project_root).resolve()).as_posix()
    row: dict[str, Any] = {
        "notebook": relative,
        "exists": source_path.is_file(),
        "bytes": source_path.stat().st_size if source_path.is_file() else 0,
        "sha256": sha256_file(source_path) if source_path.is_file() else "",
    }
    if not source_path.is_file() or source_path.stat().st_size == 0:
        return {**row, "valid": False, "errors": "missing or zero-byte"}
    try:
        notebook = nbformat.read(source_path, as_version=4)
        nbformat.validate(notebook)
    except Exception as exc:
        return {**row, "valid": False, "errors": f"nbformat: {type(exc).__name__}: {exc}"}
    trees, ast_errors = _code_tree(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    title_first = bool(notebook.cells and notebook.cells[0].cell_type == "markdown")
    title_source = notebook.cells[0].source if title_first else ""
    missing_title_fields = [field for field in TITLE_SPEC_FIELDS if field not in title_source]
    parameter_index = next((index for index, cell in enumerate(notebook.cells) if cell.cell_type == "code"), -1)
    parameter_ok = bool(
        code_cells
        and parameter_index == 1
        and "parameters" in code_cells[0].metadata.get("tags", [])
    )
    parameter_source = code_cells[0].source if code_cells else ""
    missing_parameters = [name for name in PARAMETER_NAMES if name not in parameter_source]
    parameter_values = _literal_assignments(parameter_source)
    expected_parameter_values = {
        "RUN_MODE": "observed-dev", "CONTRACT_VERSION": CONTRACT_VERSION,
        "DATA_VERSION": DATA_VERSION, "CRAWL_RELEASE_ID": CRAWL_RELEASE_ID,
        "AS_OF_DATE": "2026-08-06", "RANDOM_SEED": 20260806,
        "FAIL_ON_GATE": True, "EMPIRICAL_ANALYSIS_ALLOWED": False,
    }
    wrong_parameter_values = {
        name: parameter_values.get(name)
        for name, expected in expected_parameter_values.items()
        if parameter_values.get(name) != expected
    }
    empty_identity_parameters = [
        name for name in ("AGENT_ID", "STAGE_ID", "SCHEMA_VERSION")
        if not parameter_values.get(name)
    ]
    ids = [cell.get("id", "") for cell in notebook.cells]
    duplicate_ids = sorted({cell_id for cell_id in ids if cell_id and ids.count(cell_id) > 1})
    output_count = sum(len(cell.get("outputs", [])) for cell in code_cells)
    execution_count = sum(cell.get("execution_count") is not None for cell in code_cells)
    project_imports, calls = _module_calls(trees)
    has_project_call = bool(project_imports and calls)
    errors = ast_errors[:]
    if not title_first:
        errors.append("cell 0 must be the title/function-spec markdown")
    elif missing_title_fields:
        errors.append("missing title specification fields: " + ",".join(missing_title_fields))
    if not parameter_ok:
        errors.append("cell 1 must be the parameters-tagged first code cell")
    if missing_parameters:
        errors.append("missing parameters: " + ",".join(missing_parameters))
    if wrong_parameter_values:
        errors.append("wrong parameter values: " + json.dumps(wrong_parameter_values, ensure_ascii=False, sort_keys=True))
    if empty_identity_parameters:
        errors.append("empty identity parameters: " + ",".join(empty_identity_parameters))
    if duplicate_ids:
        errors.append("duplicate cell ids: " + ",".join(duplicate_ids))
    if output_count:
        errors.append(f"source output count is {output_count}")
    if execution_count:
        errors.append(f"source execution count is {execution_count}")
    if not has_project_call:
        errors.append("no project module import and call detected")
    return {
        **row,
        "valid": not errors,
        "cells": len(notebook.cells),
        "markdownCells": sum(cell.cell_type == "markdown" for cell in notebook.cells),
        "codeCells": len(code_cells),
        "sourceOutputs": output_count,
        "sourceExecutionCounts": execution_count,
        "titleMarkdownFirst": title_first,
        "titleSpecificationComplete": not missing_title_fields,
        "parameterCellIndex": parameter_index,
        "parameterTag": parameter_ok,
        "parameterContractValues": not wrong_parameter_values and not empty_identity_parameters,
        "duplicateCellIds": len(duplicate_ids),
        "astValid": not ast_errors,
        "projectImports": ";".join(project_imports),
        "moduleCalls": ";".join(calls),
        "actualModuleCall": has_project_call,
        "errors": " | ".join(errors),
    }


def audit_source_bundle(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root)
    metadata = {(relative): (owner, stage) for owner, stage, relative in NOTEBOOK_INDEX}
    rows = []
    for relative, (owner, stage) in metadata.items():
        row = audit_notebook(root / relative, root)
        row.update({"agentId": owner, "stageId": stage})
        rows.append(row)
    return rows


def _parameter_overrides(output_root: Path | None) -> str:
    lines = [
        "# Injected into the executed copy by crawl.control.notebook_bundle",
        "RUN_MODE = 'observed-dev'",
        "FAIL_ON_GATE = True",
        "EMPIRICAL_ANALYSIS_ALLOWED = False",
    ]
    if output_root is not None:
        lines.insert(2, f"OUTPUT_ROOT = {str(output_root)!r}")
    return "\n".join(lines)


def execute_notebook(
    source_path: str | Path,
    project_root: str | Path,
    run_root: str | Path,
    timeout: int = 900,
    kernel_name: str = "python3",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    source = Path(source_path).resolve()
    relative = source.relative_to(root)
    destination = Path(run_root).resolve() / "executed" / relative
    shared_run = Path(run_root).resolve()
    stage_lookup = {item[2]: item[1] for item in NOTEBOOK_INDEX}
    stage_id = stage_lookup[relative.as_posix()]
    owner = next(item[0] for item in NOTEBOOK_INDEX if item[2] == relative.as_posix())
    parameter_output: Path | None
    execution_run_id = ""
    kernel_cwd = root
    child_env: dict[str, str] = {}
    if owner == "P4-A1-SOURCE":
        agent_run = shared_run / "agent_runs" / "AGENT1"
        stage_output = agent_run / stage_id
        parameter_output = agent_run.relative_to(root)
        execution_run_id = agent_run.relative_to(root / "crawl/runs").as_posix()
    elif owner == "P4-A2-PIPELINE":
        agent_run = shared_run / "external_runtime" / "AGENT2"
        stage_name = source.stem
        stage_output = shared_run / "agent_runs" / "AGENT2" / stage_name
        parameter_output = None
        execution_run_id = _relative_portable_path(agent_run, root)
        child_env = {
            "P4_NOTEBOOK_RUN_ROOT": str(agent_run),
            "P4_CRAWL_ROOT": str(root / "crawl"),
            "P4_CONTROL_ROOT": str(root / "crawl/control"),
            "P4_NCS_PROJECT_ROOT": str(root),
            "P4_NCS_HANDOFF_PATH": str(root / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"),
        }
    elif owner == "P4-A4-NCS":
        stage_output = shared_run / "agent_runs" / "AGENT4" / stage_id
        parameter_output = None
        execution_run_id = _relative_portable_path(shared_run / "external_runtime" / "AGENT4", root)
        kernel_cwd = root / "ncs_mapping"
        child_env = {
            "P4_A2_DUTY_HANDOFF": str(root / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"),
            "P4_CONTROL_SCHEMA_DIR": str(root / "crawl/control"),
        }
    else:
        stage_output = shared_run / "stages" / relative.with_suffix("")
        parameter_output = stage_output.relative_to(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_output.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.read(source, as_version=4)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells or "parameters" not in code_cells[0].metadata.get("tags", []):
        raise ValueError(f"parameters cell missing: {relative}")
    code_cells[0].source = code_cells[0].source.rstrip() + "\n\n" + _parameter_overrides(parameter_output)
    started = time.monotonic()
    status = "PASS"
    error = ""
    original_env = {name: os.environ.get(name) for name in child_env}
    os.environ.update(child_env)
    try:
        NotebookClient(
            notebook,
            timeout=timeout,
            kernel_name=kernel_name,
            resources={"metadata": {"path": str(kernel_cwd)}},
            allow_errors=False,
        ).execute()
    except Exception as exc:
        status = "FAIL"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    if status == "PASS" and owner in {"P4-A2-PIPELINE", "P4-A4-NCS"}:
        if owner == "P4-A2-PIPELINE":
            canonical_stage = agent_run / "artifacts" / source.stem
        else:
            canonical_stage = root / "ncs_mapping/data/runs/observed-dev/NCS_MAPPING_OBSERVED_20260806_01" / stage_id
        if canonical_stage.is_dir():
            for name in ("stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"):
                if (canonical_stage / name).is_file():
                    shutil.copy2(canonical_stage / name, stage_output / name)
    nbformat.write(notebook, destination)
    outputs = sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code")
    return {
        "notebook": relative.as_posix(),
        "status": status,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "sourceSha256": sha256_file(source),
        "executedPath": destination.relative_to(root).as_posix() if destination.is_relative_to(root) else str(destination),
        "executedSha256": sha256_file(destination),
        "executedOutputs": outputs,
        "stageOutputRoot": stage_output.relative_to(root).as_posix() if stage_output.is_relative_to(root) else str(stage_output),
        "executionRunId": execution_run_id,
        "error": error.replace("\n", " ")[:2000],
    }


CURRENT_RUN_REQUIRED_FIELDS = (
    "stageId",
    "runId",
    "sourceNotebookSha256",
    "parameterSha256",
    "inputManifestSha256",
    "outputRoot",
    "status",
    "createdAt",
)


def _relative_portable_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"path escapes project root: {path}")
    return resolved.relative_to(project_root.resolve()).as_posix()


def validate_current_run_manifest(
    payload: Mapping[str, Any],
    *,
    expected_stage_id: str,
    expected_run_id: str,
    expected_source_sha256: str,
) -> list[str]:
    errors = [f"missing:{field}" for field in CURRENT_RUN_REQUIRED_FIELDS if not payload.get(field)]
    if payload.get("stageId") != expected_stage_id:
        errors.append("stageId:mismatch")
    if payload.get("runId") != expected_run_id:
        errors.append("runId:mismatch")
    if payload.get("sourceNotebookSha256") != expected_source_sha256:
        errors.append("sourceNotebookSha256:mismatch")
    for field in ("sourceNotebookSha256", "parameterSha256", "inputManifestSha256"):
        value = str(payload.get(field, ""))
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            errors.append(f"{field}:invalid")
    output_root = Path(str(payload.get("outputRoot", "")))
    if output_root.is_absolute() or ".." in output_root.parts:
        errors.append("outputRoot:not-portable")
    if payload.get("status") not in {"SUCCEEDED", "FAILED", "NOT_EVALUATED"}:
        errors.append("status:invalid")
    return sorted(set(errors))


def quarantine_manifest(path: str | Path, quarantine_root: str | Path, *, reason: str) -> Path:
    """Move stale/duplicate evidence without deleting its bytes."""

    source = Path(path)
    destination_root = Path(quarantine_root) / reason
    destination_root.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(source)
    destination = destination_root / f"{source.stem}.{digest[:16]}{source.suffix}"
    if destination.exists() and sha256_file(destination) != digest:
        raise ValueError(f"quarantine collision: {destination}")
    if not destination.exists():
        shutil.move(str(source), str(destination))
    else:
        source.unlink()
    return destination


def bind_current_run_manifests(
    project_root: str | Path,
    run_root: str | Path,
    executions: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """Create exactly one canonical current-run envelope per executed stage."""

    root = Path(project_root).resolve()
    run = Path(run_root).resolve()
    canonical_root = run / "current_run_manifests"
    superseded_root = run / "superseded_manifests"
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for execution in executions:
        stage_id = str(execution["stageId"])
        if stage_id in seen:
            raise ValueError(f"duplicate execution result for stage: {stage_id}")
        seen.add(stage_id)
        source_manifest = root / str(execution["stageOutputRoot"]) / "stage_manifest.json"
        if not source_manifest.is_file():
            raise FileNotFoundError(f"current-run source manifest missing: {source_manifest}")
        source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        source_run_id = str(source_payload.get("runId", ""))
        expected_source_run_id = str(execution.get("executionRunId") or run_id)
        if source_run_id != expected_source_run_id:
            raise ValueError(
                f"stale manifest runId for {stage_id}: {source_run_id!r} != {expected_source_run_id!r}"
            )
        destination = canonical_root / stage_id / "stage_manifest.json"
        if destination.exists():
            quarantine_manifest(destination, superseded_root / stage_id, reason="duplicate")
        payload = {
            "stageId": stage_id,
            "runId": run_id,
            "sourceNotebookSha256": str(execution["sourceSha256"]),
            "parameterSha256": str(source_payload.get("parameterSha256", "")),
            "inputManifestSha256": str(source_payload.get("inputManifestSha256", "")),
            "outputRoot": _relative_portable_path(root / str(execution["stageOutputRoot"]), root),
            "status": str(source_payload.get("status", "NOT_EVALUATED")),
            "createdAt": str(source_payload.get("completedAt") or source_payload.get("startedAt") or ""),
            "sourceManifestPath": _relative_portable_path(source_manifest, root),
            "sourceManifestSha256": sha256_file(source_manifest),
            "sourceManifestRunId": source_run_id,
        }
        errors = validate_current_run_manifest(
            payload,
            expected_stage_id=stage_id,
            expected_run_id=run_id,
            expected_source_sha256=str(execution["sourceSha256"]),
        )
        if errors:
            raise ValueError(f"invalid current-run manifest for {stage_id}: {errors}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows.append({**payload, "path": _relative_portable_path(destination, root), "sha256": sha256_file(destination)})
    return rows


def _normalized_code_cells(path: str | Path, *, executed: bool) -> list[tuple[str, str]]:
    notebook = nbformat.read(path, as_version=4)
    rows: list[tuple[str, str]] = []
    marker = "# Injected into the executed copy by crawl.control.notebook_bundle"
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source
        if executed and marker in source:
            source = source.split(marker, 1)[0].rstrip() + "\n"
        rows.append((cell.get("id", ""), source.rstrip() + "\n"))
    return rows


def source_executed_parity_rows(
    project_root: str | Path,
    executions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    provenance = {row["sourcePath"]: row for row in source_blob_provenance(root)}
    rows: list[dict[str, Any]] = []
    for execution in executions:
        source_relative = str(execution["notebook"])
        if source_relative not in provenance:
            continue
        executed_relative = str(execution["executedPath"])
        source_path = root / source_relative
        executed_path = root / executed_relative
        code_parity = bool(
            executed_path.is_file()
            and _normalized_code_cells(source_path, executed=False)
            == _normalized_code_cells(executed_path, executed=True)
        )
        rows.append({
            **provenance[source_relative],
            "executedPath": executed_relative,
            "executedCodeParity": code_parity,
        })
    return rows


def execute_notebook_plan(
    project_root: str | Path,
    run_root: str | Path,
    include_master: bool = False,
    fail_fast: bool = True,
) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    run = Path(run_root).resolve()
    rows: list[dict[str, Any]] = []
    plan = notebook_plan(root, include_master=include_master)
    order_audit = dependency_order_audit(root, plan)
    if any(row["status"] != "PASS" for row in order_audit):
        raise ValueError(f"Notebook dependency order violation: {order_audit}")
    for owner, stage, relative in plan:
        row = execute_notebook(root / relative, root, run)
        row.update({"agentId": owner, "stageId": stage})
        rows.append(row)
        if row["status"] != "PASS" and fail_fast:
            break
    write_csv(run / "NOTEBOOK_EXECUTION_RESULTS.csv", rows)
    return rows


def collect_stage_manifests(run_root: str | Path) -> list[dict[str, Any]]:
    run = Path(run_root)
    rows = []
    for path in sorted(run.rglob("stage_manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "stageId": payload.get("stageId", ""),
                "status": payload.get("status", ""),
                "path": path.as_posix(),
                "sha256": sha256_file(path),
            })
        except Exception as exc:
            rows.append({"stageId": "", "status": "INVALID", "path": path.as_posix(), "sha256": "", "error": str(exc)})
    return rows


def write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames or (list(rows[0].keys()) if rows else []))
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_master_stage_artifacts(
    output_root: str | Path,
    project_root: str | Path,
    source_audit: Sequence[Mapping[str, Any]],
    executions: Sequence[Mapping[str, Any]],
    manifests: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    output = Path(output_root)
    root = Path(project_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    run_id = MASTER_RUN_ID
    passed = sum(row.get("status") == "PASS" for row in executions)
    started = utc_now()
    input_sha = hashlib.sha256("".join(str(row.get("sha256", "")) for row in source_audit).encode()).hexdigest()
    parameter_sha = hashlib.sha256(b"observed-dev|2.1.2|CRAWL_20260806_03|20260806").hexdigest()
    quality_rows = [
        {"gateId": "NOTEBOOK_SOURCE_READY", "ruleId": "24_SOURCE_NOTEBOOKS", "severity": "ERROR", "status": "PASS" if len(source_audit) == 24 and all(row.get("valid") for row in source_audit) else "FAIL", "observedValue": f"{sum(bool(row.get('valid')) for row in source_audit)}/24", "threshold": "24/24", "evidencePath": "NOTEBOOK_FILE_INVENTORY.csv"},
        {"gateId": "NOTEBOOK_EXECUTION_READY_OBSERVED_DEV", "ruleId": "CHILD_EXECUTION", "severity": "ERROR", "status": "PASS" if executions and passed == len(executions) else "FAIL", "observedValue": f"{passed}/{len(executions)}", "threshold": f"{len(executions)}/{len(executions)}", "evidencePath": "NOTEBOOK_EXECUTION_RESULTS.csv"},
        {"gateId": "NO_EMPIRICAL_PROMOTION", "ruleId": "OBSERVED_ONLY", "severity": "ERROR", "status": "PASS", "observedValue": "false", "threshold": "false", "evidencePath": "stage_manifest.json"},
    ]
    write_csv(output / "stage_quality.csv", quality_rows)
    metrics = {
        "metricsVersion": "stage-metrics-v1", "runId": run_id, "runMode": "observed-dev",
        "stageId": "A3-MASTER", "contractVersion": CONTRACT_VERSION,
        "crawlReleaseId": CRAWL_RELEASE_ID, "dataVersion": DATA_VERSION,
        "dataProvenance": DATA_PROVENANCE, "empiricalAnalysisAllowed": False,
        "promotionAllowed": False, "generatedAt": utc_now(),
        "metrics": [
            {"metricId": "sourceNotebookCount", "value": len(source_audit), "numerator": len(source_audit), "denominator": 24, "unit": "notebook", "grain": "bundle", "unknownHandling": "FAIL", "status": "PASS" if len(source_audit) == 24 else "FAIL"},
            {"metricId": "executedChildNotebookCount", "value": passed, "numerator": passed, "denominator": len(executions), "unit": "notebook", "grain": "bundle", "unknownHandling": "FAIL", "status": "PASS" if executions and passed == len(executions) else "FAIL"},
            {"metricId": "collectedStageManifestCount", "value": len(manifests), "numerator": len(manifests), "denominator": None, "unit": "manifest", "grain": "stage", "unknownHandling": "INFORMATIONAL", "status": "INFORMATIONAL"},
        ],
    }
    (output / "stage_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "manifestVersion": "stage-manifest-v1", "runId": run_id, "runMode": "observed-dev",
        "stageId": "A3-MASTER", "status": "SUCCEEDED" if passed == len(executions) and len(source_audit) == 24 and all(row.get("valid") for row in source_audit) else "FAILED",
        "agentId": "P4-A3-CONTROL", "branch": "agent/p4-integration-cleanup-v2",
        "gitHead": git_head(root), "contractVersion": CONTRACT_VERSION,
        "schemaVersion": "notebook-bundle-v1", "dataVersion": DATA_VERSION,
        "crawlReleaseId": CRAWL_RELEASE_ID, "dataProvenance": DATA_PROVENANCE,
        "startedAt": started, "completedAt": utc_now(), "empiricalAnalysisAllowed": False,
        "promotionAllowed": False, "inputManifestSha256": input_sha, "parameterSha256": parameter_sha,
        "rowCounts": {"sourceNotebooks": len(source_audit), "executedChildren": len(executions), "stageManifests": len(manifests)},
        "gateResults": [{"gateId": row["gateId"], "status": row["status"], "evidencePath": row["evidencePath"]} for row in quality_rows],
        "warnings": [], "errors": [], "files": [],
        "terminationArtifacts": ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"],
        "dataPolicies": {"canonicalStorage": "DUCKDB_PARQUET", "csvPurpose": "HUMAN_INSPECTION_EXPORT", "eligibilityColumns": ["postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag"], "highDemandScore": "ALL_NULL"},
    }
    (output / "stage_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    targets = [output / "stage_manifest.json", output / "stage_metrics.json", output / "stage_quality.csv"]
    (output / "CHECKSUMS.sha256").write_text("".join(f"{sha256_file(path)}  {path.name}\n" for path in targets), encoding="utf-8")
    return {path.name: sha256_file(path) for path in (*targets, output / "CHECKSUMS.sha256")}
