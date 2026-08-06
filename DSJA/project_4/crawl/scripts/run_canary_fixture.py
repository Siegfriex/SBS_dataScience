#!/usr/bin/env python3
"""Execute Tier 0 canary regression and publish a redacted debug packet.

No network transport is imported or called.  Without a valid canary approval
the resulting state is necessarily ``CANARY_BLOCKED_BY_POLICY``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from p4_crawl.canary import (
    CanaryKillSwitch,
    CanaryKillSwitchTripped,
    CanaryStateMachine,
    CanaryStatus,
    RequestLedger,
    checkpoint_envelope,
    request_key,
    validate_canary_approval,
    validate_checkpoint,
)
from p4_crawl.detail import select_activity_text
from p4_crawl.raw_authority import (
    AVAILABLE,
    COMPRESSED_SHA_MISMATCH,
    RAW_ROOT_UNMOUNTED,
    audit_raw_posting_binding,
    build_raw_object_manifest,
    validate_manifest_against_mount,
)
from p4_crawl.storage import canonical_json


AGENT_ID = "P4-A1-CANARY-CRAWL-ORCHESTRATOR"
DEFECT_FAMILY = "POLICY_PORTABILITY_BASELINE"
FIXED_DEFECTS = "CANARY-P1-ABSOLUTE-RAW-ROOT"
RATE_POLICY = "p4-linkareer-production-rate-v1"
KILL_POLICY = "p4-linkareer-kill-switch-v1"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def git(project: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=project, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"empty CSV evidence: {path}")
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def expect_kill(case_id: str, callback) -> dict[str, Any]:
    try:
        callback()
    except CanaryKillSwitchTripped as exc:
        return {"checkId": case_id, "status": "PASS", "observed": str(exc)}
    return {"checkId": case_id, "status": "FAIL", "observed": "kill switch did not trip"}


def tracked_scan(project: Path) -> tuple[int, int]:
    tracked = git(project, "ls-files", "crawl").splitlines()
    secret_pattern = re.compile(
        rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s+(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]+|serviceKey\s*=\s*['\"][^'\"]+|api[_-]?key\s*=\s*['\"][^'\"]+",
        re.I,
    )
    home_prefix = b"/" + b"home/"
    legacy_mount_token = b"p4-" + b"agent1"
    raw_path_pattern = re.compile(
        re.escape(home_prefix)
        + rb"[^\s,'\"]+/(?:data/raw|[^\s,'\"]*"
        + re.escape(legacy_mount_token)
        + rb"[^\s,'\"]*)"
    )
    secret_count = 0
    absolute_raw_count = 0
    for relative in tracked:
        path = project / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        secret_count += bool(secret_pattern.search(content))
        absolute_raw_count += bool(raw_path_pattern.search(content))
    return int(secret_count), int(absolute_raw_count)


def tier0(project: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "ambiguousFallbackAutoSelected": 0,
        "duplicateRequestCount": 0,
        "requestResponseConflictCount": 0,
        "quarantinedRows": 0,
        "fixtureDuplicateRequestCount": 0,
        "fixtureRequestResponseConflictCount": 0,
    }
    with tempfile.TemporaryDirectory(prefix="p4-canary-tier0-") as temporary:
        root = Path(temporary)
        content = b"<html><body>canary fixture</body></html>"
        locator = "objects/detail-42.html.gz"
        object_path = root / locator
        object_path.parent.mkdir(parents=True)
        object_path.write_bytes(gzip.compress(content, mtime=0))
        source = [{
            "sourcePostingId": "42",
            "rawPath": locator,
            "rawSha256": sha_bytes(content),
            "bytes": len(content),
            "fetchedAt": "2026-08-07T00:00:00Z",
            "sourceUrl": "https://linkareer.com/activity/42",
        }]
        manifest, audit = build_raw_object_manifest(
            source, root,
            storage_root_id="P4_CANARY_FIXTURE_T0",
            mount_policy_version="p4-raw-mount-v1",
        )
        checks.append({
            "checkId": "RAW_MOUNT",
            "status": "PASS" if audit[0]["availabilityStatus"] == AVAILABLE else "FAIL",
            "observed": audit[0]["availabilityStatus"],
        })
        unmounted = validate_manifest_against_mount(manifest, root / "unmounted")
        checks.append({
            "checkId": "RAW_UNMOUNTED",
            "status": "PASS" if unmounted[0]["availabilityStatus"] == RAW_ROOT_UNMOUNTED else "FAIL",
            "observed": unmounted[0]["availabilityStatus"],
        })
        tampered = [dict(row) for row in manifest]
        tampered[0]["compressedSha256"] = "0" * 64
        wrong = validate_manifest_against_mount(tampered, root)
        checks.append({
            "checkId": "RAW_WRONG_SHA",
            "status": "PASS" if wrong[0]["availabilityStatus"] == COMPRESSED_SHA_MISMATCH and wrong[0]["bindingStatus"] == "QUARANTINED" else "FAIL",
            "observed": f"{wrong[0]['availabilityStatus']}/{wrong[0]['bindingStatus']}",
        })
        posting = pd.DataFrame([{"sourcePostingId": "42", "hasDetailRawHtml": True}])
        binding = audit_raw_posting_binding(manifest, source, posting)
        checks.append({
            "checkId": "RAW_POSTING_BINDING",
            "status": "PASS" if binding[0]["bindingStatus"] == "MATCHED" else "FAIL",
            "observed": binding[0]["bindingStatus"],
        })

    pagination = CanaryKillSwitch()
    pagination.page(cursor="cursor-1", empty=False)
    pagination.page(cursor="cursor-2", empty=False, exhausted=True)
    checks.append({"checkId": "PAGINATION_TERMINATION", "status": "PASS", "observed": "unique cursors; exhausted=true"})
    checks.append(expect_kill("CURSOR_LOOP", lambda: (lambda monitor: (monitor.page(cursor="same", empty=False), monitor.page(cursor="same", empty=False)))(CanaryKillSwitch())))
    first = checkpoint_envelope({"page": 1})
    broken = json.loads(json.dumps(first))
    broken["state"]["page"] = 2
    checks.append(expect_kill("CHECKPOINT_CORRUPTION", lambda: validate_checkpoint(broken)))
    checks.append(expect_kill("HTTP_403", lambda: CanaryKillSwitch().response(403)))

    def trip_429() -> None:
        monitor = CanaryKillSwitch(minimum_success_samples=20)
        monitor.response(429)
        monitor.response(429)
        monitor.response(429)

    checks.append(expect_kill("HTTP_429", trip_429))
    checks.append(expect_kill("CONTENT_TYPE_DRIFT", lambda: CanaryKillSwitch().response(200, "text/html")))
    checks.append(expect_kill("SCHEMA_DRIFT", lambda: CanaryKillSwitch().schema_drift("missing nodes")))
    selected, evidence = select_activity_text(
        {"ActivityText:a": {"text": "a"}, "ActivityText:b": {"text": "b"}}, {}, "42"
    )
    ambiguous_ok = selected is None and evidence["fallbackStatus"] == "AMBIGUOUS_STANDALONE"
    checks.append({
        "checkId": "ACTIVITY_TEXT_AMBIGUITY",
        "status": "PASS" if ambiguous_ok else "FAIL",
        "observed": f"selected={selected is not None}; status={evidence['fallbackStatus']}",
    })
    metrics["ambiguousFallbackAutoSelected"] = int(selected is not None)
    ledger = RequestLedger()
    key = request_key("fixture", {"page": 1}, period_month="2026-07")
    ledger.record_terminal(key, "a" * 64, "FETCHED_VALID")
    duplicate = ledger.record_terminal(key, "a" * 64, "FETCHED_VALID")
    conflict_quarantined = False
    try:
        ledger.record_terminal(key, "b" * 64, "FETCHED_VALID")
    except Exception as exc:
        conflict_quarantined = "REQUEST_RESPONSE_CONFLICT" in str(exc)
    checks.append({
        "checkId": "REQUEST_IDEMPOTENCY",
        "status": "PASS" if duplicate == "DUPLICATE_NO_RESTORE" and conflict_quarantined else "FAIL",
        "observed": f"duplicate={duplicate}; conflictQuarantined={conflict_quarantined}",
    })
    metrics["fixtureDuplicateRequestCount"] = ledger.duplicate_count
    metrics["fixtureRequestResponseConflictCount"] = ledger.conflict_count
    secret_count, absolute_raw_count = tracked_scan(project)
    checks.append({"checkId": "SECRET_COOKIE_SCAN", "status": "PASS" if secret_count == 0 else "FAIL", "observed": secret_count})
    checks.append({"checkId": "ABSOLUTE_RAW_PATH_SCAN", "status": "PASS" if absolute_raw_count == 0 else "FAIL", "observed": absolute_raw_count})
    metrics.update({"trackedSecretFindings": secret_count, "trackedAbsoluteRawPathFindings": absolute_raw_count})
    return checks, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canary-run-id", required=True)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    crawl = project / "crawl"
    run_root = crawl / "runs/canary" / args.canary_run_id
    report_root = crawl / "reports/canary_debug"
    if run_root.exists():
        raise RuntimeError(f"canary run is immutable and already exists: {run_root}")
    run_root.mkdir(parents=True)
    report_root.mkdir(parents=True, exist_ok=True)
    branch = git(project, "branch", "--show-current")
    head = git(project, "rev-parse", "HEAD")
    generated = utc_now()
    query_path = crawl / "configs/queryRegistry.yaml"
    query_sha = sha(query_path)
    policy_path = crawl / "reports/m2_production_crawl/P4_M2_CRAWL_SOURCE_POLICY_AUDIT.md"
    if policy_path.is_file():
        policy_sha = sha(policy_path)
    else:
        reconciliation_preflight = crawl / "reports/reconciliation_a1/A1_M2_PREFLIGHT_REBIND_MANIFEST.json"
        policy_sha = str(json.loads(reconciliation_preflight.read_text()).get("sourcePolicyAuditSha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", policy_sha):
        raise RuntimeError("source-policy audit SHA authority is unavailable")
    approval_payload = json.loads(args.approval.read_text()) if args.approval and args.approval.is_file() else None
    approval_errors = validate_canary_approval(
        approval_payload,
        query_registry_sha256=query_sha,
        source_policy_audit_sha256=policy_sha,
    )
    approval_id = str((approval_payload or {}).get("canaryApprovalId") or "NONE")
    approval_sha = sha(args.approval) if args.approval and args.approval.is_file() else ""
    machine = CanaryStateMachine()
    checks, tier0_metrics = tier0(project)
    machine.transition(CanaryStatus.FIXTURE_REGRESSION)
    tier0_pass = all(row["status"] == "PASS" for row in checks)
    machine.transition(CanaryStatus.DEBUG_REPORT)
    if approval_errors or not tier0_pass:
        if "expiresAtUtc:expired" in approval_errors:
            machine.transition(CanaryStatus.STOPPED_KILL_SWITCH)
        else:
            machine.transition(CanaryStatus.BLOCKED_POLICY if approval_errors else CanaryStatus.FAILED)
    else:
        machine.transition(CanaryStatus.READY)
    status = str(machine.state)
    network_calls = 0
    external_ats_calls = 0
    plan = {
        "agentId": AGENT_ID,
        "branch": branch,
        "headCommitAtRun": head,
        "canaryRunId": args.canary_run_id,
        "runMode": "fixture-only",
        "defectFamily": DEFECT_FAMILY,
        "approvalRequiredForNetwork": True,
        "approvalId": approval_id,
        "approvedCanaryScope": (approval_payload or {}).get("approvedCanaryScope"),
        "approvedRequestBudget": int((approval_payload or {}).get("approvedMaxRequests", 0)),
        "networkTransportEnabled": False,
        "productionPromotionAllowed": False,
    }
    write_json(run_root / "canary_plan.json", plan)
    write_json(run_root / "approval_binding.json", {
        "canaryRunId": args.canary_run_id,
        "approvalId": approval_id,
        "approvalSha256": approval_sha,
        "queryRegistrySha256": query_sha,
        "sourcePolicyAuditSha256": policy_sha,
        "validationErrors": approval_errors,
        "status": "PASS" if not approval_errors else "CANARY_BLOCKED_BY_POLICY",
    })
    for name in ("request_attempt.jsonl", "request_response_manifest.jsonl", "raw_object_manifest.jsonl", "kill_switch_events.jsonl", "quarantine_manifest.jsonl"):
        write_jsonl(run_root / name, [])
    checkpoint = checkpoint_envelope({
        "canaryRunId": args.canary_run_id,
        "state": status,
        "networkCalls": 0,
        "fixtureChecksPassed": sum(row["status"] == "PASS" for row in checks),
    })
    write_json(run_root / "checkpoint_manifest.json", checkpoint)
    empty_frames = {
        "index_results.parquet": ["requestKey", "periodMonth", "terminalStatus"],
        "detail_results.parquet": ["requestKey", "postingId", "terminalStatus"],
        "asset_results.parquet": ["requestKey", "assetId", "terminalStatus"],
    }
    for name, columns in empty_frames.items():
        pd.DataFrame(columns=columns).to_parquet(run_root / name, index=False)
    write_csv(run_root / "canary_coverage.csv", [{
        "canaryRunId": args.canary_run_id,
        "tier": 0,
        "fixtureChecks": len(checks),
        "fixtureChecksPassed": sum(row["status"] == "PASS" for row in checks),
        "networkCalls": 0,
        "status": status,
    }])
    metrics = {
        "canaryRunId": args.canary_run_id,
        "approvedRequestBudget": int((approval_payload or {}).get("approvedMaxRequests", 0)),
        "actualRequestCount": 0,
        "indexTerminalCoverage": "NOT_EVALUATED",
        "detailTerminalCoverage": "NOT_EVALUATED",
        "assetTerminalCoverage": "NOT_EVALUATED",
        "rawShaCompleteness": "NOT_EVALUATED",
        "assetShaCompleteness": "NOT_EVALUATED",
        **tier0_metrics,
        "externalAtsTransportCalls": external_ats_calls,
        "killSwitchEvents": 0,
        "networkCalls": network_calls,
        "fixtureChecks": len(checks),
        "fixtureChecksPassed": sum(row["status"] == "PASS" for row in checks),
        "status": status,
    }
    write_json(run_root / "stage_metrics.json", metrics)
    write_csv(run_root / "stage_quality.csv", checks)
    write_json(run_root / "stage_manifest.json", {
        "agentId": AGENT_ID,
        "canaryRunId": args.canary_run_id,
        "stateHistory": [str(value) for value in machine.history],
        "status": status,
        "runMode": "fixture-only",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "createdAtUtc": generated,
    })
    checksum_files = sorted(path for path in run_root.iterdir() if path.is_file() and path.name != "CHECKSUMS.sha256")
    (run_root / "CHECKSUMS.sha256").write_text(
        "\n".join(f"{sha(path)}  {path.name}" for path in checksum_files) + "\n", encoding="utf-8"
    )

    suffix = args.canary_run_id
    metrics_path = report_root / f"P4_CANARY_CRAWL_METRICS_{suffix}.csv"
    defects_path = report_root / f"P4_CANARY_CRAWL_DEFECTS_{suffix}.csv"
    lineage_path = report_root / f"P4_CANARY_CRAWL_LINEAGE_{suffix}.csv"
    policy_report = report_root / f"P4_CANARY_CRAWL_POLICY_{suffix}.json"
    report_path = report_root / f"P4_CANARY_CRAWL_REPORT_{suffix}.md"
    evidence_path = report_root / f"EVIDENCE_MANIFEST_{suffix}.sha256"
    write_csv(metrics_path, [metrics])
    write_csv(defects_path, [
        {"defectId": FIXED_DEFECTS, "priority": "P1", "status": "FIXED", "defectFamily": DEFECT_FAMILY, "description": "Removed committed absolute raw mount fallback from tests."},
        {"defectId": "CANARY-POLICY-APPROVAL", "priority": "POLICY", "status": "BLOCKED_EXPECTED" if approval_errors else "PASS", "defectFamily": DEFECT_FAMILY, "description": ";".join(approval_errors) if approval_errors else "approval valid"},
    ])
    run_artifacts = sorted(path for path in run_root.iterdir() if path.is_file())
    write_csv(lineage_path, ({
        "canaryRunId": args.canary_run_id,
        "artifactPath": path.relative_to(project).as_posix(),
        "artifactRole": "LOCAL_CANARY_RUNTIME_REDACTED",
        "bytes": path.stat().st_size,
        "sha256": sha(path),
        "gitTracked": False,
        "containsRawBytes": False,
    } for path in run_artifacts))
    write_json(policy_report, {
        "agentId": AGENT_ID,
        "canaryRunId": args.canary_run_id,
        "approvalId": approval_id,
        "approvalErrors": approval_errors,
        "queryRegistrySha256": query_sha,
        "sourcePolicyAuditSha256": policy_sha,
        "rateLimitPolicyVersion": RATE_POLICY,
        "killSwitchPolicyVersion": KILL_POLICY,
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "status": status,
    })
    report_path.write_text(f"""# P4 Canary Crawl Debug Report — {suffix}

## Verdict

`{status}`

- agentId: `{AGENT_ID}`
- branch: `{branch}`
- headCommitAtRun: `{head}`
- canaryRunId: `{suffix}`
- approvalId: `{approval_id}`
- runMode: `fixture-only`
- defectFamily: `{DEFECT_FAMILY}`
- Tier 0: `{sum(row['status'] == 'PASS' for row in checks)}/{len(checks)} PASS`
- networkCalls: `0`
- externalAtsTransportCalls: `0`

No Linkareer, external ATS, browser, or credentialed transport was opened. The
absence or invalidity of a canary approval blocks Tier 1 before transport. Runtime
artifacts contain only fixture-derived or empty redacted tables; raw bytes are not
Git authority and no canonical production root was written.

## Next scope

Provide a new, unexpired approval matching `CANARY_APPROVAL.schema.json`, with a
small period/query/request budget and hashes bound to the current query registry
and source-policy audit. A new canaryRunId is required.
""", encoding="utf-8")
    evidence_files = [metrics_path, defects_path, lineage_path, policy_report, report_path]
    evidence_path.write_text(
        "\n".join(f"{sha(path)}  {path.name}" for path in evidence_files) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "canaryRunId": args.canary_run_id,
        "approvalId": approval_id,
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "status": status,
        "fixtureChecksPassed": sum(row["status"] == "PASS" for row in checks),
        "fixtureChecks": len(checks),
        "reportPath": report_path.relative_to(project).as_posix(),
    }, indent=2))
    return 0 if tier0_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
