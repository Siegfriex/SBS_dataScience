#!/usr/bin/env python3
"""Validate an A1 canary handoff and publish fail-closed acceptance reports."""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from canary_acceptance_contract import (
    REQUIRED_ARTIFACTS, file_sha256, read_jsonl, read_jsonl_artifact, validate_approval,
    validate_checkpoint_chain, validate_checksum_manifest, validate_coverage,
    validate_kill_switch, validate_plan_and_stage, validate_raw_objects, validate_request_ledger,
    validate_redacted_handoff, validate_response_manifest,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def validate_git_head_artifacts(root: Path, names: tuple[str, ...]) -> tuple[list[str], str, str]:
    errors: list[str] = []
    try:
        top = Path(git_value(root, "rev-parse", "--show-toplevel"))
        head = git_value(root, "rev-parse", "HEAD")
        branch = git_value(root, "branch", "--show-current") or "DETACHED"
        tracked = set(git_value(top, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["HANDOFF_NOT_IN_GIT_WORKTREE"], "UNKNOWN", "UNKNOWN"
    for name in names:
        target = root / name
        relative = target.relative_to(top).as_posix()
        if relative not in tracked:
            errors.append(f"HANDOFF_ARTIFACT_NOT_IN_HEAD:{name}")
            continue
        head_blob = git_value(top, "rev-parse", f"HEAD:{relative}")
        worktree_blob = git_value(top, "hash-object", str(target))
        if head_blob != worktree_blob:
            errors.append(f"HANDOFF_ARTIFACT_DIRTY:{name}")
    return errors, branch, head


def validate_component_parquets(root: Path, run_id: str, data_version: str) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    allowed_statuses = {
        "FETCHED_VALID", "FETCHED_EMPTY_VALID", "NOT_FOUND", "EXPIRED", "POLICY_BLOCKED",
        "RETRY_EXHAUSTED", "PARSER_QUARANTINED", "DUPLICATE_CONTENT", "UNSUPPORTED_MIME",
    }
    for name in ("index_results.parquet", "detail_results.parquet", "asset_results.parquet"):
        parquet = pq.ParquetFile(root / name)
        frame = pd.read_parquet(root / name)
        counts[name] = len(frame)
        if frame.empty:
            required = {"canaryRunId", "canaryDataVersion", "terminalStatus", "schemaVersion", "emptyReason"}
            missing = required - set(frame.columns)
            if missing:
                errors.append(f"CANARY_PARQUET_COLUMNS_MISSING:{name}:{','.join(sorted(missing))}")
            metadata = {key.decode(): value.decode() for key, value in (parquet.schema_arrow.metadata or {}).items()}
            expected_metadata = {
                "p4.runId": run_id,
                "p4.dataVersion": data_version,
                "p4.schemaVersion": "p4-canary-handoff-v1",
                "p4.rowCount": "0",
            }
            for field, expected in expected_metadata.items():
                if metadata.get(field) != expected:
                    errors.append(f"CANARY_PARQUET_METADATA_MISMATCH:{name}:{field}")
            if not metadata.get("p4.emptyReason"):
                errors.append(f"CANARY_PARQUET_EMPTY_REASON_MISSING:{name}")
            continue
        required = {"canaryRunId", "canaryDataVersion", "terminalStatus"}
        missing = required - set(frame.columns)
        if missing:
            errors.append(f"CANARY_PARQUET_COLUMNS_MISSING:{name}:{','.join(sorted(missing))}")
            continue
        if not frame["canaryRunId"].eq(run_id).all():
            errors.append(f"CANARY_PARQUET_RUN_ID_MISMATCH:{name}")
        if not frame["canaryDataVersion"].eq(data_version).all():
            errors.append(f"CANARY_PARQUET_DATA_VERSION_MISMATCH:{name}")
        if frame["terminalStatus"].isna().any() or not frame["terminalStatus"].isin(allowed_statuses).all():
            errors.append(f"CANARY_PARQUET_TERMINAL_STATUS_INVALID:{name}")
    return errors, counts


def validate_legacy_tier0_packet(policy_path: Path) -> tuple[list[str], dict[str, Any]]:
    """Consume the A1 fixture-only blocked packet without promoting it to the v1 handoff."""
    if not policy_path.is_file():
        return ["LEGACY_TIER0_POLICY_MISSING"], {}
    root = policy_path.parent
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    run_id = str(policy.get("canaryRunId") or "NONE")
    names = (
        f"P4_CANARY_CRAWL_METRICS_{run_id}.csv",
        f"P4_CANARY_CRAWL_DEFECTS_{run_id}.csv",
        f"P4_CANARY_CRAWL_LINEAGE_{run_id}.csv",
        f"P4_CANARY_CRAWL_TIER0_CHECKS_{run_id}.csv",
        f"P4_CANARY_CRAWL_POLICY_{run_id}.json",
        f"P4_CANARY_CRAWL_REPORT_{run_id}.md",
    )
    manifest_name = f"EVIDENCE_MANIFEST_{run_id}.sha256"
    errors: list[str] = []
    for name in names + (manifest_name,):
        if not (root / name).is_file():
            errors.append(f"LEGACY_TIER0_ARTIFACT_MISSING:{name}")
    if errors:
        return errors, policy
    declared: set[str] = set()
    for line in (root / manifest_name).read_text(encoding="utf-8").splitlines():
        expected, name = line.split(maxsplit=1); name = name.strip(); declared.add(name)
        if name not in names or file_sha256(root / name) != expected:
            errors.append(f"LEGACY_TIER0_CHECKSUM_MISMATCH:{name}")
    if declared != set(names):
        errors.append("LEGACY_TIER0_CHECKSUM_SET_MISMATCH")
    git_errors, branch, head = validate_git_head_artifacts(root, names + (manifest_name,))
    errors.extend(git_errors)
    with (root / f"P4_CANARY_CRAWL_TIER0_CHECKS_{run_id}.csv").open(encoding="utf-8-sig", newline="") as stream:
        checks = list(csv.DictReader(stream))
    if len(checks) != 15 or any(row.get("status") != "PASS" for row in checks):
        errors.append("LEGACY_TIER0_CHECKS_NOT_15_PASS")
    if any(int(row.get("networkCalls", -1)) != 0 or int(row.get("externalAtsTransportCalls", -1)) != 0 for row in checks):
        errors.append("LEGACY_TIER0_TRANSPORT_NONZERO")
    with (root / f"P4_CANARY_CRAWL_METRICS_{run_id}.csv").open(encoding="utf-8-sig", newline="") as stream:
        metrics = list(csv.DictReader(stream))
    if len(metrics) != 1 or metrics[0].get("status") != "CANARY_BLOCKED_BY_POLICY":
        errors.append("LEGACY_TIER0_METRICS_STATUS_INVALID")
    if int(policy.get("networkCalls", -1)) != 0 or int(policy.get("externalAtsTransportCalls", -1)) != 0:
        errors.append("LEGACY_TIER0_POLICY_TRANSPORT_NONZERO")
    report_text = (root / f"P4_CANARY_CRAWL_REPORT_{run_id}.md").read_text(encoding="utf-8")
    match = re.search(r"headCommitAtRun: `([0-9a-f]{40})`", report_text)
    policy.update({
        "detectedBranch": branch, "detectedHead": head,
        "headCommitAtRun": match.group(1) if match else None,
        "evidenceManifestSha256": file_sha256(root / manifest_name),
        "tier0Checks": len(checks), "tier0ChecksPassed": sum(row.get("status") == "PASS" for row in checks),
    })
    return errors, policy


def scan_canary_contamination(project: Path, run_id: str, data_version: str) -> list[str]:
    """Search canonical/observed/NCS authority stores for submitted canary identifiers."""
    if run_id == "NONE":
        return ["CONTAMINATION_NOT_EVALUATED_NO_RUN_ID"]
    needles = {run_id, data_version}
    hits: list[str] = []
    roots = [project / "pipeline/data", project / "ncs_mapping/data/gold", project / "ncs_mapping/data/reference"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(project).as_posix()
            try:
                if path.suffix in {".csv", ".json", ".jsonl", ".yaml", ".yml", ".md"}:
                    text = path.read_text(encoding="utf-8-sig", errors="ignore")
                    if any(needle in text for needle in needles):
                        hits.append(relative)
                elif path.suffix == ".parquet":
                    frame = pd.read_parquet(path)
                    if any(frame.astype("string").eq(needle).any().any() for needle in needles):
                        hits.append(relative)
                elif path.suffix == ".duckdb":
                    try:
                        import duckdb
                    except ImportError:
                        hits.append(f"CONTAMINATION_SCAN_DEPENDENCY_MISSING:{relative}")
                        continue
                    with duckdb.connect(str(path), read_only=True) as connection:
                        tables = connection.execute(
                            "SELECT table_schema, table_name FROM information_schema.tables WHERE table_type='BASE TABLE'"
                        ).fetchall()
                        for schema, table in tables:
                            columns = connection.execute(
                                "SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=? AND data_type IN ('VARCHAR','TEXT')",
                                [schema, table],
                            ).fetchall()
                            for (column,) in columns:
                                qualified = f'"{schema}"."{table}"'
                                quoted_column = '"' + str(column).replace('"', '""') + '"'
                                placeholders = ",".join("?" for _ in needles)
                                found = connection.execute(
                                    f"SELECT COUNT(*) FROM {qualified} WHERE {quoted_column} IN ({placeholders})",
                                    list(needles),
                                ).fetchone()[0]
                                if found:
                                    hits.append(f"{relative}:{schema}.{table}.{column}")
            except Exception:  # fail closed on unreadable authority stores
                hits.append(f"CONTAMINATION_SCAN_ERROR:{relative}")
    return sorted(set(hits))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--handoff-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--a5-status", default="PASS_WITH_FINDINGS")
    parser.add_argument("--a5-commit", default="06cd0cb4cb3726b1408dce58ad24f935ca008de9")
    parser.add_argument("--a1-branch", default="UNKNOWN")
    parser.add_argument("--a1-commit", default="UNKNOWN")
    parser.add_argument("--a1-dirty-path-count", type=int, default=0)
    parser.add_argument("--test-command", default="python -m pytest -q integration/tests")
    parser.add_argument("--test-exit-code", type=int, default=0)
    parser.add_argument("--test-pass-count", type=int, default=0)
    parser.add_argument("--legacy-tier0-policy", type=Path)
    args = parser.parse_args()
    project = args.project_root.resolve(); handoff = args.handoff_root.resolve()
    report = args.report_root.resolve(); report.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)

    missing = [name for name in REQUIRED_ARTIFACTS if not (handoff / name).is_file()]
    plan = json.loads((handoff / "canary_plan.json").read_text(encoding="utf-8")) if (handoff / "canary_plan.json").is_file() else {}
    legacy_errors: list[str] = []
    legacy: dict[str, Any] = {}
    if args.legacy_tier0_policy:
        legacy_errors, legacy = validate_legacy_tier0_packet(args.legacy_tier0_policy.resolve())
    run_id = str(plan.get("canaryRunId") or legacy.get("canaryRunId") or "NONE")
    data_version = str(plan.get("canaryDataVersion") or "NONE")
    approval_id = str(legacy.get("approvalId") or "NONE")
    declared_network_calls = int(plan.get("networkCalls", 0))
    network_calls = 0
    errors: list[str] = []
    policy_errors: list[str] = []
    request_rows, request_artifact_errors, request_envelope = read_jsonl_artifact(
        handoff / "request_attempt.jsonl", "REQUEST_ATTEMPT", run_id
    )
    raw_rows: list[dict[str, Any]] = []
    raw_stats = {"rows": 0, "resolved": 0, "quarantined": 0}
    conflict_count = 0
    component_counts: dict[str, int] = {}
    contamination_hits: list[str] = ["CONTAMINATION_NOT_EVALUATED_NO_HANDOFF"]
    tier0_fixture_only = False
    errors.extend(request_artifact_errors)

    network_calls = len(request_rows)
    if network_calls:
        partial_plan = dict(plan)
        partial_plan["networkCalls"] = network_calls
        partial_plan["detailRequestCount"] = sum(row.get("logicalRequestType") == "DETAIL" for row in request_rows)
        partial_plan["assetRequestCount"] = sum(row.get("logicalRequestType") == "ASSET" for row in request_rows)
        policy_errors = validate_approval(handoff, partial_plan, network_calls, now)

    if missing:
        errors.extend(legacy_errors)
        legacy_policy_block = (
            not legacy_errors
            and legacy.get("status") == "CANARY_BLOCKED_BY_POLICY"
            and "CANARY_APPROVAL_MISSING" in legacy.get("approvalErrors", [])
            and int(legacy.get("networkCalls", -1)) == 0
        )
        if legacy_policy_block:
            policy_errors.extend(str(value) for value in legacy.get("approvalErrors", []))
        status = "CANARY_BLOCKED_BY_POLICY" if policy_errors else "CANARY_EVIDENCE_INSUFFICIENT"
        errors.extend(f"REQUIRED_ARTIFACT_MISSING:{name}" for name in missing)
    else:
        git_errors, detected_a1_branch, detected_a1_commit = validate_git_head_artifacts(handoff, REQUIRED_ARTIFACTS)
        errors.extend(git_errors)
        if plan.get("branch") != detected_a1_branch:
            errors.append("A1_HANDOFF_BRANCH_BINDING_MISMATCH")
        if args.a1_commit != detected_a1_commit:
            errors.append("A1_SUBMITTED_COMMIT_MISMATCH")
        source_commit = str(plan.get("sourceCommit") or "")
        source_binding = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, detected_a1_commit],
            cwd=handoff, capture_output=True,
        ) if re.fullmatch(r"[0-9a-f]{40}", source_commit) else None
        if source_binding is None or source_binding.returncode != 0:
            errors.append("A1_HANDOFF_SOURCE_COMMIT_NOT_ANCESTOR")
        errors.extend(validate_checksum_manifest(handoff))
        errors.extend(validate_redacted_handoff(handoff))
        stage = json.loads((handoff / "stage_manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((handoff / "stage_metrics.json").read_text(encoding="utf-8"))
        errors.extend(validate_plan_and_stage(plan, stage, metrics))
        component_errors, component_counts = validate_component_parquets(handoff, run_id, data_version)
        errors.extend(component_errors)
        contamination_hits = scan_canary_contamination(project, run_id, data_version)
        errors.extend(f"CANARY_CONTAMINATION:{hit}" for hit in contamination_hits)
        network_calls = len(request_rows)
        if network_calls != declared_network_calls:
            errors.append("DECLARED_NETWORK_CALL_COUNT_MISMATCH")
        request_errors, conflict_count = validate_request_ledger(request_rows)
        errors.extend(request_errors)
        raw_rows, raw_artifact_errors, raw_envelope = read_jsonl_artifact(
            handoff / "raw_object_manifest.jsonl", "RAW_OBJECT", run_id
        )
        response_rows, response_artifact_errors, response_envelope = read_jsonl_artifact(
            handoff / "request_response_manifest.jsonl", "REQUEST_RESPONSE", run_id
        )
        kill_switch_rows, kill_artifact_errors, kill_envelope = read_jsonl_artifact(
            handoff / "kill_switch_events.jsonl", "KILL_SWITCH_EVENT", run_id
        )
        quarantine_rows, quarantine_artifact_errors, quarantine_envelope = read_jsonl_artifact(
            handoff / "quarantine_manifest.jsonl", "QUARANTINE_RECORD", run_id
        )
        errors.extend(raw_artifact_errors + response_artifact_errors + kill_artifact_errors + quarantine_artifact_errors)
        errors.extend(validate_response_manifest(request_rows, response_rows, raw_rows))
        raw_errors, raw_stats = validate_raw_objects(raw_rows, args.raw_root.resolve() if args.raw_root else None)
        errors.extend(raw_errors)
        if raw_rows and args.raw_root is None:
            errors.append("RAW_ROOT_UNMOUNTED")
        raw_manifest_sha = file_sha256(handoff / "raw_object_manifest.jsonl")
        checkpoint = json.loads((handoff / "checkpoint_manifest.json").read_text(encoding="utf-8"))
        errors.extend(validate_checkpoint_chain(checkpoint, raw_manifest_sha))
        errors.extend(validate_kill_switch(request_rows, kill_switch_rows))
        coverage_errors, coverage_by_layer = validate_coverage(handoff / "canary_coverage.csv")
        errors.extend(coverage_errors)
        effective_plan = dict(plan)
        effective_plan["networkCalls"] = network_calls
        effective_plan["detailRequestCount"] = sum(row.get("logicalRequestType") == "DETAIL" for row in request_rows)
        effective_plan["assetRequestCount"] = sum(row.get("logicalRequestType") == "ASSET" for row in request_rows)
        binding = json.loads((handoff / "approval_binding.json").read_text(encoding="utf-8"))
        approval_id = str(binding.get("approvalId") or "NONE")
        policy_errors = validate_approval(handoff, effective_plan, network_calls, now)
        scope = plan.get("canaryScope") if isinstance(plan.get("canaryScope"), dict) else {}
        tier0_fixture_only = (
            network_calls == 0
            and scope.get("tier") == 0
            and scope.get("mode") == "fixture-only"
            and plan.get("runMode") == "fixture-only"
        )
        if binding.get("status") == "CANARY_APPROVAL_MISSING" and not tier0_fixture_only:
            policy_errors.append("CANARY_APPROVAL_MISSING")
        if policy_errors:
            status = "CANARY_BLOCKED_BY_POLICY"
        elif errors:
            status = "CANARY_REJECTED"
        elif args.a5_status not in {"PASS", "PASS_WITH_FINDINGS"} and not tier0_fixture_only:
            status = "CANARY_EVIDENCE_INSUFFICIENT"
            errors.append("A5_INDEPENDENT_AUDIT_NOT_ACCEPTABLE")
        else:
            status = "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE"

    head = git_value(project, "rev-parse", "HEAD")
    branch = git_value(project, "branch", "--show-current") or "DETACHED"
    command_text = "python3 integration/validate_canary_handoff.py [redacted portable arguments]"
    common = {
        "runId": run_id, "dataVersion": data_version, "approvalId": approval_id,
        "gitSha": head, "requestCount": len(request_rows),
        "manifestSha256": file_sha256(handoff / "CHECKSUMS.sha256") if (handoff / "CHECKSUMS.sha256").is_file() else str(legacy.get("evidenceManifestSha256") or "NONE"),
        "command": command_text, "exitCode": 0 if status == "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE" else 2,
        "policyVersion": str(plan.get("sourcePolicyVersion") or "NOT_EVALUATED"),
    }
    gate_rows = [
        {**common, "gateId": "CANARY_REQUIRED_EVIDENCE", "status": "FAIL" if missing else "PASS", "observed": len(REQUIRED_ARTIFACTS) - len(missing), "expected": len(REQUIRED_ARTIFACTS), "evidence": ";".join(missing) or "CHECKSUMS.sha256"},
        {**common, "gateId": "CANARY_POLICY", "status": "FAIL" if policy_errors else ("NOT_EVALUATED" if missing else "PASS"), "observed": len(policy_errors), "expected": 0, "evidence": ";".join(policy_errors) or "approval_binding.json"},
        {**common, "gateId": "CANARY_REQUEST_RAW_CHECKPOINT", "status": "NOT_EVALUATED" if missing else ("FAIL" if errors else "PASS"), "observed": len(errors), "expected": 0, "evidence": ";".join(errors) or "portable manifests"},
        {**common, "gateId": "CANARY_OBSERVED_PRODUCTION_ISOLATION", "status": "NOT_EVALUATED" if missing else ("FAIL" if contamination_hits else "PASS"), "observed": ";".join(contamination_hits) if contamination_hits else 0, "expected": "canonical/observed/mart/gold/article rows = 0", "evidence": "pipeline and NCS authority-store scan"},
        {**common, "gateId": "CANARY_PIPELINE_NCS_COMPATIBILITY", "status": "NOT_EVALUATED" if missing else ("FAIL" if any(e.startswith("CANARY_PARQUET") for e in errors) else "PASS"), "observed": json.dumps(component_counts, sort_keys=True), "expected": "run/data/status-bound debug-only rows", "evidence": "index/detail/asset Parquet schema"},
        {**common, "gateId": "A5_INDEPENDENT_AUDIT", "status": args.a5_status, "observed": args.a5_commit, "expected": "NOT_REQUIRED for Tier 0 fixture-only; otherwise PASS or PASS_WITH_FINDINGS", "evidence": "tier policy / independent audit branch"},
        {**common, "gateId": "M2_CRAWL_READY_FOR_USER_APPROVAL", "status": "BLOCKED", "observed": "not promoted", "expected": "separate gate", "evidence": status},
        {**common, "gateId": "CRAWL_RELEASE_READY", "status": "BLOCKED", "observed": "not promoted", "expected": "production release evidence", "evidence": status},
        {**common, "gateId": "ANALYSIS_READY", "status": "BLOCKED", "observed": "not promoted", "expected": "analysis gate", "evidence": status},
    ]
    gate_path = report / f"P4_CANARY_GATE_STATUS_{run_id}.csv"
    write_csv(gate_path, list(gate_rows[0]), gate_rows)

    defect_rows: list[dict[str, Any]] = []
    if missing:
        defect_rows.append({
            **common, "defectId": "CANARY-P1-EVIDENCE-BUNDLE", "taxonomy": "LINEAGE",
            "severity": "P1", "description": f"canonical canary handoff incomplete: {len(missing)}/{len(REQUIRED_ARTIFACTS)} missing; " + ";".join(missing), "status": "OPEN",
        })
    for index, value in enumerate((error for error in errors if not error.startswith("REQUIRED_ARTIFACT_MISSING:")), 1):
        defect_rows.append({
            **common, "defectId": f"CANARY-P2-VALIDATION-{index:03d}", "taxonomy": "VALIDATOR",
            "severity": "P2", "description": value, "status": "OPEN",
        })
    for index, value in enumerate(policy_errors, 1):
        defect_rows.append({
            **common, "defectId": f"CANARY-POLICY-{index:03d}", "taxonomy": "APPROVAL_BINDING",
            "severity": "POLICY", "description": value, "status": "BLOCKED_EXPECTED",
        })
    defect_path = report / f"P4_CANARY_DEFECT_TAXONOMY_{run_id}.csv"
    write_csv(defect_path, list(defect_rows[0]) if defect_rows else [*common, "defectId", "taxonomy", "severity", "description", "status"], defect_rows)

    request_audit = [{**common, "checkId": "REQUEST_LEDGER", "rows": len(request_rows), "conflicts": conflict_count, "emptyReason": request_envelope.get("emptyReason") if request_envelope else "", "status": "NOT_EVALUATED" if missing or request_envelope else ("FAIL" if any(e.startswith("REQUEST") or e.startswith("TERMINAL") for e in errors) else "PASS")}]
    raw_audit = [{**common, "checkId": "RAW_AUTHORITY", **raw_stats, "emptyReason": raw_envelope.get("emptyReason") if not missing and raw_envelope else "", "status": "NOT_EVALUATED" if missing or (not missing and raw_envelope) else ("FAIL" if any(e.startswith("RAW") for e in errors) else "PASS")}]
    coverage_audit = []
    for layer in ("MONTH", "PAGE", "POSTING", "ASSET"):
        source = coverage_by_layer.get(layer, {}) if not missing else {}
        coverage_audit.append({
            **common, "coverageLayer": layer, "plannedCount": source.get("plannedCount", 0),
            "terminalCount": source.get("terminalCount", 0), "coverage": source.get("coverage", "NOT_EVALUATED"),
            "status": "NOT_EVALUATED" if missing or source.get("coverage") == "NOT_EVALUATED" else ("FAIL" if any(error.endswith(f":{layer}") for error in errors) else "PASS"),
        })
    write_csv(report / f"P4_CANARY_REQUEST_AUDIT_{run_id}.csv", list(request_audit[0]), request_audit)
    write_csv(report / f"P4_CANARY_RAW_AUDIT_{run_id}.csv", list(raw_audit[0]), raw_audit)
    write_csv(report / f"P4_CANARY_COVERAGE_AUDIT_{run_id}.csv", list(coverage_audit[0]), coverage_audit)
    test_rows = [{
        **common, "testSuite": "CANARY_INTEGRATION_VALIDATOR", "testCommand": args.test_command,
        "testExitCode": args.test_exit_code, "passed": args.test_pass_count,
        "failed": 0 if args.test_exit_code == 0 else "UNKNOWN",
        "status": "PASS" if args.test_exit_code == 0 else "FAIL",
    }]
    write_csv(report / f"P4_CANARY_TEST_SUMMARY_{run_id}.csv", list(test_rows[0]), test_rows)

    decision = {
        "agentId": "P4-A3-GLOBAL-CANARY-INTEGRATION-ORCHESTRATOR",
        "canaryRunId": run_id, "dataVersion": data_version, "approvalId": approval_id,
        "status": status,
        "acceptedScope": "TIER0_FIXTURE_ONLY" if status == "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE" else "NONE",
        "approvedNextScope": "NONE",
        "requestCount": len(request_rows), "requestResponseConflictCount": conflict_count,
        "productionReleaseAllowed": False, "analysisPromotionAllowed": False,
        "externalAtsTransportAllowed": False, "productionNetworkCalls": network_calls,
        "externalAtsTransportCalls": 0, "credentialedApiCalls": 0,
        "a5AuditCommit": args.a5_commit, "a5AuditStatus": args.a5_status,
        "a1CandidateBranch": args.a1_branch, "a1CandidateCommit": args.a1_commit,
        "a1CandidateDirtyPathCount": args.a1_dirty_path_count,
        "canonicalHandoffStatus": "PASS" if not missing and not errors else "FAIL",
        "canonicalHandoffArtifactCount": len(REQUIRED_ARTIFACTS) - len(missing),
        "canonicalHandoffManifestSha256": common["manifestSha256"],
        "legacyTier0EvidenceStatus": "PASS" if legacy and not legacy_errors else "NOT_EVALUATED" if not legacy else "FAIL",
        "legacyTier0EvidenceManifestSha256": legacy.get("evidenceManifestSha256"),
        "legacyTier0Checks": legacy.get("tier0Checks", 0),
        "legacyTier0ChecksPassed": legacy.get("tier0ChecksPassed", 0),
        "a1HeadCommitAtRun": plan.get("sourceCommitAtRun") or legacy.get("headCommitAtRun"),
        "missingArtifacts": missing, "errors": errors, "policyErrors": policy_errors,
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
    }
    decision_path = report / f"P4_CANARY_SCOPE_ESCALATION_DECISION_{run_id}.json"
    decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = report / f"P4_CANARY_ACCEPTANCE_{run_id}.md"
    report_path.write_text(
        "# P4 Canary Acceptance\n\n"
        f"- Verdict: `{status}`\n- Integration branch: `{branch}`\n- Head before report commit: `{head}`\n"
        f"- Canary run: `{run_id}`\n- Approval: `{approval_id}`\n- Network calls evidenced: `{network_calls}`\n"
        f"- Required artifacts present: `{len(REQUIRED_ARTIFACTS) - len(missing)}/{len(REQUIRED_ARTIFACTS)}`\n"
        f"- A5 audit: `{args.a5_status}` at `{args.a5_commit}`\n\n"
        f"- A1 candidate: `{args.a1_branch}` at `{args.a1_commit}`; dirty paths `{args.a1_dirty_path_count}`\n\n"
        f"- Canonical handoff: `{'PASS' if not missing and not errors else 'FAIL'}`; "
        f"artifacts `{len(REQUIRED_ARTIFACTS) - len(missing)}/{len(REQUIRED_ARTIFACTS)}`\n\n"
        "## Decision\n\nTier 0 fixture-only evidence may be accepted with zero network calls and no network approval. "
        "Every networked tier and every scope expansion still requires a separate valid approval artifact. "
        "No production release, canonical database, RQ mart, Gold/reference, or article promotion is permitted.\n\n"
        "`CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE` is not equivalent to any M2, crawl-release, production-data, or analysis gate.\n",
        encoding="utf-8",
    )

    manifest_path = report / f"EVIDENCE_MANIFEST_{run_id}.sha256"
    evidence_files = sorted(path for path in report.iterdir() if path.is_file() and path != manifest_path)
    manifest_path.write_text("".join(f"{file_sha256(path)}  {path.name}\n" for path in evidence_files), encoding="utf-8")
    print(json.dumps({"status": status, "runId": run_id, "missingArtifacts": len(missing), "report": report_path.name}, sort_keys=True))
    return 0 if status == "CANARY_ACCEPTED_FOR_NEXT_DEBUG_SCOPE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
