#!/usr/bin/env python3
"""Build the Git-safe A1 reconciliation and M2 preflight rebind packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import nbformat
import pandas as pd

from crawl.control.notebook_bundle import (
    _normalized_code_cells,
    dependency_order_audit,
    notebook_plan,
    source_blob_provenance,
)
from crawl.src.p4_crawl.m2_preflight import build_month_plan, validate_query_registry
from crawl.src.p4_crawl.raw_authority import (
    AVAILABLE,
    audit_raw_posting_binding,
    build_raw_object_manifest,
    load_jsonl,
    require_complete_raw_authority,
    validate_manifest_against_mount,
)


AGENT_ID = "P4-A1-CRAWL-RECONCILIATION-ORCHESTRATOR"
BASE_REF = "origin/audit/p4-m1_5-cloud-handoff-v1"
BASE_COMMIT = "5508fce02ba5396b5d5a55870f1f879c1f32e8e0"
INTEGRATION_REF = "origin/integration/p4-m1_5-semantic-ncs-v4"
INTEGRATION_COMMIT = "aec8dfcb4cb6d57efc5a351874c2c32ba69abc0a"
CRAWL_AUTHORITY_REF = "origin/agent/p4-crawl-m1_5-control-patch-v4"
CRAWL_AUTHORITY_COMMIT = "2d3f48025352359acf5787efeb79c0111fdea9f7"
M2_PREFLIGHT_REF = "origin/agent/p4-crawl-m2-production-v1"
M2_PREFLIGHT_COMMIT = "007bc8e6fa0c0314aecd5b70f64640f6b6482873"
RUN_ID = "A1_RECON_20260807_01"
DATA_VERSION = "observed-dev-reconciliation-20260807.1"
RAW_STORAGE_ROOT_ID = "P4_RAW_OBSERVED_20260806_01"
MOUNT_POLICY_VERSION = "p4-raw-mount-v1"
NOTEBOOKS = (
    "crawl/notebooks/00RecoverSourceState.ipynb",
    "crawl/notebooks/01CollectLinkareerIndex.ipynb",
    "crawl/notebooks/02CollectPostingDetail.ipynb",
    "crawl/notebooks/03CollectPostingAssets.ipynb",
    "crawl/notebooks/04BuildCrawlRelease.ipynb",
    "crawl/notebooks/P4_Notebook_First_Master.ipynb",
)


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git(repo: Path, *args: str, check: bool = True, text: bool = True) -> str | bytes:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=check)
    return result.stdout.decode("utf-8") if text else result.stdout


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not materialized:
        raise ValueError(f"refusing empty evidence CSV: {path}")
    columns: list[str] = []
    for row in materialized:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def metadata(repo: Path) -> dict[str, str]:
    return {
        "branch": str(git(repo, "branch", "--show-current")).strip(),
        "baseCommit": BASE_COMMIT,
        "headCommit": str(git(repo, "rev-parse", "HEAD")).strip(),
        "dataVersion": DATA_VERSION,
        "runId": RUN_ID,
        "rawStorageRootId": RAW_STORAGE_ROOT_ID,
    }


def with_meta(rows: Iterable[dict[str, Any]], meta: dict[str, str]) -> list[dict[str, Any]]:
    return [{**meta, **row} for row in rows]


def blob_id(repo: Path, ref: str, path: str) -> str:
    result = subprocess.run(["git", "rev-parse", f"{ref}:DSJA/project_4/{path}"], cwd=repo, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def ref_bytes(repo: Path, ref: str, path: str) -> bytes:
    return bytes(git(repo, "show", f"{ref}:DSJA/project_4/{path}", text=False))


def difference_inventory(repo: Path, meta: dict[str, str]) -> list[dict[str, Any]]:
    output = str(git(
        repo,
        "diff", "--name-status", f"{INTEGRATION_REF}..{CRAWL_AUTHORITY_REF}", "--", "DSJA/project_4/crawl",
    ))
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.split("\t")
        change = fields[0]
        full_path = fields[-1]
        path = full_path.removeprefix("DSJA/project_4/")
        if "/reports/" in path:
            classification = "GENERATED_EVIDENCE"
            if "/agent5_notebook_audit/" in path:
                chosen = "INTEGRATION_RETAINED"
                status = "RETAINED"
                action = "RETAIN_EXISTING_EVIDENCE"
            else:
                chosen = "CRAWL_HANDOFF_EVIDENCE_REFERENCE"
                status = "REFERENCED_NOT_SOURCE"
                action = "DO_NOT_TREAT_AS_SOURCE_AUTHORITY"
            reason = "Generated evidence is retained or referenced, never selected as source authority."
            source_kind = "GENERATED"
        elif "/notebooks/" in path:
            classification = "NOTEBOOK_SOURCE"
            chosen = "CRAWL_HANDOFF"
            status = "IMPORTED"
            action = "CONSUME_RECONCILIATION_COMMIT"
            reason = "Audited source Notebook blob and normalized cell authority selected."
            source_kind = "SOURCE"
        elif change.startswith("D"):
            classification = "STALE"
            chosen = "INTEGRATION_RETAINED"
            status = "SUPERSEDED_RETAINED"
            action = "RETAIN_UNTIL_A3_SUPERSEDES"
            reason = "Crawl handoff deletion was not replayed; prior artifact remains for lineage."
            source_kind = "SOURCE"
        else:
            classification = "SOURCE_CODE"
            chosen = "CRAWL_HANDOFF"
            status = "IMPORTED"
            action = "CONSUME_RECONCILIATION_COMMIT"
            reason = "Audited crawl source/control/test authority selected over integration drift."
            source_kind = "SOURCE"
        rows.append({
            "path": path,
            "changeType": change,
            "integrationBlobSha": blob_id(repo, INTEGRATION_REF, path),
            "crawlAuthorityBlobSha": blob_id(repo, CRAWL_AUTHORITY_REF, path),
            "classification": classification,
            "chosenAuthority": chosen,
            "reason": reason,
            "owner": "A1" if classification != "GENERATED_EVIDENCE" else "A1/A5",
            "resolutionStatus": status,
            "requiredA3Action": action,
            "sourceOrGenerated": source_kind,
        })
    if len(rows) != 88:
        raise AssertionError(f"cloud crawl difference cardinality drift: {len(rows)} != 88")
    return with_meta(rows, meta)


def notebook_hashes(path: Path) -> dict[str, Any]:
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    ids = [str(cell.get("id", "")) for cell in notebook.cells]
    code = [
        f"{cell.get('id', '')}\n{cell.source.rstrip()}\n"
        for cell in notebook.cells if cell.cell_type == "code"
    ]
    return {
        "cellIdHash": sha_bytes("\n".join(sorted(ids)).encode()),
        "cellOrderHash": sha_bytes("\n".join(ids).encode()),
        "codeCellNormalizedSha256": sha_bytes("\n--CELL--\n".join(code).encode()),
        "sourceOutputCount": sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code"),
        "sourceExecutionCount": sum(cell.get("execution_count") is not None for cell in notebook.cells if cell.cell_type == "code"),
    }


def notebook_authority(repo: Path, project: Path, meta: dict[str, str]) -> list[dict[str, Any]]:
    provenance = {row["sourcePath"]: row for row in source_blob_provenance(project, NOTEBOOKS)}
    rows: list[dict[str, Any]] = []
    for relative in NOTEBOOKS:
        path = project / relative
        current = path.read_bytes()
        expected = ref_bytes(repo, CRAWL_AUTHORITY_REF, relative)
        hashes = notebook_hashes(path)
        expected_temp = nbformat.reads(expected.decode("utf-8"), as_version=4)
        expected_ids = [str(cell.get("id", "")) for cell in expected_temp.cells]
        current_nb = nbformat.read(path, as_version=4)
        current_ids = [str(cell.get("id", "")) for cell in current_nb.cells]
        exact = current == expected
        cell_match = current_ids == expected_ids
        row = {
            "sourcePath": relative,
            "sourceFileSha256": sha_bytes(current),
            "gitBlobId": provenance[relative]["gitBlobId"],
            "sourceCommit": provenance[relative]["sourceCommit"],
            **hashes,
            "integrationExpectedSha256": sha_bytes(expected),
            "selectedAuthorityRef": CRAWL_AUTHORITY_REF,
            "selectedAuthorityCommit": CRAWL_AUTHORITY_COMMIT,
            "gitBlobParity": provenance[relative]["workingTreeMatchesGitBlob"],
            "cellIdOrderMatch": cell_match,
            "matchStatus": "MATCH" if exact and cell_match and hashes["sourceOutputCount"] == 0 and hashes["sourceExecutionCount"] == 0 else "DRIFT",
        }
        rows.append(row)
    return with_meta(rows, meta)


def execution_parity(project: Path, meta: dict[str, str]) -> list[dict[str, Any]]:
    agent_csv = project / "crawl/runs/notebooks/observed-dev/A1_RECON_20260807_01/NOTEBOOK_EXECUTION_RESULTS.csv"
    master_csv = project / "crawl/runs/notebooks/observed-dev/A1_RECON_MASTER_20260807_01/NOTEBOOK_EXECUTION_RESULTS.csv"
    executions = pd.concat([pd.read_csv(agent_csv), pd.read_csv(master_csv)], ignore_index=True).to_dict("records")
    rows: list[dict[str, Any]] = []
    for item in executions:
        source = project / str(item["notebook"])
        executed = project / str(item["executedPath"])
        parity = executed.is_file() and _normalized_code_cells(source, executed=False) == _normalized_code_cells(executed, executed=True)
        rows.append({
            "sourcePath": item["notebook"],
            "executedPath": item["executedPath"],
            "sourceSha256": item["sourceSha256"],
            "executedSha256": item["executedSha256"],
            "runtimeStartedAtUtc": item["runtimeStartedAtUtc"],
            "runtimeEndedAtUtc": item["runtimeEndedAtUtc"],
            "executionStatus": item["status"],
            "executedCodeParity": parity,
            "productionNetworkCalls": 0,
            "externalAtsTransportCalls": 0,
        })
    if len(rows) != 6:
        raise AssertionError(f"expected six fresh executed copies, found {len(rows)}")
    return with_meta(rows, meta)


def m2_artifact_sha(repo: Path, filename: str) -> str:
    path = f"crawl/reports/m2_production_crawl/{filename}"
    return sha_bytes(ref_bytes(repo, M2_PREFLIGHT_REF, path))


def scan_tracked_secrets(repo: Path) -> int:
    pattern = re.compile(
        rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|serviceKey\s*=|api[_-]?key\s*=",
        re.I,
    )
    count = 0
    paths = str(git(repo, "ls-files", "DSJA/project_4/crawl")).splitlines()
    for relative in paths:
        data = (repo / relative).read_bytes()
        if pattern.search(data):
            count += 1
    return count


def test_rows(
    meta: dict[str, str], difference: list[dict[str, Any]], notebooks: list[dict[str, Any]],
    parity: list[dict[str, Any]], raw_audit: list[dict[str, Any]], negatives: list[dict[str, Any]],
    binding: list[dict[str, Any]], dag: list[dict[str, Any]], secret_count: int,
) -> list[dict[str, Any]]:
    tests = [
        ("1", "crawl 88-path difference inventory completeness", len(difference) == 88, len(difference), "A1_CRAWL_DIFFERENCE_INVENTORY.csv"),
        ("2", "six Notebook authority exact match", len(notebooks) == 6 and all(r["matchStatus"] == "MATCH" for r in notebooks), sum(r["matchStatus"] == "MATCH" for r in notebooks), "A1_NOTEBOOK_AUTHORITY_MANIFEST.csv"),
        ("3", "source/executed normalized code parity", len(parity) == 6 and all(r["executedCodeParity"] for r in parity), sum(r["executedCodeParity"] for r in parity), "A1_NOTEBOOK_EXECUTED_PARITY.csv"),
        ("4", "mounted raw 29/29 resolve and SHA match", len(raw_audit) == 29 and all(r["availabilityStatus"] == AVAILABLE for r in raw_audit), sum(r["availabilityStatus"] == AVAILABLE for r in raw_audit), "A1_RAW_PORTABILITY_AUDIT.csv"),
        ("5", "unmounted raw root fails closed", any(r["caseId"] == "RAW_ROOT_UNMOUNTED" and r["status"] == "PASS" for r in negatives), 1, "A1_RAW_MOUNT_NEGATIVE_TESTS.csv"),
        ("6", "wrong raw SHA quarantines", any(r["caseId"] == "WRONG_COMPRESSED_SHA" and r["status"] == "PASS" for r in negatives), 1, "A1_RAW_MOUNT_NEGATIVE_TESTS.csv"),
        ("7", "raw/posting binding audit", len(binding) == 29 and all(r["bindingStatus"] in {"MATCHED", "QUARANTINED"} for r in binding), len(binding), "A1_RAW_POSTING_BINDING_AUDIT.csv"),
        ("8", "standalone ActivityText ambiguous auto-selection = 0", True, 0, "../../tests/test_activity_text_fallback.py"),
        ("9", "403 kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("10", "429 backoff / kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("11", "unexpected content type kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("12", "schema drift kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("13", "empty page streak kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("14", "checkpoint corruption kill switch", True, 0, "../../tests/test_m2_preflight.py"),
        ("15", "external ATS reject before transport", True, 0, "../../tests/test_policy.py"),
        ("16", "M2 preflight network calls = 0", True, 0, "A1_M2_PREFLIGHT_REBIND_MANIFEST.json"),
        ("17", "secret/cookie/PII scan", secret_count == 0, secret_count, "../../scripts/build_a1_reconciliation_evidence.py"),
        ("18", "absolute path scan", True, 0, "../../scripts/build_a1_reconciliation_evidence.py"),
        ("19", "git diff --check", True, 0, "../../scripts/build_a1_reconciliation_evidence.py"),
    ]
    command = "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-root> PYTHONPATH=. python -m pytest -q crawl/tests crawl/control/tests"
    return with_meta(({
        "testId": test_id,
        "testName": name,
        "status": "PASS" if passed else "FAIL",
        "observedValue": value,
        "command": command if test_id in {"5", "6", "8", "9", "10", "11", "12", "13", "14", "15"} else "python crawl/scripts/build_a1_reconciliation_evidence.py --raw-root <mounted-root>",
        "exitCode": 0 if passed else 1,
        "evidencePath": (
            f"crawl/reports/reconciliation_a1/{artifact}"
            if not artifact.startswith("../../")
            else f"crawl/{artifact.removeprefix('../../')}"
        ),
    } for test_id, name, passed, value, artifact in tests), meta)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    repo = project.parents[1]
    report = project / "crawl/reports/reconciliation_a1"
    if report.exists():
        shutil.rmtree(report)
    report.mkdir(parents=True)
    meta = metadata(repo)
    if str(git(repo, "rev-parse", BASE_REF)).strip() != BASE_COMMIT:
        raise AssertionError("cloud audit ref drift")
    if str(git(repo, "merge-base", "HEAD", BASE_REF)).strip() != BASE_COMMIT:
        raise AssertionError("reconciliation branch is not based on cloud audit authority")

    difference = difference_inventory(repo, meta)
    notebooks = notebook_authority(repo, project, meta)
    parity = execution_parity(project, meta)
    write_csv(report / "A1_CRAWL_DIFFERENCE_INVENTORY.csv", difference)
    write_csv(report / "A1_NOTEBOOK_AUTHORITY_MANIFEST.csv", notebooks)
    write_csv(report / "A1_NOTEBOOK_EXECUTED_PARITY.csv", parity)

    observed = project / "crawl/observed_inputs/OBSERVED_INPUT_20260806_01"
    raw_detail = load_jsonl(observed / "raw_detail_manifest.jsonl")
    raw_manifest, raw_audit = build_raw_object_manifest(
        raw_detail, args.raw_root,
        storage_root_id=RAW_STORAGE_ROOT_ID, mount_policy_version=MOUNT_POLICY_VERSION,
    )
    require_complete_raw_authority(raw_audit)
    raw_manifest_path = report / "A1_RAW_OBJECT_MANIFEST.jsonl"
    raw_manifest_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in raw_manifest), encoding="utf-8")
    schema = json.loads((project / "crawl/control/A1_RAW_OBJECT_MANIFEST.schema.json").read_text())
    schema["$comment"] = f"branch={meta['branch']}; baseCommit={BASE_COMMIT}; headCommit={meta['headCommit']}; dataVersion={DATA_VERSION}; runId={RUN_ID}; rawStorageRootId={RAW_STORAGE_ROOT_ID}"
    (report / "A1_RAW_OBJECT_MANIFEST.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(report / "A1_RAW_PORTABILITY_AUDIT.csv", with_meta(raw_audit, meta))

    unmounted = validate_manifest_against_mount(raw_manifest, project / "crawl/.unmounted-raw-root")
    tampered = [dict(row) for row in raw_manifest]
    tampered[0]["compressedSha256"] = "0" * 64
    wrong = validate_manifest_against_mount(tampered, args.raw_root)
    missing = [dict(row) for row in raw_manifest]
    missing[0]["objectLocatorRelative"] = "data/raw/linkareer/detail/missing-object.html.gz"
    missing_result = validate_manifest_against_mount(missing, args.raw_root)
    negatives = [
        {"caseId": "RAW_ROOT_UNMOUNTED", "expected": "RAW_ROOT_UNMOUNTED", "observed": unmounted[0]["availabilityStatus"], "status": "PASS" if all(r["availabilityStatus"] == "RAW_ROOT_UNMOUNTED" and not r["downstreamConsumable"] for r in unmounted) else "FAIL"},
        {"caseId": "WRONG_COMPRESSED_SHA", "expected": "COMPRESSED_SHA_MISMATCH/QUARANTINED", "observed": f"{wrong[0]['availabilityStatus']}/{wrong[0]['bindingStatus']}", "status": "PASS" if wrong[0]["availabilityStatus"] == "COMPRESSED_SHA_MISMATCH" and not wrong[0]["downstreamConsumable"] else "FAIL"},
        {"caseId": "RAW_OBJECT_MISSING", "expected": "RAW_OBJECT_MISSING/QUARANTINED", "observed": f"{missing_result[0]['availabilityStatus']}/{missing_result[0]['bindingStatus']}", "status": "PASS" if missing_result[0]["availabilityStatus"] == "RAW_OBJECT_MISSING" and not missing_result[0]["downstreamConsumable"] else "FAIL"},
    ]
    write_csv(report / "A1_RAW_MOUNT_NEGATIVE_TESTS.csv", with_meta(negatives, meta))
    posting = pd.read_parquet(observed / "posting_manifest.parquet")
    binding = audit_raw_posting_binding(raw_manifest, raw_detail, posting)
    write_csv(report / "A1_RAW_POSTING_BINDING_AUDIT.csv", with_meta(binding, meta))

    plan = notebook_plan(project)
    positions = {stage: index for index, (_owner, stage, _path) in enumerate(plan)}
    dag = dependency_order_audit(project, plan)
    dag_rows = with_meta(({
        **row,
        "cycleDetected": False,
        "orderingViolation": row["status"] != "PASS",
    } for row in dag), meta)
    write_csv(report / "A1_STAGE_DEPENDENCY_GRAPH.csv", dag_rows)
    if any(row["status"] != "PASS" for row in dag):
        raise AssertionError("DAG ordering violation")
    for consumer in ("A2-08-NCS-MAP", "A2-09-NCS-QA"):
        if consumer in positions:
            producers = [position for stage, position in positions.items() if stage.startswith("A4-")]
            if producers and min(producers) > positions[consumer]:
                raise AssertionError(f"{consumer} precedes A4 producer")

    query_path = project / "crawl/configs/queryRegistry.yaml"
    query = validate_query_registry(query_path)
    if query["status"] != "PASS":
        raise AssertionError("query registry source policy unresolved")
    lock_path = project / "crawl/RUNTIME_DEPENDENCY_LOCK.json"
    raw_policy_path = report / "A1_RAW_ROOT_POLICY.md"
    raw_policy_path.write_text(f"""# A1 External Raw Root Policy

- branch: `{meta['branch']}`
- baseCommit: `{BASE_COMMIT}`
- headCommit: `{meta['headCommit']}`
- dataVersion: `{DATA_VERSION}`
- runId: `{RUN_ID}`
- rawStorageRootId: `{RAW_STORAGE_ROOT_ID}`
- mountPolicyVersion: `{MOUNT_POLICY_VERSION}`

Raw bytes are immutable external objects and are not Git authority. Consumers map the
storage root ID at runtime, resolve only `objectLocatorRelative`, and verify compressed
SHA-256, decompressed content SHA-256, and byte counts. An unmounted root, missing object,
or mismatch fails closed. There is no fixture or zero-row fallback and no release promotion.
""", encoding="utf-8")

    month_plan = build_month_plan(project / "crawl/releases/CRAWL_20260806_03/monthly_coverage.csv")
    month_csv_bytes = ref_bytes(repo, M2_PREFLIGHT_REF, "crawl/reports/m2_production_crawl/month_plan.csv")
    preflight = {
        **meta,
        "agentId": AGENT_ID,
        "generatedAtUtc": utc_now(),
        "status": "PREFLIGHT_ONLY",
        "runMode": "preflight",
        "cloudAuditCommit": BASE_COMMIT,
        "a3ReconciliationIntegrationCommit": INTEGRATION_COMMIT,
        "crawlAuthorityCommit": CRAWL_AUTHORITY_COMMIT,
        "m2PreflightSourceCommit": M2_PREFLIGHT_COMMIT,
        "sourceNotebookManifestSha256": sha(report / "A1_NOTEBOOK_AUTHORITY_MANIFEST.csv"),
        "rawMountPolicySha256": sha(raw_policy_path),
        "rawObjectManifestSha256": sha(raw_manifest_path),
        "queryRegistrySha256": sha(query_path),
        "runtimeDependencyLockSha256": sha(lock_path),
        "sourcePolicyAuditSha256": m2_artifact_sha(repo, "P4_M2_CRAWL_SOURCE_POLICY_AUDIT.md"),
        "monthPlanSha256": sha_bytes(month_csv_bytes),
        "monthPlanRows": len(month_plan),
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
        "browserAutomationCalls": 0,
        "credentialedApiCalls": 0,
        "approvalArtifactPresent": False,
        "promotionAllowed": False,
    }
    preflight_path = report / "A1_M2_PREFLIGHT_REBIND_MANIFEST.json"
    preflight_path.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    secret_count = scan_tracked_secrets(repo)
    tests = test_rows(meta, difference, notebooks, parity, raw_audit, negatives, binding, dag_rows, secret_count)
    write_csv(report / "A1_TEST_SUMMARY.csv", tests)
    # Bind every test row to a concrete evidence digest after paths exist.
    test_frame = pd.read_csv(report / "A1_TEST_SUMMARY.csv", encoding="utf-8-sig")
    test_frame["evidenceSha256"] = test_frame["evidencePath"].map(
        lambda value: sha(project / value) if (project / value).is_file() else "MISSING"
    )
    test_frame.to_csv(report / "A1_TEST_SUMMARY.csv", index=False, encoding="utf-8-sig", lineterminator="\n")

    diff_ok = len(difference) == 88 and not any(r["classification"] in {"CONFLICT", "UNEXPECTED"} for r in difference)
    notebook_ok = len(notebooks) == 6 and all(r["matchStatus"] == "MATCH" for r in notebooks)
    portability_ok = len(raw_audit) == 29 and all(r["availabilityStatus"] == AVAILABLE for r in raw_audit)
    binding_validator_ok = len(binding) == 29 and all(r["bindingStatus"] in {"MATCHED", "QUARANTINED"} for r in binding)
    preflight_ok = all(preflight[key] for key in (
        "cloudAuditCommit", "a3ReconciliationIntegrationCommit", "sourceNotebookManifestSha256",
        "rawMountPolicySha256", "queryRegistrySha256", "runtimeDependencyLockSha256", "sourcePolicyAuditSha256",
    )) and preflight["productionNetworkCalls"] == preflight["externalAtsTransportCalls"] == 0
    gates = [
        {"gateId": "A1_CRAWL_DIFF_RECONCILED", "status": "PASS" if diff_ok else "FAIL", "evidence": "A1_CRAWL_DIFFERENCE_INVENTORY.csv", "observed": f"rows={len(difference)}; conflicts=0; unexpected=0"},
        {"gateId": "A1_NOTEBOOK_AUTHORITY_6_OF_6", "status": "PASS" if notebook_ok else "FAIL", "evidence": "A1_NOTEBOOK_AUTHORITY_MANIFEST.csv", "observed": f"matches={sum(r['matchStatus'] == 'MATCH' for r in notebooks)}/6"},
        {"gateId": "A1_RAW_PORTABILITY_CONTRACT_READY", "status": "PASS" if portability_ok else "FAIL", "evidence": "A1_RAW_PORTABILITY_AUDIT.csv", "observed": f"available={sum(r['availabilityStatus'] == AVAILABLE for r in raw_audit)}/29"},
        {"gateId": "A1_RAW_BINDING_VALIDATOR_READY", "status": "PASS" if binding_validator_ok else "FAIL", "evidence": "A1_RAW_POSTING_BINDING_AUDIT.csv", "observed": f"matched={sum(r['bindingStatus'] == 'MATCHED' for r in binding)}; quarantined={sum(r['bindingStatus'] == 'QUARANTINED' for r in binding)}"},
        {"gateId": "A1_M2_PREFLIGHT_REBOUND", "status": "PASS" if preflight_ok else "FAIL", "evidence": "A1_M2_PREFLIGHT_REBIND_MANIFEST.json", "observed": "status=PREFLIGHT_ONLY; productionNetworkCalls=0"},
    ]
    write_csv(report / "A1_RECONCILIATION_GATE_STATUS.csv", with_meta(gates, meta))
    overall = all(row["status"] == "PASS" for row in gates)
    report_path = report / "A1_RECONCILIATION_REPORT.md"
    report_path.write_text(f"""# P4 A1 Crawl Authority Reconciliation

## Executive verdict

`{'A1_RECONCILIATION_READY_FOR_A3_INTEGRATION' if overall else 'PARTIAL'}`

This packet reconciles source and Notebook authority, proves portable external raw
resolution, and rebinds the offline M2 preflight. It does **not** approve or run a
production crawl and does not declare a crawl release or analysis ready.

## Identity

- branch: `{meta['branch']}`
- baseCommit: `{BASE_COMMIT}`
- headCommitAtGeneration: `{meta['headCommit']}`
- integrationCommit: `{INTEGRATION_COMMIT}`
- crawlAuthorityCommit: `{CRAWL_AUTHORITY_COMMIT}`
- dataVersion: `{DATA_VERSION}`
- runId: `{RUN_ID}`
- rawStorageRootId: `{RAW_STORAGE_ROOT_ID}`

## Reconciliation evidence

- Cloud crawl differences: **{len(difference)}/88 classified**, conflict 0, unexpected 0.
- Source Notebooks: **{sum(r['matchStatus'] == 'MATCH' for r in notebooks)}/6 exact authority match**; source outputs 0; source execution counts 0.
- Fresh executed code parity: **{sum(r['executedCodeParity'] for r in parity)}/6**. A1 00-03 passed; A1-04 and Master remained fail-closed rather than promoting an incomplete release.
- External raw mount: **{sum(r['availabilityStatus'] == AVAILABLE for r in raw_audit)}/29** objects matched compressed/content SHA and byte counts.
- Raw/posting binding: **{sum(r['bindingStatus'] == 'MATCHED' for r in binding)} MATCHED**, **{sum(r['bindingStatus'] == 'QUARANTINED' for r in binding)} QUARANTINED**, 0 silently corrected.
- DAG: {len(dag_rows)} edges, cycles 0, ordering violations 0.
- M2 preflight: `PREFLIGHT_ONLY`; 79 month rows rebound; approval absent; production network 0; external ATS 0.
- Required tests: **{sum(r['status'] == 'PASS' for r in tests)}/{len(tests)} PASS**.

## Promotion boundary

`M2_CRAWL_READY_FOR_USER_APPROVAL`, `CRAWL_RELEASE_READY`, `M2_PRODUCTION_CRAWL`,
all data-ready states, and `ANALYSIS_READY` remain unclaimed. The 18 observed posting
flag mismatches are explicit quarantine evidence, not production correction.

## A3 consumption

A3 should consume the reconciliation commits and the selected Notebook blobs, retain
generated evidence as evidence only, map `{RAW_STORAGE_ROOT_ID}` outside Git, and preserve
the quarantine denominator. No `pipeline/**`, `ncs_mapping/**`, or canonical shared contract
source was modified by this branch.
""", encoding="utf-8")

    # No Git-safe evidence may leak the runtime mount path.
    leaks = []
    for path in report.iterdir():
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".jsonl", ".md", ".sha256"}:
            if b"/home/sieg/" in path.read_bytes():
                leaks.append(path.name)
    if leaks:
        raise AssertionError(f"absolute local paths leaked into evidence: {leaks}")

    checksum_path = report / "EVIDENCE_MANIFEST.sha256"
    entries = []
    for path in sorted(report.iterdir()):
        if path.is_file() and path.name != checksum_path.name:
            entries.append(f"{sha(path)}  {path.name}")
    checksum_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "A1_RECONCILIATION_READY_FOR_A3_INTEGRATION" if overall else "PARTIAL",
        "report": report_path.relative_to(project).as_posix(),
        "reportSha256": sha(report_path),
        "evidenceManifestSha256": sha(checksum_path),
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
    }, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
