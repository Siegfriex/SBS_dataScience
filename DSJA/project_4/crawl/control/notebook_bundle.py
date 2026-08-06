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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import nbformat
from nbclient import NotebookClient
from jsonschema import Draft202012Validator, FormatChecker


CONTRACT_VERSION = "2.1.2"
DATA_VERSION = "observed-dev-20260806.1"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"
MASTER_RUN_ID = "MASTER_20260806_01"

NOTEBOOKS: tuple[tuple[str, str, str], ...] = (
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
    ("P4-A2-PIPELINE", "A2-08-NCS-LOAD", "pipeline/notebooks/08LoadAndPrepareNcs.ipynb"),
    ("P4-A2-PIPELINE", "A2-09-NCS-MAP", "pipeline/notebooks/09MapPostingToNcs.ipynb"),
    ("P4-A2-PIPELINE", "A2-10-EXPORT", "pipeline/notebooks/10ExportPreprocessedCsv.ipynb"),
    ("P4-A2-PIPELINE", "A2-11-EXPORT-QA", "pipeline/notebooks/11PreprocessedDataQa.ipynb"),
    ("P4-A4-NCS", "A4-00-NCS-SOURCE", "ncs_mapping/notebooks/00NcsSourceAudit.ipynb"),
    ("P4-A4-NCS", "A4-01-CODESET", "ncs_mapping/notebooks/01BuildCoreAiItCodeSet.ipynb"),
    ("P4-A4-NCS", "A4-02-RETRIEVAL", "ncs_mapping/notebooks/02BuildNcsRetrievalIndex.ipynb"),
    ("P4-A4-NCS", "A4-03-MAP-OBSERVED", "ncs_mapping/notebooks/03MapObservedDuties.ipynb"),
    ("P4-A4-NCS", "A4-04-EXPORT", "ncs_mapping/notebooks/04ExportNcsMappingCsv.ipynb"),
    ("P4-A4-NCS", "A4-05-EVALUATE", "ncs_mapping/notebooks/05EvaluateNcsMapping.ipynb"),
    ("P4-A3-CONTROL", "A3-MASTER", "crawl/notebooks/P4_Notebook_First_Master.ipynb"),
)

CURRENT_RUN_MANIFEST = "current_run_manifest.json"

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


def load_stage_registry(project_root: str | Path) -> dict[str, Any]:
    import yaml

    path = Path(project_root) / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml"
    registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    registry["stages"] = topological_stage_rows(registry)
    return registry


def topological_stage_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return a deterministic upstream-first plan or fail on an invalid DAG."""
    stages = registry.get("stages", [])
    if not isinstance(stages, list) or any(not isinstance(stage, dict) for stage in stages):
        raise ValueError("registry stages must be a list of mappings")
    by_id = {str(stage.get("stageId", "")): stage for stage in stages}
    if "" in by_id or len(by_id) != len(stages):
        raise ValueError("registry stageId values must be non-empty and unique")
    unknown = sorted({upstream for stage in stages for upstream in stage.get("upstreamStages", []) if upstream not in by_id})
    if unknown:
        raise ValueError("unknown upstream stages: " + ",".join(unknown))

    remaining = {stage_id: set(stage.get("upstreamStages", [])) for stage_id, stage in by_id.items()}
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(stage_id for stage_id, upstream in remaining.items() if not upstream)
        if not ready:
            raise ValueError("stage registry contains a dependency cycle: " + ",".join(sorted(remaining)))
        for stage_id in ready:
            ordered.append(by_id[stage_id])
            remaining.pop(stage_id)
        for upstream in remaining.values():
            upstream.difference_update(ready)
    return ordered


def registry_notebook_plan(project_root: str | Path, include_master: bool = False) -> tuple[tuple[str, str, str], ...]:
    """Build the executable Notebook plan from registry upstream edges, not tuple order."""
    root = Path(project_root).resolve()
    inventory_paths = {relative for _, _, relative in NOTEBOOKS}
    rows: list[tuple[str, str, str]] = []
    for stage in topological_stage_rows(load_stage_registry(root)):
        relative = str(stage["notebookPath"])
        if relative not in inventory_paths or (stage["stageId"] == "A3-MASTER" and not include_master):
            continue
        rows.append((str(stage["ownerAgent"]), str(stage["stageId"]), relative))
    expected = {relative for _, stage, relative in NOTEBOOKS if include_master or stage != "A3-MASTER"}
    actual = {relative for _, _, relative in rows}
    if actual != expected:
        raise ValueError(f"registry/inventory Notebook mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    return tuple(rows)


def git_blob_provenance(path: str | Path, project_root: str | Path, git_ref: str = "HEAD") -> dict[str, Any]:
    """Bind a source file to a tracked Git blob at an explicit ref."""
    root = Path(project_root).resolve()
    source = Path(path).resolve()
    try:
        repo_root = Path(subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=root,
            text=True, capture_output=True, check=True,
        ).stdout.strip()).resolve()
        relative = source.relative_to(repo_root).as_posix()
    except (OSError, ValueError, subprocess.CalledProcessError):
        return {"gitTracked": False, "gitRef": git_ref, "gitBlobSha": "", "workingTreeBlobSha": "", "gitBlobMatch": False}
    base = {"gitTracked": False, "gitRef": git_ref, "gitBlobSha": "", "workingTreeBlobSha": "", "gitBlobMatch": False}
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative], cwd=repo_root,
            text=True, capture_output=True, check=False,
        )
        if tracked.returncode != 0:
            return base
        ref_blob = subprocess.run(
            ["git", "rev-parse", f"{git_ref}:{relative}"], cwd=repo_root,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        worktree_blob = subprocess.run(
            ["git", "hash-object", "--", relative], cwd=repo_root,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return base
    return {
        "gitTracked": True,
        "gitRef": git_ref,
        "gitBlobSha": ref_blob,
        "workingTreeBlobSha": worktree_blob,
        "gitBlobMatch": bool(ref_blob and ref_blob == worktree_blob),
    }


def repository_architecture(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root)
    rows = []
    for owner, stage_id, relative in registry_notebook_plan(root, include_master=True):
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
        **git_blob_provenance(source_path, project_root),
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
    if not row["gitTracked"]:
        errors.append("source Notebook is not tracked by Git")
    elif not row["gitBlobMatch"]:
        errors.append(f"source Notebook does not match {row['gitRef']} blob")
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
    rows = []
    for owner, stage, relative in registry_notebook_plan(root, include_master=True):
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


def _parameter_sha(source_parameter_cell: str, output_root: Path | None) -> str:
    material = source_parameter_cell.rstrip() + "\n\n" + _parameter_overrides(output_root)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _relative_or_absolute(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _write_current_run_manifest(
    *, root: Path, run: Path, source: Path, destination: Path, stage_output: Path,
    stage_id: str, owner: str, status: str, parameter_sha: str, error: str,
) -> Path:
    provenance = git_blob_provenance(source, root)
    native = stage_output / "stage_manifest.json"
    errors = [error] if error else []
    if not native.is_file():
        errors.append("native stage_manifest.json missing")
    if not provenance["gitTracked"] or not provenance["gitBlobMatch"]:
        errors.append("source Git provenance invalid")
    effective_status = "PASS" if status == "PASS" and not errors else "FAIL"
    payload = {
        "manifestVersion": "current-run-manifest-v1",
        "currentRunId": MASTER_RUN_ID,
        "stageId": stage_id,
        "agentId": owner,
        "status": effective_status,
        "sourceNotebookPath": source.relative_to(root).as_posix(),
        "sourceNotebookSha256": sha256_file(source),
        "sourceGitRef": provenance["gitRef"],
        "sourceGitBlobSha": provenance["gitBlobSha"],
        "parameterSha256": parameter_sha,
        "artifactRoot": _relative_or_absolute(stage_output, root),
        "executedNotebookPath": _relative_or_absolute(destination, root),
        "executedNotebookSha256": sha256_file(destination),
        "nativeStageManifestPath": _relative_or_absolute(native, root) if native.is_file() else None,
        "nativeStageManifestSha256": sha256_file(native) if native.is_file() else None,
        "createdAt": utc_now(),
        "errors": errors,
    }
    path = stage_output / CURRENT_RUN_MANIFEST
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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
    plan = registry_notebook_plan(root, include_master=True)
    stage_lookup = {item[2]: item[1] for item in plan}
    stage_id = stage_lookup[relative.as_posix()]
    owner = next(item[0] for item in plan if item[2] == relative.as_posix())
    parameter_output: Path | None
    kernel_cwd = root
    child_env: dict[str, str] = {}
    if owner == "P4-A1-SOURCE":
        agent_run = shared_run / "agent_runs" / "AGENT1"
        stage_output = agent_run / stage_id
        parameter_output = agent_run.relative_to(root)
    elif owner == "P4-A2-PIPELINE":
        agent_run = root / "pipeline/runs/notebooks/observed-dev/MASTER_20260806_01"
        stage_name = source.stem
        stage_output = shared_run / "agent_runs" / "AGENT2" / stage_name
        parameter_output = None
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
    parameter_sha = _parameter_sha(code_cells[0].source, parameter_output)
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
            canonical_stage = root / "pipeline/runs/notebooks/observed-dev/MASTER_20260806_01/artifacts" / source.stem
        else:
            canonical_stage = root / "ncs_mapping/data/runs/observed-dev/NCS_MAPPING_OBSERVED_20260806_01" / stage_id
        if canonical_stage.is_dir():
            for name in ("stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"):
                if (canonical_stage / name).is_file():
                    shutil.copy2(canonical_stage / name, stage_output / name)
    nbformat.write(notebook, destination)
    outputs = sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code")
    current_manifest = _write_current_run_manifest(
        root=root,
        run=shared_run,
        source=source,
        destination=destination,
        stage_output=stage_output,
        stage_id=stage_id,
        owner=owner,
        status=status,
        parameter_sha=parameter_sha,
        error=error,
    )
    binding = json.loads(current_manifest.read_text(encoding="utf-8"))
    return {
        "notebook": relative.as_posix(),
        "status": binding["status"],
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "sourceSha256": sha256_file(source),
        "executedPath": destination.relative_to(root).as_posix() if destination.is_relative_to(root) else str(destination),
        "executedSha256": sha256_file(destination),
        "executedOutputs": outputs,
        "stageOutputRoot": stage_output.relative_to(root).as_posix() if stage_output.is_relative_to(root) else str(stage_output),
        "parameterSha256": parameter_sha,
        "currentRunManifest": current_manifest.relative_to(root).as_posix() if current_manifest.is_relative_to(root) else str(current_manifest),
        "sourceGitRef": binding["sourceGitRef"],
        "sourceGitBlobSha": binding["sourceGitBlobSha"],
        "error": error.replace("\n", " ")[:2000],
    }


def execute_notebook_plan(
    project_root: str | Path,
    run_root: str | Path,
    include_master: bool = False,
    fail_fast: bool = True,
) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    run = Path(run_root).resolve()
    rows: list[dict[str, Any]] = []
    plan = registry_notebook_plan(root, include_master=include_master)
    for owner, stage, relative in plan:
        row = execute_notebook(root / relative, root, run)
        row.update({"agentId": owner, "stageId": stage})
        rows.append(row)
        if row["status"] != "PASS" and fail_fast:
            break
    write_csv(run / "NOTEBOOK_EXECUTION_RESULTS.csv", rows)
    return rows


def collect_stage_manifests(
    run_root: str | Path,
    project_root: str | Path | None = None,
    current_run_id: str = MASTER_RUN_ID,
) -> list[dict[str, Any]]:
    """Validate exactly one provenance-bound manifest for every planned child stage."""
    run = Path(run_root).resolve()
    root = Path(project_root).resolve() if project_root else resolve_project_root(run)
    expected_plan = registry_notebook_plan(root, include_master=False)
    expected = {stage: (owner, relative) for owner, stage, relative in expected_plan}
    result_path = run / "NOTEBOOK_EXECUTION_RESULTS.csv"
    if not result_path.is_file():
        raise ValueError(f"current-run execution results missing: {result_path}")
    with result_path.open(encoding="utf-8-sig", newline="") as handle:
        execution_rows = list(csv.DictReader(handle))
    by_stage = {str(row.get("stageId", "")): row for row in execution_rows}
    if len(by_stage) != len(execution_rows) or set(by_stage) != set(expected):
        raise ValueError("current-run execution plan is incomplete or has duplicate/unplanned stages")

    paths = sorted(run.rglob(CURRENT_RUN_MANIFEST))
    schema = json.loads((Path(__file__).resolve().parent / "CURRENT_RUN_MANIFEST.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    payloads: list[tuple[Path, dict[str, Any]]] = []
    parse_errors: list[str] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest must be an object")
            validation_errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
            if validation_errors:
                raise ValueError("; ".join(error.message for error in validation_errors))
            payloads.append((path, payload))
        except Exception as exc:
            parse_errors.append(f"{path}: {exc}")
    if parse_errors:
        raise ValueError("invalid current-run manifest: " + " | ".join(parse_errors))
    counts = Counter(str(payload.get("stageId", "")) for _, payload in payloads)
    missing = sorted(set(expected) - set(counts))
    duplicate = sorted(stage for stage, count in counts.items() if count != 1)
    unplanned = sorted(set(counts) - set(expected))
    if missing or duplicate or unplanned:
        raise ValueError(f"current-run manifest cardinality failure: missing={missing} duplicate={duplicate} unplanned={unplanned}")

    source_audit = {row["stageId"]: row for row in audit_source_bundle(root) if row["stageId"] in expected}
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    for path, payload in payloads:
        stage_id = str(payload.get("stageId", ""))
        if stage_id not in expected:
            continue
        owner, relative = expected[stage_id]
        execution = by_stage[stage_id]
        source = source_audit[stage_id]
        expected_artifact = (root / str(execution["stageOutputRoot"])).resolve()
        native = expected_artifact / "stage_manifest.json"
        native_value = payload.get("nativeStageManifestPath")
        native_path = (root / str(native_value)).resolve() if native_value else None
        executed_value = payload.get("executedNotebookPath")
        executed_path = (root / str(executed_value)).resolve() if executed_value else None
        checks = {
            "manifestVersion": payload.get("manifestVersion") == "current-run-manifest-v1",
            "currentRunId": payload.get("currentRunId") == current_run_id,
            "agentId": payload.get("agentId") == owner,
            "sourceNotebookPath": payload.get("sourceNotebookPath") == relative,
            "sourceNotebookSha256": payload.get("sourceNotebookSha256") == source.get("sha256"),
            "sourceGitRef": payload.get("sourceGitRef") == source.get("gitRef") == "HEAD",
            "sourceGitBlobSha": payload.get("sourceGitBlobSha") == source.get("gitBlobSha"),
            "sourceGitTrackedClean": bool(source.get("gitTracked") and source.get("gitBlobMatch")),
            "executionSourceSha256": execution.get("sourceSha256") == source.get("sha256"),
            "parameterSha256": payload.get("parameterSha256") == execution.get("parameterSha256"),
            "artifactRoot": (root / str(payload.get("artifactRoot", ""))).resolve() == expected_artifact == path.parent.resolve(),
            "nativeStageManifestPath": native_path == native and native.is_file(),
            "nativeStageManifestSha256": native.is_file() and payload.get("nativeStageManifestSha256") == sha256_file(native),
            "executedNotebookPath": executed_path is not None and executed_path.is_file(),
            "executedNotebookSha256": executed_path is not None and executed_path.is_file() and payload.get("executedNotebookSha256") == sha256_file(executed_path),
            "status": payload.get("status") == execution.get("status") == "PASS",
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            errors.append(f"{stage_id}: " + ",".join(failed))
        rows.append({
            "stageId": stage_id,
            "status": "SUCCEEDED" if not failed else "INVALID",
            "path": _relative_or_absolute(path, root),
            "sha256": sha256_file(path),
            "currentRunId": payload.get("currentRunId", ""),
            "sourceGitBlobSha": payload.get("sourceGitBlobSha", ""),
            "parameterSha256": payload.get("parameterSha256", ""),
            "artifactRoot": payload.get("artifactRoot", ""),
            "error": ",".join(failed),
        })
    if errors:
        raise ValueError("current-run provenance validation failed: " + " | ".join(errors))
    order = {stage: index for index, (_, stage, _) in enumerate(expected_plan)}
    return sorted(rows, key=lambda row: order[row["stageId"]])


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
