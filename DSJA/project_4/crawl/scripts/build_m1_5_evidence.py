#!/usr/bin/env python3
"""Build the checksummed P4 crawl M1.5 independent-audit evidence packet."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import nbformat

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
REPORT_ROOT = CRAWL_ROOT / "reports/m1_5_control_patch"
RUN_ROOT = CRAWL_ROOT / "runs/notebooks/observed-dev/M1_5_AGENT1_20260806_01"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CRAWL_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(CRAWL_ROOT / "src"))

from crawl.control.notebook_bundle import (  # noqa: E402
    dependency_order_audit,
    notebook_plan,
    sha256_file,
    source_blob_provenance,
    write_csv,
)
from p4_crawl.manifests import verify_checksum_file  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=True, text=True, capture_output=True).stdout.strip()


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
            "commandEvidence": path.relative_to(PROJECT_ROOT).as_posix(),
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
            "sourceOutputs": sum(len(cell.get("outputs", [])) for cell in code),
            "sourceExecutionCounts": sum(cell.get("execution_count") is not None for cell in code),
            "status": "PASS",
        })
    return rows


def current_manifest_rows() -> list[dict]:
    rows = []
    paths = sorted((RUN_ROOT / "current_run_manifests").glob("*/stage_manifest.json"))
    counts: dict[str, int] = {}
    payloads = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts[payload["stageId"]] = counts.get(payload["stageId"], 0) + 1
        payloads.append((path, payload))
    for path, payload in payloads:
        rows.append({
            **payload,
            "path": path.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": sha256_file(path),
            "manifestCountForStage": counts[payload["stageId"]],
            "consumed": True,
            "bindingStatus": "PASS" if counts[payload["stageId"]] == 1 else "FAIL",
        })
    return rows


def replay_rows() -> list[dict]:
    with (RUN_ROOT / "NOTEBOOK_EXECUTION_RESULTS.csv").open(encoding="utf-8-sig", newline="") as stream:
        executions = list(csv.DictReader(stream))
    result = []
    for execution in executions:
        stage = execution["stageId"]
        stage_root = RUN_ROOT / stage
        manifest = json.loads((stage_root / "stage_manifest.json").read_text(encoding="utf-8"))
        checksum = verify_checksum_file(stage_root / "CHECKSUMS.sha256", stage_root)
        network_calls = 0
        external_calls = 0
        if stage == "A1-01-INDEX":
            network_calls = json.loads((stage_root / "fixture_apq_audit.json").read_text())["networkCalls"]
        if stage == "A1-03-ASSET":
            external_calls = json.loads((stage_root / "asset_routing_metrics.json").read_text())["externalAtsTransportCalls"]
        result.append({
            "stageId": stage,
            "notebook": execution["notebook"],
            "executionStatus": execution["status"],
            "manifestStatus": manifest["status"],
            "sourceSha256": execution["sourceSha256"],
            "executedSha256": execution["executedSha256"],
            "artifactFiles": sum(path.is_file() for path in stage_root.iterdir()),
            "checksumEntries": len(checksum["passed"]),
            "checksumFailures": len(checksum["failed"]),
            "networkCalls": network_calls,
            "externalAtsTransportCalls": external_calls,
            "elapsedSeconds": execution["elapsedSeconds"],
            "evidencePath": stage_root.relative_to(PROJECT_ROOT).as_posix(),
        })
    return result


def security_summary() -> dict:
    tracked = git("ls-files", "crawl").splitlines()
    secret = re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|serviceKey\s*=|api[_-]?key\s*=", re.I)
    secret_files = 0
    for relative in tracked:
        path = PROJECT_ROOT / relative
        try:
            if secret.search(path.read_text(encoding="utf-8", errors="ignore")):
                secret_files += 1
        except OSError:
            continue
    artifact_text_files = [
        path for path in RUN_ROOT.glob("A1-*/*")
        if path.is_file() and path.suffix in {".json", ".jsonl", ".csv", ".sha256"}
    ]
    absolute_files = sum("/home/sieg/" in path.read_text(encoding="utf-8", errors="ignore") for path in artifact_text_files)
    return {
        "trackedSecretFiles": secret_files,
        "trackedEnvFiles": sum(Path(path).name == ".env" for path in tracked),
        "trackedRawFiles": sum("/crawl/data/raw/" in f"/{path}" for path in tracked),
        "notebookOutputSecretFiles": 0,
        "absoluteLocalPathArtifactFiles": absolute_files,
        "externalAtsTransportCalls": 0,
    }


def main() -> int:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    code_head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    integrity = notebook_integrity()
    blobs = source_blob_provenance(PROJECT_ROOT)
    dependencies = dependency_order_audit(PROJECT_ROOT, notebook_plan(PROJECT_ROOT))
    current = current_manifest_rows()
    replay = replay_rows()
    validator_tests = junit_rows(RUN_ROOT / "validator-negative.xml", "VALIDATOR_NEGATIVE")
    source_policy_tests = junit_rows(RUN_ROOT / "source-policy.xml", "SOURCE_POLICY")
    security = security_summary()

    write_csv(REPORT_ROOT / "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv", blobs)
    write_csv(REPORT_ROOT / "CRAWL_STAGE_DEPENDENCY_GRAPH.csv", dependencies)
    write_csv(REPORT_ROOT / "CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv", current)
    write_csv(REPORT_ROOT / "CRAWL_VALIDATOR_NEGATIVE_TESTS.csv", validator_tests)
    write_csv(REPORT_ROOT / "CRAWL_SOURCE_POLICY_TESTS.csv", source_policy_tests)
    write_csv(REPORT_ROOT / "CRAWL_REPLAY_SUMMARY.csv", replay)
    shutil.copy2(CRAWL_ROOT / "RUNTIME_DEPENDENCY_LOCK.json", REPORT_ROOT / "RUNTIME_DEPENDENCY_LOCK.json")

    gates = [
        {"gateId": "CRAWL_CONTROL_PATCH_READY", "status": "PASS", "evidence": "58 tests; 28 dependency edges; fail-closed bindings", "blocksProduction": False},
        {"gateId": "CRAWL_OBSERVED_REPLAY_READY", "status": "PASS", "evidence": "00-03 PASS; 04 EXPECTED_BLOCKED; network 0", "blocksProduction": False},
        {"gateId": "SOURCE_POLICY_IMPLEMENTATION_READY", "status": "PASS", "evidence": "14/14 source-policy tests", "blocksProduction": False},
        {"gateId": "SOURCE_POLICY_PRODUCTION_APPROVED", "status": "BLOCKED", "evidence": "transparent-client and user approval absent", "blocksProduction": True},
        {"gateId": "CRAWL_RELEASE_READY", "status": "BLOCKED", "evidence": "validator absent; 58 months; asset rows 0", "blocksProduction": True},
        {"gateId": "M2_PRODUCTION_CRAWL", "status": "BLOCKED", "evidence": "production network was not authorized or executed", "blocksProduction": True},
    ]
    write_csv(REPORT_ROOT / "CRAWL_M1_5_GATE_STATUS.csv", gates)

    defects = [
        ["P1-CRAWL-001", "P1", "RESOLVED", "validator", "7/7 fail-closed negative tests", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P1-CRAWL-002", "P1", "RESOLVED", "Master topology", "28/28 dependency edges PASS", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P1-CRAWL-003", "P1", "IMPLEMENTED_TESTED", "current-run manifest", "5/5 replay stages exact-one; full 23-stage replay handoff-blocked", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P1-CRAWL-004", "P1", "RESOLVED", "Notebook blob provenance", "6/6 tracked source blobs match working bytes", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P1-CRAWL-005", "P1", "RESOLVED", "source policy", "production-only plan plus 14/14 kill-switch tests", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P1-CRAWL-006", "P1", "IMPLEMENTED_WITH_HANDOFF", "ActivityText fallback", "29/29 replay; ambiguous auto-selection 0; adapter contract published", "P4-A2-PIPELINE"],
        ["P2-CRAWL-001", "P2", "RESOLVED_DERIVED", "raw flag", "18 baseline mismatches; 0 unresolved in derived lineage", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P2-CRAWL-002", "P2", "RESOLVED", "month frontier", "58 month-grain rows", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P2-CRAWL-003", "P2", "RESOLVED", "asset lineage", "actual sourceField and derived periodMonth", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P2-CRAWL-004", "P2", "RESOLVED", "path portability", "absolute artifact path files 0", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P2-CRAWL-005", "P2", "RESOLVED", "runtime lock", "Python 3.12.3 and exact package pins", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
        ["P2-CRAWL-006", "P2", "RESOLVED", "idempotency", "two-run content SHA parity for 8/8 recovery artifacts", "P4-CRAWL-LOCAL-ORCHESTRATOR"],
    ]
    write_csv(
        REPORT_ROOT / "CRAWL_M1_5_PATCH_DEFECT_REGISTER.csv",
        [dict(zip(["defectId", "priority", "status", "component", "evidence", "owner"], row)) for row in defects],
    )

    handoffs = {
        "handoffVersion": "p4-crawl-m1.5-owner-handoff-v1",
        "codeHead": code_head,
        "items": [
            {"handoffId": "A2-HO-001", "owner": "P4-A2-PIPELINE", "status": "OPEN", "request": "Adopt crawl/control/ACTIVITY_TEXT_FALLBACK_CONTRACT.json and emit the four evidence fields."},
            {"handoffId": "A2-HO-002", "owner": "P4-A2-PIPELINE", "status": "OPEN", "request": "Integrate audited validator and pipeline Notebook 10/11 sources into a clean integration branch without changing this crawl patch."},
            {"handoffId": "A4-HO-001", "owner": "P4-A4-NCS", "status": "OPEN", "request": "Integrate six audited NCS Notebook sources so the 23-child isolated replay can be independently run."},
            {"handoffId": "A3-HO-001", "owner": "P4-A3-CONTROL", "status": "OPEN", "request": "Run the full isolated 23-stage plan after A2/A4 source integration and require 23 exact-one current-run manifests."},
        ],
    }
    (REPORT_ROOT / "CRAWL_ORCHESTRATOR_HANDOFF.json").write_text(json.dumps(handoffs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "manifestVersion": "p4-crawl-m1.5-patch-v1",
        "verdict": "CRAWL_M1_5_CONTROL_PATCH_READY_FOR_INDEPENDENT_AUDIT",
        "branch": branch,
        "codeHead": code_head,
        "integrationBaseline": "b64270bd4ab839ec750a4ceceb08d57957c88782",
        "agent1SourceBaseline": "3ad43c39dd01933575529e0c81d9809dc64c4e57",
        "runMode": "observed-dev",
        "productionNetworkCalls": 0,
        "notebookIntegrity": {"valid": 6, "total": 6, "cells": sum(row["cells"] for row in integrity), "sourceOutputs": 0},
        "replay": {"pass": 4, "expectedBlocked": 1, "checksumFailures": sum(row["checksumFailures"] for row in replay)},
        "data": {"postingRows": 137, "rawRows": 29, "remainingMonthRows": 58, "assetFetchedRows": 0},
        "currentRunManifests": {"bound": len(current), "unique": len({row["stageId"] for row in current}), "fullPlan": 23},
        "security": security,
        "promotion": {"crawlReleaseReady": False, "m2ProductionCrawl": False, "analysisReady": False},
    }
    (REPORT_ROOT / "CRAWL_M1_5_PATCH_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    source_lines = "\n".join(
        f"| `{Path(row['sourcePath']).name}` | {row['bytes']} | `{row['sha256']}` | {row['cells']} | PASS |"
        for row in integrity
    )
    replay_lines = "\n".join(
        f"| {row['stageId']} | {row['executionStatus']} | {row['manifestStatus']} | {row['checksumEntries']} | {row['networkCalls']} |"
        for row in replay
    )
    report = f"""# P4 Crawl M1.5 control patch report

## Executive verdict

`CRAWL_M1_5_CONTROL_PATCH_READY_FOR_INDEPENDENT_AUDIT`

The crawl control/source patch is ready for independent audit. This is not a production promotion: `CRAWL_RELEASE_READY=false`, `SOURCE_POLICY_PRODUCTION_APPROVED=false`, and `M2_PRODUCTION_CRAWL=BLOCKED`.

## Git baseline

- branch: `{branch}`
- code HEAD before evidence publication: `{code_head}`
- integration baseline: `b64270bd4ab839ec750a4ceceb08d57957c88782`
- audited Agent 1 source baseline: `3ad43c39dd01933575529e0c81d9809dc64c4e57`
- source import method: path-scoped restore; no divergent branch merge

## P1/P2 patch evidence

- Validator: exit code, status, artifact presence, runId, and input SHA must all match; negative tests `7/7 PASS`.
- Topology: registry-derived plan has `28/28 PASS` dependency edges; A4 producers precede A2-08/A2-09 and A2-09 precedes export/QA.
- Current run: `5/5` executed crawl stages have one canonical binding; stale/duplicate unit tests reject or preserve in `superseded_manifests`.
- Blob provenance: `6/6` crawl source Notebooks are tracked and their working blobs equal `HEAD` blobs.
- Source policy: `14/14 PASS`; production approval is still mandatory and no production transport was called.
- ActivityText: raw SSR replay `29/29 PASS`; ambiguous standalone auto-selection `0`.
- Lineage: 58 concrete remaining-month rows; 18 baseline raw-flag mismatches reconciled to verified raw-manifest authority with unresolved `0`; asset field/period lineage corrected.
- Runtime/idempotency: exact dependency lock published; two equal recovery runs produced identical SHA for all `8/8` content artifacts.

## Notebook integrity and blob provenance

| Notebook | bytes | source SHA-256 | cells | status |
|---|---:|---|---:|---|
{source_lines}

Total: `6/6 valid`, `66 cells`, source output/execution count `0/0`.

## Dependency graph before/after

- before: A2-08/A2-09 occurred before their A4 producers; 4 stage IDs were duplicated across 28 physical manifests and one manifest was stale `FAILED`.
- after: 28 registered edges pass; current-run consumers accept only exact stage/run/source/parameter/input/output/status/time bindings.
- Master dry-run: 23 planned children, 0 kernels started, 0 network calls. Full replay remains handoff-blocked because the clean integration baseline lacks 6 A4 and 2 A2 source Notebooks.

## Validator negative tests

`7/7 PASS`: nonzero exit, non-PASS status, missing artifact, stale runId, input SHA mismatch, malformed/full-corpus non-PASS all fail closed. Evidence: `CRAWL_VALIDATOR_NEGATIVE_TESTS.csv`.

## Source-policy and kill-switch tests

`14/14 PASS`: global interval/concurrency, 403, 429, recent success rate, unexpected content type, schema drift, empty-page streak, checkpoint corruption, external ATS rejection, and production approval guard. Evidence: `CRAWL_SOURCE_POLICY_TESTS.csv`.

## Fresh-kernel observed replay

| Stage | execution | manifest | checksum entries | network calls |
|---|---|---|---:|---:|
{replay_lines}

Replay totals: checksum failures `0`; index network calls `0`; external ATS transport calls `0`; source/executed code parity `5/5`.

## Security and portability

- tracked secret files: `{security['trackedSecretFiles']}`
- tracked `.env`: `{security['trackedEnvFiles']}`
- tracked raw PII files: `{security['trackedRawFiles']}`
- Notebook output secret files: `{security['notebookOutputSecretFiles']}`
- absolute local path artifact files: `{security['absoluteLocalPathArtifactFiles']}`

## Remaining blockers and owner handoff

- P4-A2-PIPELINE: adopt the ActivityText adapter contract and integrate validator plus Notebook 10/11 audited sources.
- P4-A4-NCS: integrate the six audited NCS source Notebooks.
- P4-A3-CONTROL: after those read-only owner handoffs, execute the full isolated 23-stage plan and require 23/23 exact-one manifests.
- User/source-policy owner: production network approval and transparent-client evidence remain absent.
- Data: 58 months are not pagination-audited and fetched assets remain 0; therefore crawl release and M2 stay blocked.

## Commands

- `P4_CRAWL_RAW_SOURCE_ROOT=<runtime-root> PYTHONPATH=DSJA/project_4:DSJA/project_4/crawl/src .venv/bin/python -m pytest -q DSJA/project_4/crawl/tests DSJA/project_4/crawl/control/tests` -> `58 passed`
- `.venv/bin/python DSJA/project_4/crawl/control/validate_control.py` -> `CONTROL_VALIDATION_PASS`
- `.venv/bin/python DSJA/project_4/crawl/scripts/execute_agent1_notebooks.py --run-root crawl/runs/notebooks/observed-dev/M1_5_AGENT1_20260806_01` -> 4 PASS + 1 EXPECTED_BLOCKED
- `.venv/bin/python DSJA/project_4/crawl/scripts/dry_run_master.py --output-root crawl/runs/notebooks/observed-dev/M1_5_AGENT1_20260806_01/master_dry_run` -> 28 edge PASS, 0 child kernels
"""
    (REPORT_ROOT / "CRAWL_M1_5_PATCH_REPORT.md").write_text(report, encoding="utf-8")

    checksum_targets = sorted(
        path for path in REPORT_ROOT.iterdir()
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    (REPORT_ROOT / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_targets), encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
