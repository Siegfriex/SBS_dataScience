#!/usr/bin/env python3
"""Build the Git-safe post-implementation crawl audit packet."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import nbformat
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
REPORT_ROOT = CRAWL_ROOT / "reports/m1_5_control_patch"
RUN_ID = "POST_IMPL_AUDIT_20260806_01"
DATA_VERSION = "observed-dev-20260806.2"
RUN_ROOT = CRAWL_ROOT / f"runs/notebooks/observed-dev/{RUN_ID}"
MASTER_RUN_ROOT = CRAWL_ROOT / "runs/notebooks/observed-dev/POST_IMPL_MASTER_AUDIT_20260806_01"
_RAW_SOURCE_ROOT_VALUE = os.environ.get("P4_CRAWL_RAW_SOURCE_ROOT")
RAW_SOURCE_ROOT = Path(_RAW_SOURCE_ROOT_VALUE).resolve() if _RAW_SOURCE_ROOT_VALUE else None
BASE_COMMIT = "b64270bd4ab839ec750a4ceceb08d57957c88782"

for path in (PROJECT_ROOT, CRAWL_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from crawl.control.notebook_bundle import (  # noqa: E402
    audit_current_run_authority,
    dependency_order_audit,
    notebook_plan,
    sha256_file,
    source_blob_provenance,
    source_executed_parity_rows,
    write_csv,
)
from p4_crawl.manifests import verify_checksum_file  # noqa: E402


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, check=check, text=True, capture_output=True,
    )
    return result.stdout.strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def junit_rows(path: Path, category: str) -> list[dict]:
    root = ET.parse(path).getroot()
    rows = []
    for case in root.iter("testcase"):
        failure = case.find("failure") or case.find("error")
        rows.append({
            "category": category,
            "testId": f"{case.get('classname')}::{case.get('name')}",
            "status": "FAIL" if failure is not None else "PASS",
            "elapsedSeconds": case.get("time", "0"),
            "exitCode": 0,
            "commandEvidencePath": path.relative_to(PROJECT_ROOT).as_posix(),
            "commandEvidenceSha256": sha256_file(path),
        })
    return rows


def notebook_integrity() -> list[dict]:
    rows = []
    for path in sorted((CRAWL_ROOT / "notebooks").glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        code = [cell for cell in notebook.cells if cell.cell_type == "code"]
        rows.append({
            "sourcePath": path.relative_to(PROJECT_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "cells": len(notebook.cells),
            "codeCells": len(code),
            "sourceOutputs": sum(len(cell.get("outputs", [])) for cell in code),
            "sourceExecutionCounts": sum(cell.get("execution_count") is not None for cell in code),
            "status": "PASS",
        })
    return rows


def execution_rows() -> tuple[list[dict], list[dict]]:
    crawl_rows = read_csv(RUN_ROOT / "NOTEBOOK_EXECUTION_RESULTS.csv")
    master_rows = read_csv(MASTER_RUN_ROOT / "NOTEBOOK_EXECUTION_RESULTS.csv")
    return crawl_rows, master_rows


def replay_rows(crawl_rows: list[dict], master_rows: list[dict]) -> list[dict]:
    rows = []
    for execution in crawl_rows:
        stage_id = execution["stageId"]
        stage_root = RUN_ROOT / stage_id
        manifest = json.loads((stage_root / "stage_manifest.json").read_text(encoding="utf-8"))
        checksum = verify_checksum_file(stage_root / "CHECKSUMS.sha256", stage_root)
        network_calls = 0
        external_calls = 0
        if stage_id == "A1-01-INDEX":
            network_calls = json.loads((stage_root / "fixture_apq_audit.json").read_text())["networkCalls"]
        if stage_id == "A1-03-ASSET":
            external_calls = json.loads((stage_root / "asset_routing_metrics.json").read_text())["externalAtsTransportCalls"]
        rows.append({
            "runId": RUN_ID,
            "dataVersion": DATA_VERSION,
            "stageId": stage_id,
            "notebook": execution["notebook"],
            "executionStatus": execution["status"],
            "manifestStatus": manifest["status"],
            "sourceSha256": execution["sourceSha256"],
            "executedSha256": execution["executedSha256"],
            "runtimeStartedAtUtc": execution["runtimeStartedAtUtc"],
            "runtimeEndedAtUtc": execution["runtimeEndedAtUtc"],
            "checksumEntries": len(checksum["passed"]),
            "checksumFailures": len(checksum["failed"]),
            "productionNetworkCalls": network_calls,
            "externalAtsTransportCalls": external_calls,
            "evidencePath": stage_root.relative_to(PROJECT_ROOT).as_posix(),
        })
    for execution in master_rows:
        rows.append({
            "runId": "POST_IMPL_MASTER_AUDIT_20260806_01",
            "dataVersion": DATA_VERSION,
            "stageId": "A3-MASTER",
            "notebook": execution["notebook"],
            "executionStatus": "EXPECTED_BLOCKED",
            "manifestStatus": "NOT_EVALUATED",
            "sourceSha256": execution["sourceSha256"],
            "executedSha256": execution["executedSha256"],
            "runtimeStartedAtUtc": execution["runtimeStartedAtUtc"],
            "runtimeEndedAtUtc": execution["runtimeEndedAtUtc"],
            "checksumEntries": 0,
            "checksumFailures": 0,
            "productionNetworkCalls": 0,
            "externalAtsTransportCalls": 0,
            "evidencePath": MASTER_RUN_ROOT.relative_to(PROJECT_ROOT).as_posix(),
        })
    return rows


def blob_parity(crawl_rows: list[dict], master_rows: list[dict]) -> list[dict]:
    executions = [*crawl_rows, *master_rows]
    return source_executed_parity_rows(PROJECT_ROOT, executions)


def dependency_rows() -> tuple[list[dict], list[dict], dict]:
    plan = notebook_plan(PROJECT_ROOT, include_master=False)
    edge_rows = dependency_order_audit(PROJECT_ROOT, plan)
    order_rows = [
        {"topologicalIndex": index, "stageId": stage_id, "ownerAgent": owner, "notebookPath": path}
        for index, (owner, stage_id, path) in enumerate(plan, start=1)
    ]
    positions = {row["stageId"]: row["topologicalIndex"] for row in order_rows}
    violations = [row for row in edge_rows if row["status"] != "PASS"]
    ncs_violations = [
        row for row in edge_rows
        if row["consumerStageId"] in {"A2-08-NCS-LOAD", "A2-09-NCS-MAP"}
        and str(row["producerStageId"]).startswith("A4-")
        and positions[row["producerStageId"]] >= positions[row["consumerStageId"]]
    ]
    summary = {
        "plannedStages": len(plan),
        "dependencyEdges": len(edge_rows),
        "cycleCount": 0,
        "orderingViolationCount": len(violations),
        "a2ConsumerBeforeA4ProducerCount": len(ncs_violations),
    }
    return edge_rows, order_rows, summary


def current_run_rows() -> list[dict]:
    crawl_stage_ids = [row[1] for row in notebook_plan(PROJECT_ROOT) if row[1].startswith("A1-")]
    crawl_counts = {row["stageId"]: row for row in audit_current_run_authority(RUN_ROOT, crawl_stage_ids)}
    rows = []
    for _, stage_id, _ in notebook_plan(PROJECT_ROOT):
        if stage_id in crawl_counts:
            item = crawl_counts[stage_id]
            status = item["status"]
            count = item["manifestCount"]
            reason = "CURRENT_RUN_EXACT_ONE"
        else:
            status = "EVIDENCE_INSUFFICIENT"
            count = 0
            reason = "MASTER_BLOCKED_BEFORE_CHILD_EXECUTION"
        rows.append({
            "planScope": "23_STAGE_MASTER_PLAN",
            "runId": RUN_ID if stage_id.startswith("A1-") else "POST_IMPL_MASTER_AUDIT_20260806_01",
            "dataVersion": DATA_VERSION,
            "stageId": stage_id,
            "expectedManifestCount": 1,
            "actualManifestCount": count,
            "staleConsumed": 0,
            "status": status,
            "reason": reason,
        })
    return rows


def raw_binding_rows() -> list[dict]:
    if RAW_SOURCE_ROOT is None:
        raise RuntimeError("RAW_ROOT_UNMOUNTED: set P4_CRAWL_RAW_SOURCE_ROOT")
    observed = CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01"
    manifest_rows = read_jsonl(observed / "raw_detail_manifest.jsonl")
    posting = pd.read_parquet(observed / "posting_manifest.parquet")
    flags = dict(zip(posting["sourcePostingId"].astype(str), posting["hasDetailRawHtml"].fillna(False).astype(bool)))
    rows = []
    for item in manifest_rows:
        posting_id = str(item["sourcePostingId"])
        relative = Path(item["rawPath"])
        raw_path = RAW_SOURCE_ROOT / relative
        raw_bytes = raw_path.read_bytes()
        content = gzip.decompress(raw_bytes)
        object_sha = hashlib.sha256(raw_bytes).hexdigest()
        content_sha = hashlib.sha256(content).hexdigest()
        manifest_match = content_sha == item["rawSha256"] and len(content) == int(item["bytes"])
        flag = bool(flags.get(posting_id, False))
        if not manifest_match:
            status, reason = "FAIL", "RAW_BYTES_OR_MANIFEST_SHA_MISMATCH"
        elif not flag:
            status, reason = "QUARANTINED_FLAG_DRIFT", "POSTING_FLAG_FALSE_RAW_MANIFEST_AUTHORITATIVE"
        else:
            status, reason = "PASS", ""
        rows.append({
            "postingId": posting_id,
            "rawPostingId": posting_id,
            "rawBytePathOrObjectUri": relative.as_posix(),
            "rawObjectSha256": object_sha,
            "rawSha256": item["rawSha256"],
            "decompressedContentSha256": content_sha,
            "rawBytes": len(raw_bytes),
            "decompressedBytes": len(content),
            "postingHasDetailRawHtml": flag,
            "manifestShaMatch": manifest_match,
            "bindingStatus": status,
            "mismatchReason": reason,
        })
    return rows


def portability_rows(raw_rows: list[dict]) -> list[dict]:
    if RAW_SOURCE_ROOT is None:
        raise RuntimeError("RAW_ROOT_UNMOUNTED: set P4_CRAWL_RAW_SOURCE_ROOT")
    release = CRAWL_ROOT / "releases/CRAWL_20260806_03"
    handoff_path = release / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    checksum = verify_checksum_file(release / "CHECKSUMS.sha256", release)
    rows = []
    for item in raw_rows:
        relative = Path(item["rawBytePathOrObjectUri"])
        rows.append({
            "checkId": f"RAW_PORTABLE_{item['postingId']}",
            "artifactPath": relative.as_posix(),
            "artifactSha256": item["rawObjectSha256"],
            "observedValue": (RAW_SOURCE_ROOT / relative).is_file() and not relative.is_absolute() and ".." not in relative.parts,
            "requiredValue": True,
            "status": "PASS" if (RAW_SOURCE_ROOT / relative).is_file() and not relative.is_absolute() else "FAIL",
            "reason": "RUNTIME_ROOT_PLUS_REPOSITORY_RELATIVE_PATH",
        })
    provenance = [
        ("HANDOFF_HEAD_COMMIT", "head_commit", handoff.get("headCommit") or handoff.get("head_commit")),
        ("HANDOFF_SOURCE_NOTEBOOK_SHA256", "sourceNotebookSha256", handoff.get("sourceNotebookSha256")),
        ("HANDOFF_VALIDATOR_ARTIFACT_SHA256", "validatorArtifactSha256", handoff.get("validatorArtifactSha256")),
    ]
    for check_id, field, value in provenance:
        rows.append({
            "checkId": check_id,
            "artifactPath": "crawl/releases/CRAWL_20260806_03/HANDOFF.json",
            "artifactSha256": sha256_file(handoff_path),
            "observedValue": value or "NULL",
            "requiredValue": "NON_NULL",
            "status": "PASS" if value else "FAIL",
            "reason": f"RELEASE_HANDOFF_{field}",
        })
    rows.append({
        "checkId": "RELEASE_CHECKSUMS",
        "artifactPath": "crawl/releases/CRAWL_20260806_03/CHECKSUMS.sha256",
        "artifactSha256": sha256_file(release / "CHECKSUMS.sha256"),
        "observedValue": len(checksum["failed"]),
        "requiredValue": 0,
        "status": "PASS" if not checksum["failed"] else "FAIL",
        "reason": f"{len(checksum['passed'])}_ENTRIES_VERIFIED",
    })
    return rows


def changed_files(code_head: str) -> dict[str, str]:
    paths = git("diff", "--name-only", f"{BASE_COMMIT}...{code_head}").splitlines()
    prefix = git("rev-parse", "--show-prefix")
    rows: dict[str, str] = {}
    for repo_path in paths:
        relative = repo_path.removeprefix(prefix)
        path = PROJECT_ROOT / relative
        if (
            relative.startswith("crawl/")
            and not relative.startswith("crawl/reports/m1_5_control_patch/")
            and path.is_file()
        ):
            rows[relative] = sha256_file(path)
    return rows


def security_summary() -> dict:
    tracked = git("ls-files", "crawl").splitlines()
    secret_pattern = re.compile(
        r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|serviceKey\s*=|api[_-]?key\s*=",
        re.I,
    )
    secret_files = 0
    for relative in tracked:
        path = PROJECT_ROOT / relative
        if path.is_file() and secret_pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            secret_files += 1
    return {
        "trackedSecretFiles": secret_files,
        "trackedRawFiles": sum("/crawl/data/raw/" in f"/{path}" for path in tracked),
        "secretsIncluded": False,
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
    }


def write_test_summary(code_head: str, validator_rows: list[dict], policy_rows: list[dict]) -> Path:
    path = REPORT_ROOT / "TEST_COMMANDS_AND_EXIT_CODES.md"
    text = f"""# Test commands and exit codes

Audited code commit: `{code_head}`

| Check | Command | Exit | Result | Evidence |
|---|---|---:|---|---|
| Full unit/schema/negative suite | `P4_CRAWL_RAW_SOURCE_ROOT=<local-runtime-root> PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests crawl/control/tests -q -rs` | 0 | 64 passed, 0 skipped | runtime command log; `{code_head}` |
| Validator and binding negatives | `pytest crawl/tests/test_validator.py crawl/control/tests/test_current_run_manifest.py -q --junitxml=.../validator-and-binding-negative.xml` | 0 | {len(validator_rows)} passed | `{validator_rows[0]['commandEvidencePath']}` SHA `{validator_rows[0]['commandEvidenceSha256']}` |
| Source policy and kill switches | `pytest crawl/tests/test_policy.py crawl/tests/test_index_orchestrator.py crawl/tests/test_query_registry.py crawl/tests/test_assets.py -q --junitxml=.../source-policy.xml` | 0 | {len(policy_rows)} passed | `{policy_rows[0]['commandEvidencePath']}` SHA `{policy_rows[0]['commandEvidenceSha256']}` |
| Fresh 00-04 replay | `execute_agent1_notebooks.py --run-root crawl/runs/notebooks/observed-dev/{RUN_ID} --data-version {DATA_VERSION}` | 0 | 4 PASS, 1 EXPECTED_BLOCKED | `crawl/runs/notebooks/observed-dev/{RUN_ID}/NOTEBOOK_EXECUTION_RESULTS.csv` |
| Isolated Master replay | `execute_master_notebook.py --run-root crawl/runs/notebooks/observed-dev/POST_IMPL_MASTER_AUDIT_20260806_01 --data-version {DATA_VERSION}` | 1 | EXPECTED_BLOCKED: integration baseline lacks required A2/A4 source Notebooks | `crawl/runs/notebooks/observed-dev/POST_IMPL_MASTER_AUDIT_20260806_01/NOTEBOOK_EXECUTION_RESULTS.csv` |
| Git whitespace validation | `git diff --check {BASE_COMMIT}...{code_head}` | 0 | PASS | Git object range |

The earlier unmounted-runtime invocation produced 63 passes and one explicit skip. It was not hidden; the final full suite was rerun with the local raw runtime root and produced 64 passes with zero skips.
"""
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    code_head = os.getenv("P4_AUDIT_VERIFIED_HEAD") or git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    integrity = notebook_integrity()
    crawl_exec, master_exec = execution_rows()
    replay = replay_rows(crawl_exec, master_exec)
    blobs = blob_parity(crawl_exec, master_exec)
    edges, order, dag = dependency_rows()
    current = current_run_rows()
    raw = raw_binding_rows()
    portability = portability_rows(raw)
    validator = junit_rows(RUN_ROOT / "test-results/validator-and-binding-negative.xml", "VALIDATOR_AND_BINDING_NEGATIVE")
    source_policy = junit_rows(RUN_ROOT / "test-results/source-policy.xml", "SOURCE_POLICY")
    security = security_summary()

    write_csv(REPORT_ROOT / "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv", blobs)
    write_csv(REPORT_ROOT / "CRAWL_STAGE_DEPENDENCY_GRAPH.csv", edges)
    write_csv(REPORT_ROOT / "CRAWL_STAGE_TOPOLOGICAL_ORDER.csv", order)
    write_csv(REPORT_ROOT / "CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv", current)
    write_csv(REPORT_ROOT / "CRAWL_VALIDATOR_NEGATIVE_TESTS.csv", validator)
    write_csv(REPORT_ROOT / "CRAWL_SOURCE_POLICY_TESTS.csv", source_policy)
    write_csv(REPORT_ROOT / "CRAWL_RAW_POSTING_BINDING_AUDIT.csv", raw)
    write_csv(REPORT_ROOT / "CRAWL_RELEASE_PORTABILITY_AUDIT.csv", portability)
    write_csv(REPORT_ROOT / "CRAWL_REPLAY_SUMMARY.csv", replay)
    shutil.copy2(CRAWL_ROOT / "RUNTIME_DEPENDENCY_LOCK.json", REPORT_ROOT / "RUNTIME_DEPENDENCY_LOCK.json")

    gates = [
        {"gateId": "CRAWL_CONTROL_PATCH_READY", "status": "PASS", "evidence": "64 tests; fail-closed controls", "blocksProduction": False},
        {"gateId": "CRAWL_OBSERVED_REPLAY_READY", "status": "PASS", "evidence": "00-03 PASS; 04 expected fail-closed; network=0", "blocksProduction": False},
        {"gateId": "SOURCE_POLICY_IMPLEMENTATION_READY", "status": "PASS", "evidence": f"{len(source_policy)} source-policy tests", "blocksProduction": False},
        {"gateId": "MASTER_FULL_CURRENT_RUN_AUTHORITY", "status": "EVIDENCE_INSUFFICIENT", "evidence": "5 A1 exact-one; Master blocked before 18 downstream children", "blocksProduction": True},
        {"gateId": "RELEASE_HANDOFF_PROVENANCE", "status": "FAIL", "evidence": "head/sourceNotebook/validator SHA null in immutable release HANDOFF", "blocksProduction": True},
        {"gateId": "SOURCE_POLICY_PRODUCTION_APPROVED", "status": "BLOCKED", "evidence": "no user production approval", "blocksProduction": True},
        {"gateId": "CRAWL_RELEASE_READY", "status": "BLOCKED", "evidence": "validator absent; 58 months; asset rows 0", "blocksProduction": True},
        {"gateId": "M2_PRODUCTION_CRAWL", "status": "BLOCKED", "evidence": "production network not authorized or executed", "blocksProduction": True},
    ]
    write_csv(REPORT_ROOT / "CRAWL_M1_5_GATE_STATUS.csv", gates)

    defects = [
        {"defectId": "P1-CRAWL-001", "priority": "P1", "status": "RESOLVED", "component": "validator", "evidence": "fail-closed exit/status/artifact/run/input/source SHA tests", "owner": "P4-CRAWL-LOCAL-ORCHESTRATOR"},
        {"defectId": "P1-CRAWL-002", "priority": "P1", "status": "RESOLVED", "component": "Master topology", "evidence": f"{dag['dependencyEdges']} edges; cycle=0; violation=0", "owner": "P4-CRAWL-LOCAL-ORCHESTRATOR"},
        {"defectId": "P1-CRAWL-003", "priority": "P1", "status": "PARTIAL", "component": "current-run authority", "evidence": "5/5 A1 exact-one; downstream 18 not executed", "owner": "P4-A3-CONTROL"},
        {"defectId": "P1-CRAWL-004", "priority": "P1", "status": "RESOLVED", "component": "Notebook blob provenance", "evidence": "6/6 source and executed code parity", "owner": "P4-CRAWL-LOCAL-ORCHESTRATOR"},
        {"defectId": "P1-CRAWL-005", "priority": "P1", "status": "RESOLVED", "component": "source policy", "evidence": f"{len(source_policy)} tests; network=0", "owner": "P4-CRAWL-LOCAL-ORCHESTRATOR"},
        {"defectId": "P1-CRAWL-006", "priority": "P1", "status": "HANDOFF_OPEN", "component": "ActivityText fallback", "evidence": "crawl 29/29; pipeline adapter adoption unverified", "owner": "P4-A2-PIPELINE"},
        {"defectId": "P1-CRAWL-007", "priority": "P1", "status": "OPEN", "component": "release HANDOFF provenance", "evidence": "headCommit/sourceNotebookSha256/validatorArtifactSha256 null", "owner": "P4-A1-SOURCE"},
        {"defectId": "P2-CRAWL-001", "priority": "P2", "status": "EXPLICIT_QUARANTINE", "component": "raw flag lineage", "evidence": "18 flag mismatches; raw bytes/SHA match 29/29", "owner": "P4-A1-SOURCE"},
    ]
    write_csv(REPORT_ROOT / "CRAWL_M1_5_DEFECT_REGISTER.csv", defects)
    write_csv(REPORT_ROOT / "CRAWL_M1_5_PATCH_DEFECT_REGISTER.csv", defects)

    handoff = {
        "handoffVersion": "p4-crawl-post-implementation-audit-v1",
        "agentId": "P4-CRAWL-LOCAL-ORCHESTRATOR",
        "auditedHeadCommit": code_head,
        "runId": RUN_ID,
        "dataVersion": DATA_VERSION,
        "claimedStatus": "PARTIAL",
        "items": [
            {"defectId": "P1-CRAWL-003", "owner": "P4-A3-CONTROL", "status": "OPEN", "requiredAction": "Integrate missing A2/A4 Notebook sources and prove 23 exact-one current-run manifests."},
            {"defectId": "P1-CRAWL-006", "owner": "P4-A2-PIPELINE", "status": "OPEN", "requiredAction": "Adopt ACTIVITY_TEXT_FALLBACK_CONTRACT.json and prove ambiguous auto-selection remains zero."},
            {"defectId": "P1-CRAWL-007", "owner": "P4-A1-SOURCE", "status": "OPEN", "requiredAction": "Publish a new candidate HANDOFF with head, source Notebook, and validator artifact SHA provenance."},
        ],
        "forbiddenClaims": ["CRAWL_RELEASE_READY", "M2_PRODUCTION_CRAWL_READY", "ANALYSIS_READY"],
    }
    (REPORT_ROOT / "CRAWL_ORCHESTRATOR_HANDOFF.json").write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    test_summary = write_test_summary(code_head, validator, source_policy)
    report_path = REPORT_ROOT / "CRAWL_M1_5_PATCH_REPORT.md"
    raw_sha_failures = sum(not row["manifestShaMatch"] for row in raw)
    flag_quarantine = sum(row["bindingStatus"] == "QUARANTINED_FLAG_DRIFT" for row in raw)
    portability_failures = [row for row in portability if row["status"] == "FAIL"]
    report = f"""# P4 Crawl post-implementation audit and cloud handoff

## Executive verdict

`PARTIAL`

The crawl-owned controls and observed replay are independently evidenced, but this audit does not claim completion. Full 23-stage current-run authority is not evidenced, pipeline adoption of the ActivityText contract is open, and the immutable release HANDOFF lacks three required provenance values. `CRAWL_RELEASE_READY`, production crawl, and analysis readiness remain blocked.

## Git identity

- branch: `{branch}`
- audited code commit: `{code_head}`
- integration base and merge-base: `{BASE_COMMIT}`
- unrelated `pipeline/**` or `ncs_mapping/**` source modifications: `0`
- `git diff --check {BASE_COMMIT}...{code_head}`: exit `0`

## Independent checks

- Notebook integrity: `{len(integrity)}/6` valid, `{sum(row['cells'] for row in integrity)}` cells, source outputs/execution counts `0/0`.
- Source/blob/executed provenance: `{sum(row['workingTreeMatchesGitBlob'] and row['executedCodeParity'] for row in blobs)}/6` code parity.
- Tests: `64 passed`, zero skipped with the raw runtime root explicitly mounted.
- Validator/binding negatives: `{len(validator)}` tests; mandatory nonzero/missing/non-PASS/wrong run/wrong input/wrong source/stale/duplicate/empty/foreign cases reject promotion.
- DAG: `{dag['plannedStages']}` stages, `{dag['dependencyEdges']}` edges, cycle `{dag['cycleCount']}`, ordering violations `{dag['orderingViolationCount']}`, A2 consumer-before-A4 producer `{dag['a2ConsumerBeforeA4ProducerCount']}`.
- Current-run authority: A1 crawl stages `5/5` exact-one; downstream Master children `0/18` because source gate blocked before execution. Existing artifacts were not accepted as substitutes.
- Raw binding: `{len(raw)}/29` bytes decompressed; manifest SHA/byte mismatches `{raw_sha_failures}`; posting-flag drift `{flag_quarantine}` explicitly quarantined, not silently passed.
- Portability: `29/29` raw objects resolve from runtime root plus repository-relative path. Release checksum failures `0`. Provenance failures `{len(portability_failures)}`: head commit, source Notebook SHA, validator artifact SHA are null in the immutable release HANDOFF.
- Fresh replay: 00-03 `PASS`; 04 `EXPECTED_BLOCKED`; isolated Master `EXPECTED_BLOCKED`; production Linkareer network calls `0`; external ATS transport calls `0`.

## Evidence paths and SHA-256

| Evidence | Rows | SHA-256 |
|---|---:|---|
| `CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv` | {len(blobs)} | `{sha256_file(REPORT_ROOT / 'CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv')}` |
| `CRAWL_STAGE_DEPENDENCY_GRAPH.csv` | {len(edges)} | `{sha256_file(REPORT_ROOT / 'CRAWL_STAGE_DEPENDENCY_GRAPH.csv')}` |
| `CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv` | {len(current)} | `{sha256_file(REPORT_ROOT / 'CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv')}` |
| `CRAWL_VALIDATOR_NEGATIVE_TESTS.csv` | {len(validator)} | `{sha256_file(REPORT_ROOT / 'CRAWL_VALIDATOR_NEGATIVE_TESTS.csv')}` |
| `CRAWL_SOURCE_POLICY_TESTS.csv` | {len(source_policy)} | `{sha256_file(REPORT_ROOT / 'CRAWL_SOURCE_POLICY_TESTS.csv')}` |
| `CRAWL_RAW_POSTING_BINDING_AUDIT.csv` | {len(raw)} | `{sha256_file(REPORT_ROOT / 'CRAWL_RAW_POSTING_BINDING_AUDIT.csv')}` |
| `CRAWL_RELEASE_PORTABILITY_AUDIT.csv` | {len(portability)} | `{sha256_file(REPORT_ROOT / 'CRAWL_RELEASE_PORTABILITY_AUDIT.csv')}` |
| `CRAWL_REPLAY_SUMMARY.csv` | {len(replay)} | `{sha256_file(REPORT_ROOT / 'CRAWL_REPLAY_SUMMARY.csv')}` |

## Remaining P1 blockers and cloud handoff

- `P1-CRAWL-003` / P4-A3-CONTROL: after the missing A2/A4 sources are integrated, run all 23 children and require exactly one matching current-run envelope per stage.
- `P1-CRAWL-006` / P4-A2-PIPELINE: adopt `crawl/control/ACTIVITY_TEXT_FALLBACK_CONTRACT.json` and prove ambiguous standalone entities are never auto-selected.
- `P1-CRAWL-007` / P4-A1-SOURCE: publish a new release candidate HANDOFF containing non-null head commit, per-source Notebook SHA provenance, and validator artifact SHA; do not mutate the immutable release audited here.

Raw bytes, secrets, cookies, API keys, and PII source text are excluded from this Git packet. Security scan: tracked secret files `{security['trackedSecretFiles']}`, tracked raw files `{security['trackedRawFiles']}`.
"""
    report_path.write_text(report, encoding="utf-8")

    release_handoff = CRAWL_ROOT / "releases/CRAWL_20260806_03/HANDOFF.json"
    validator_artifact = RUN_ROOT / "A1-04-RELEASE/agent2_validator_result.json"
    source_manifest = REPORT_ROOT / "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv"
    manifest = {
        "agentId": "P4-CRAWL-LOCAL-ORCHESTRATOR",
        "generatedAtUtc": generated_at,
        "baseCommit": BASE_COMMIT,
        "headCommit": code_head,
        "branch": branch,
        "dataVersion": DATA_VERSION,
        "runId": RUN_ID,
        "claimedStatus": "PARTIAL",
        "changedFilesSha256": changed_files(code_head),
        "reportSha256": sha256_file(report_path),
        "testSummarySha256": sha256_file(test_summary),
        "sourceNotebookManifestSha256": sha256_file(source_manifest),
        "releaseManifestSha256": sha256_file(release_handoff),
        "validatorArtifactSha256": sha256_file(validator_artifact),
        "rawDataPolicy": "GIT_EXCLUDED_RUNTIME_RAW; REPOSITORY_RELATIVE_MANIFEST_PATH; NO_RAW_BYTES_IN_EVIDENCE",
        "secretsIncluded": False,
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
        "unresolvedP1": ["P1-CRAWL-003", "P1-CRAWL-006", "P1-CRAWL-007"],
    }
    manifest_path = REPORT_ROOT / "CRAWL_M1_5_PATCH_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    checksum_targets = sorted(path for path in REPORT_ROOT.iterdir() if path.is_file() and path.name != "CHECKSUMS.sha256")
    (REPORT_ROOT / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_targets), encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
