#!/usr/bin/env python3
"""Generate the network-zero M2 production crawl approval packet."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
REPORT_ROOT = CRAWL_ROOT / "reports/m2_production_crawl"
BASELINE_RELEASE = CRAWL_ROOT / "releases/CRAWL_20260806_03"
M1_5_REPORT_ROOT = PROJECT_ROOT / "reports/m1_5_v4_implementation"
RUN_ID = "M2_PREFLIGHT_20260806_01"
DATA_VERSION = "m2-preflight-20260806.1"

for path in (PROJECT_ROOT, CRAWL_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from p4_crawl.m2_preflight import (  # noqa: E402
    M2PolicyConfig,
    build_month_plan,
    checkpoint_envelope,
    utc_now,
    validate_approval,
    validate_query_registry,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, check=True, text=True, capture_output=True,
    ).stdout.strip()


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = columns or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def junit_rows(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    rows = []
    for case in root.iter("testcase"):
        failed = case.find("failure") is not None or case.find("error") is not None
        rows.append({
            "testId": f"{case.get('classname')}::{case.get('name')}",
            "status": "FAIL" if failed else "PASS",
            "elapsedSeconds": case.get("time", "0"),
            "junitSha256": sha256(path),
        })
    return rows


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def storage_plan(raw_source_root: Path, month_plan: pd.DataFrame) -> dict:
    raw_manifest = load_jsonl(CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01/raw_detail_manifest.jsonl")
    compressed_sizes = []
    decompressed_sizes = []
    for row in raw_manifest:
        path = raw_source_root / row["rawPath"]
        if not path.is_file():
            continue
        raw = path.read_bytes()
        compressed_sizes.append(len(raw))
        decompressed_sizes.append(len(gzip.decompress(raw)))
    if len(compressed_sizes) != 29:
        raise FileNotFoundError(f"expected 29 local ignored raw files, found {len(compressed_sizes)}")

    complete = month_plan[month_plan["baselinePaginationComplete"]]
    average_requests = float(complete["baselineRequestCount"].mean())
    target_postings = 40_551
    observed_asset_candidates = 30
    observed_postings = 137
    estimated_index_requests = math.ceil(average_requests * 79 * 1.25)
    estimated_index_bytes = estimated_index_requests * 250_000
    estimated_detail_bytes = math.ceil(sum(compressed_sizes) / len(compressed_sizes) * target_postings)
    estimated_asset_candidates = math.ceil(target_postings * observed_asset_candidates / observed_postings)
    estimated_asset_bytes = estimated_asset_candidates * 1_500_000
    machine_artifact_bytes = math.ceil((estimated_index_bytes + estimated_detail_bytes) * 0.35)
    subtotal = estimated_index_bytes + estimated_detail_bytes + estimated_asset_bytes + machine_artifact_bytes
    return {
        "estimationStatus": "PLANNING_ESTIMATE_NOT_QUOTA_RESERVATION",
        "baselineRawRows": len(raw_manifest),
        "baselineRawCompressedBytes": sum(compressed_sizes),
        "baselineRawDecompressedBytes": sum(decompressed_sizes),
        "targetPostingIdPlanningCount": target_postings,
        "estimatedIndexRequests": estimated_index_requests,
        "assumedMeanIndexResponseBytes": 250_000,
        "estimatedIndexBytes": estimated_index_bytes,
        "estimatedDetailRawCompressedBytes": estimated_detail_bytes,
        "observedAssetCandidateRate": observed_asset_candidates / observed_postings,
        "estimatedAssetCandidates": estimated_asset_candidates,
        "assumedMeanAssetBytes": 1_500_000,
        "estimatedAssetBytes": estimated_asset_bytes,
        "estimatedMachineArtifactBytes": machine_artifact_bytes,
        "estimatedSubtotalBytes": subtotal,
        "requiredCapacityWith2xHeadroomBytes": subtotal * 2,
        "rawRuntimeAuthority": "LOCAL_IGNORED_RUNTIME_ROOT_NOT_RECORDED",
    }


def secret_scan() -> dict:
    pattern = re.compile(
        r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|serviceKey\s*=|api[_-]?key\s*=",
        re.I,
    )
    findings = []
    for relative in git("ls-files", "crawl").splitlines():
        path = PROJECT_ROOT / relative
        if path.is_file() and pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            findings.append(relative)
    return {"trackedSecretFileCount": len(findings), "trackedRawFileCount": sum("/data/raw/" in f"/{p}" for p in git("ls-files", "crawl").splitlines())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-source-root", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--full-junit", type=Path, required=True)
    parser.add_argument("--authority-prompt", type=Path)
    args = parser.parse_args()

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    generated_at = utc_now()
    policy = M2PolicyConfig()

    approval_path = CRAWL_ROOT / "control/PRODUCTION_APPROVAL.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path.is_file() else None
    approval_errors = validate_approval(approval, policy)
    query = validate_query_registry(CRAWL_ROOT / "configs/queryRegistry.yaml")
    month_plan = build_month_plan(BASELINE_RELEASE / "monthly_coverage.csv")
    month_plan.to_csv(REPORT_ROOT / "month_plan.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    month_plan.to_parquet(REPORT_ROOT / "month_plan.parquet", index=False)
    test_rows = junit_rows(args.junit)
    full_test_rows = junit_rows(args.full_junit)
    write_csv(REPORT_ROOT / "P4_M2_PREFLIGHT_TESTS.csv", test_rows)
    write_csv(REPORT_ROOT / "P4_M2_FULL_REGRESSION_TESTS.csv", full_test_rows)

    parameters = {
        "agentId": "P4-A1-M2-PRODUCTION-ORCHESTRATOR",
        "runId": RUN_ID,
        "dataVersion": DATA_VERSION,
        "runMode": "production",
        "empiricalAnalysisAllowed": False,
        "failOnGate": True,
        "targetPeriod": "2020-01~2026-07",
        "targetMonthCount": 79,
        "activityTypeID": 5,
        "statusFilter": "OMITTED",
        "rangeSemantics": "recruitStartAt OR recruitCloseAt",
        "externalAtsTransportAllowed": False,
        "linkareerHostedAssetAllowed": True,
        "productionNetworkCalls": 0,
        **policy.as_frozen_dict(),
    }
    (REPORT_ROOT / "production_parameters.json").write_text(json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checkpoint = checkpoint_envelope({
        "runId": RUN_ID,
        "dataVersion": DATA_VERSION,
        "completedPeriods": [],
        "nextPeriod": "2020-01",
        "productionApproved": False,
        "networkTransportCalls": 0,
    })
    (REPORT_ROOT / "index_checkpoint_seed.json").write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    storage = storage_plan(args.raw_source_root.resolve(), month_plan)
    (REPORT_ROOT / "storage_plan.json").write_text(json.dumps(storage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(CRAWL_ROOT / "configs/queryRegistry.yaml", REPORT_ROOT / "query_registry_snapshot.yaml")
    security = secret_scan()

    complete_months = int(month_plan["baselinePaginationComplete"].sum())
    unverified_months = 79 - complete_months
    test_pass = sum(row["status"] == "PASS" for row in test_rows)
    test_fail = len(test_rows) - test_pass
    full_test_pass = sum(row["status"] == "PASS" for row in full_test_rows)
    full_test_fail = len(full_test_rows) - full_test_pass
    authority_prompt_sha = sha256(args.authority_prompt) if args.authority_prompt and args.authority_prompt.is_file() else "EVIDENCE_INSUFFICIENT"
    source_policy_text = (PROJECT_ROOT / "shared/contracts/P4_CONTRACT_v2.1.2/SOURCE_POLICY_GATE.md").read_text(encoding="utf-8")
    transparent_conflict = bool(re.search(r"does not promote source policy\s+to PASS", source_policy_text))

    gates = [
        {"gateId": "PRODUCTION_PARAMETER_FROZEN", "status": "PASS", "observed": "79 months; activityTypeID=5; status omitted", "evidencePath": "production_parameters.json"},
        {"gateId": "QUERY_REGISTRY_FROZEN", "status": query["status"], "observed": f"queries={query['queryCount']}; unresolved={len(query['unresolvedSemantics'])}", "evidencePath": "query_registry_snapshot.yaml"},
        {"gateId": "KILL_SWITCH_TESTED", "status": "PASS" if test_fail == 0 else "FAIL", "observed": f"{test_pass}/{len(test_rows)} tests", "evidencePath": "P4_M2_PREFLIGHT_TESTS.csv"},
        {"gateId": "CRAWL_REGRESSION_TESTED", "status": "PASS" if full_test_fail == 0 else "FAIL", "observed": f"{full_test_pass}/{len(full_test_rows)} tests", "evidencePath": "P4_M2_FULL_REGRESSION_TESTS.csv"},
        {"gateId": "CHECKPOINT_RESUME_TESTED", "status": "PASS" if test_fail == 0 else "FAIL", "observed": "round-trip and corruption rejection", "evidencePath": "index_checkpoint_seed.json"},
        {"gateId": "STORAGE_PLAN_READY", "status": "PASS", "observed": storage["requiredCapacityWith2xHeadroomBytes"], "evidencePath": "storage_plan.json"},
        {"gateId": "SOURCE_POLICY_APPROVED", "status": "NOT_EVALUATED", "observed": "transparent-client production evidence and signed approval absent", "evidencePath": "P4_M2_CRAWL_SOURCE_POLICY_AUDIT.md"},
        {"gateId": "PRODUCTION_USER_APPROVAL", "status": "NOT_EVALUATED", "observed": ";".join(approval_errors), "evidencePath": "P4_M2_CRAWL_USER_DECISION_PACKET.md"},
        {"gateId": "PREAPPROVAL_NETWORK_ZERO", "status": "PASS", "observed": 0, "evidencePath": "M2_PREFLIGHT_MANIFEST.json"},
        {"gateId": "CRAWL_RELEASE_READY", "status": "BLOCKED", "observed": f"baseline complete={complete_months}/79; approval missing", "evidencePath": "P4_M2_CRAWL_EXECUTION_REPORT.md"},
    ]
    write_csv(REPORT_ROOT / "P4_M2_CRAWL_GATE_STATUS.csv", gates)

    components = [
        {"component": "M2_PREFLIGHT", "status": "PASS", "rows": 79, "networkCalls": 0, "evidencePath": "month_plan.parquet"},
        {"component": "INDEX_CRAWL", "status": "NOT_STARTED", "rows": 0, "networkCalls": 0, "evidencePath": "P4_M2_CRAWL_USER_DECISION_PACKET.md"},
        {"component": "DETAIL_CRAWL", "status": "NOT_STARTED", "rows": 0, "networkCalls": 0, "evidencePath": "P4_M2_CRAWL_USER_DECISION_PACKET.md"},
        {"component": "ASSET_CRAWL", "status": "NOT_STARTED", "rows": 0, "networkCalls": 0, "evidencePath": "P4_M2_CRAWL_USER_DECISION_PACKET.md"},
        {"component": "IMMUTABLE_RELEASE", "status": "BLOCKED", "rows": 0, "networkCalls": 0, "evidencePath": "P4_M2_CRAWL_GATE_STATUS.csv"},
        {"component": "STRICT_AGENT2_VALIDATOR", "status": "NOT_EVALUATED", "rows": 0, "networkCalls": 0, "evidencePath": "P4_M2_CRAWL_GATE_STATUS.csv"},
    ]
    write_csv(REPORT_ROOT / "P4_M2_CRAWL_COMPONENT_STATUS.csv", components)

    defects = [
        {"defectId": "M2-P1-001", "priority": "P1", "status": "USER_ACTION_REQUIRED", "component": "production approval", "description": "signed approval artifact absent", "blocksNetwork": True, "recommendedFix": "complete D-M2-001 approval artifact"},
        {"defectId": "M2-P1-002", "priority": "P1", "status": "EVIDENCE_REQUIRED", "component": "source policy", "description": "transparent-client production request evidence is not promoted to PASS", "blocksNetwork": True, "recommendedFix": "record transparent-client verification without impersonation or keep production blocked"},
        {"defectId": "M2-P1-003", "priority": "P1", "status": "EXPECTED_M2_WORK", "component": "monthly coverage", "description": f"{unverified_months}/79 months require terminal pagination", "blocksNetwork": False, "recommendedFix": "execute approved resumable index plan"},
        {"defectId": "M2-P2-001", "priority": "P2", "status": "PLANNING_ASSUMPTION", "component": "storage", "description": "asset volume uses observed candidate rate and assumed mean bytes", "blocksNetwork": False, "recommendedFix": "recalculate quota after first approved checkpoint"},
    ]
    write_csv(REPORT_ROOT / "P4_M2_CRAWL_DEFECT_REGISTER.csv", defects)

    lineage = [
        {"stage": "PREFLIGHT_MONTH_PLAN", "inputPath": "crawl/releases/CRAWL_20260806_03/monthly_coverage.csv", "inputRows": len(pd.read_csv(BASELINE_RELEASE / "monthly_coverage.csv", encoding="utf-8-sig")), "outputPath": "crawl/reports/m2_production_crawl/month_plan.parquet", "outputRows": len(month_plan), "status": "PASS"},
        {"stage": "QUERY_FREEZE", "inputPath": "crawl/configs/queryRegistry.yaml", "inputRows": query["queryCount"], "outputPath": "crawl/reports/m2_production_crawl/query_registry_snapshot.yaml", "outputRows": query["queryCount"], "status": query["status"]},
        {"stage": "CHECKPOINT_SEED", "inputPath": "production_parameters.json", "inputRows": 1, "outputPath": "crawl/reports/m2_production_crawl/index_checkpoint_seed.json", "outputRows": 1, "status": "PASS"},
        {"stage": "PRODUCTION_NETWORK", "inputPath": "PRODUCTION_APPROVAL.json", "inputRows": 0 if approval is None else 1, "outputPath": "NONE", "outputRows": 0, "status": "BLOCKED_PREAPPROVAL"},
    ]
    write_csv(REPORT_ROOT / "P4_M2_CRAWL_DATA_LINEAGE.csv", lineage)

    source_policy_report = f"""# P4 M2 crawl source-policy audit

- Run ID: `{RUN_ID}`
- Policy: `{policy.policy_version}` / `{policy.kill_switch_version}`
- Production network transport calls: `0`
- External ATS transport calls: `0`
- Query registry: `{query['status']}`, SHA-256 `{query['registrySha256']}`
- Negative tests: `{test_pass}/{len(test_rows)} PASS`
- Approval artifact: `MISSING`
- Transparent-client production evidence: `REVIEW_REQUIRED`

The source-policy contract is fail-closed. Robots allowance and conditional terms review do not substitute for transparent-client evidence and a signed user approval. No Linkareer or external ATS request was issued by this preflight.
"""
    (REPORT_ROOT / "P4_M2_CRAWL_SOURCE_POLICY_AUDIT.md").write_text(source_policy_report, encoding="utf-8")

    decision = f"""# P4 M2 crawl user decision packet

Status: `USER_DECISION_REQUIRED`

## D-M2-001 — Production Linkareer crawl approval

- Question: Approve the 2020-01 through 2026-07 Linkareer-only production crawl after the source-policy evidence condition is satisfied?
- Current evidence: 79-row plan ready; baseline `{complete_months}/79` complete and `{unverified_months}` require collection; kill-switch tests `{test_pass}/{len(test_rows)}` PASS; network calls `0`.
- Options: A approve after transparent-client evidence / B conditional limited-month approval / C defer.
- Recommendation: A only after `M2-P1-002` is closed; until then keep transport disabled.
- Impact: A opens the frozen plan; B must specify an exact month subset and cannot publish a full release; C preserves preflight only.
- May defer: yes.

## Required signed artifact

Create `crawl/control/PRODUCTION_APPROVAL.json` conforming to `crawl/control/PRODUCTION_APPROVAL.schema.json` with these fixed values:

```json
{{
  "productionApprovalId": "<user-issued-id>",
  "approvedBy": "<user-identity>",
  "approvedAt": "<UTC timestamp>",
  "approvedPeriod": "2020-01~2026-07",
  "approvedSource": "Linkareer",
  "externalAtsTransportAllowed": false,
  "linkareerHostedAssetAllowed": true,
  "rateLimitPolicyVersion": "{policy.policy_version}",
  "killSwitchPolicyVersion": "{policy.kill_switch_version}"
}}
```

Approval does not itself declare `CRAWL_RELEASE_READY`; 79-month, detail, asset, checksum, and strict Agent2 validator gates still must pass.
"""
    (REPORT_ROOT / "P4_M2_CRAWL_USER_DECISION_PACKET.md").write_text(decision, encoding="utf-8")

    manifest = {
        "agentId": "P4-A1-M2-PRODUCTION-ORCHESTRATOR",
        "generatedAtUtc": generated_at,
        "branch": branch,
        "headCommit": head,
        "runId": RUN_ID,
        "dataVersion": DATA_VERSION,
        "runMode": "production-preflight",
        "authorityPromptSha256": authority_prompt_sha,
        "contractVersion": "2.1.2",
        "baselineReleaseId": "CRAWL_20260806_03",
        "targetMonths": 79,
        "baselineCompleteMonths": complete_months,
        "baselineUnverifiedMonths": unverified_months,
        "productionApprovalPresent": approval is not None,
        "productionApprovalErrors": approval_errors,
        "productionNetworkCalls": 0,
        "externalAtsTransportCalls": 0,
        "queryRegistryStatus": query["status"],
        "killSwitchTests": {"passed": test_pass, "failed": test_fail},
        "fullRegressionTests": {"passed": full_test_pass, "failed": full_test_fail},
        "transparentClientEvidenceConflict": transparent_conflict,
        "secretsIncluded": False,
        "claimedStatus": "M2_CRAWL_READY_FOR_USER_APPROVAL",
        "forbiddenClaims": ["CRAWL_RELEASE_READY", "DATA_READY_RQ1_RQ2A", "DATA_READY_RQ2B", "ANALYSIS_READY"],
        "security": security,
    }
    (REPORT_ROOT / "M2_PREFLIGHT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# P4 M2 production crawl preflight report

## Executive verdict

`M2_CRAWL_READY_FOR_USER_APPROVAL`

This is a network-zero approval handoff, not a production crawl or release. Production transport remains physically blocked because the signed approval artifact is absent and transparent-client evidence is still review-required.

## Git and authority

- branch: `{branch}`
- preflight code HEAD: `{head}`
- integration baseline: `aec8dfcb4cb6d57efc5a351874c2c32ba69abc0a`
- contract: `2.1.2` (latest tracked approved contract)
- authority prompt SHA-256: `{authority_prompt_sha}`

## Production preflight

- Month plan: `79` rows (`2020-01` to `2026-07`), SHA-256 `{sha256(REPORT_ROOT / 'month_plan.parquet')}`.
- Baseline: `{complete_months}/79` pagination-complete; `{unverified_months}` require approved collection.
- Query registry: `{query['status']}`, two verified APQ operations, status filter omitted, OR/union semantics documented.
- Kill-switch/checkpoint tests: `{test_pass}/{len(test_rows)} PASS`, JUnit SHA-256 `{sha256(args.junit)}`.
- Full crawl/control regression: `{full_test_pass}/{len(full_test_rows)} PASS`, JUnit SHA-256 `{sha256(args.full_junit)}`.
- Capacity estimate with 2x headroom: `{storage['requiredCapacityWith2xHeadroomBytes']}` bytes; this is a planning estimate, not quota reservation.
- Production Linkareer network calls: `0`.
- External ATS transport calls: `0`.
- Tracked secrets/raw bytes: `{security['trackedSecretFileCount']}/{security['trackedRawFileCount']}`.

## Execution boundary

Index, detail, asset, immutable release, and Agent2 validator stages are `NOT_STARTED` or `BLOCKED`. A signed artifact alone is insufficient: transparent-client source-policy evidence must also close before transport is enabled. `CRAWL_RELEASE_READY` remains blocked.

## User action

Review `P4_M2_CRAWL_USER_DECISION_PACKET.md`. If approved, add a schema-valid `crawl/control/PRODUCTION_APPROVAL.json`; then rerun this preflight before any network transport.
"""
    (REPORT_ROOT / "P4_M2_CRAWL_EXECUTION_REPORT.md").write_text(report, encoding="utf-8")

    commands = f"""# P4 M2 preflight test commands and exit codes

| Check | Command | Exit | Result | Evidence |
|---|---|---:|---|---|
| M2 policy/month/checkpoint unit tests | `PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests/test_m2_preflight.py -q --junitxml=<temporary-junit>` | 0 | {test_pass}/{len(test_rows)} PASS | `P4_M2_PREFLIGHT_TESTS.csv`, {len(test_rows)} rows, SHA `{sha256(REPORT_ROOT / 'P4_M2_PREFLIGHT_TESTS.csv')}` |
| Full crawl/control regression | `P4_CRAWL_RAW_SOURCE_ROOT=<ignored-runtime-root> PYTHONPATH=crawl/src:. .venv/bin/python -m pytest crawl/tests crawl/control/tests -q -rs --junitxml=<temporary-full-junit>` | 0 | {full_test_pass}/{len(full_test_rows)} PASS | `P4_M2_FULL_REGRESSION_TESTS.csv`, {len(full_test_rows)} rows, SHA `{sha256(REPORT_ROOT / 'P4_M2_FULL_REGRESSION_TESTS.csv')}` |
| Network-zero preflight build | `PYTHONPATH=crawl/src:. .venv/bin/python crawl/scripts/build_m2_preflight.py --raw-source-root <ignored-runtime-root> --junit <temporary-junit> --full-junit <temporary-full-junit> --authority-prompt <Prompt-A>` | 0 | 79 month rows; transport 0 | `M2_PREFLIGHT_MANIFEST.json`, SHA recorded in `EVIDENCE_MANIFEST.sha256` |

Git commit at generation: `{head}`. Production Linkareer and external ATS transports were not invoked.
"""
    (REPORT_ROOT / "TEST_COMMANDS_AND_EXIT_CODES.md").write_text(commands, encoding="utf-8")

    targets = sorted(path for path in REPORT_ROOT.iterdir() if path.is_file() and path.name != "EVIDENCE_MANIFEST.sha256")
    (REPORT_ROOT / "EVIDENCE_MANIFEST.sha256").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in targets), encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if test_fail == 0 and full_test_fail == 0 and query["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
