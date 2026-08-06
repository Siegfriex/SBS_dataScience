#!/usr/bin/env python3
"""Publish a raw-free canonical handoff from an existing local canary runtime."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA_VERSION = "p4-canary-handoff-v1"
EMPTY_REASON = "NETWORK_NOT_AUTHORIZED"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_PATH_RE = re.compile(r"(?:/home/|/mnt/|[A-Za-z]:\\\\)")
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|session[_-]?cookie|authorization)\s*[:=]\s*[^,;\s]{8,}"
)
RUNTIME_NAMES = (
    "canary_plan.json", "approval_binding.json", "request_attempt.jsonl",
    "request_response_manifest.jsonl", "checkpoint_manifest.json",
    "raw_object_manifest.jsonl", "index_results.parquet", "detail_results.parquet",
    "asset_results.parquet", "canary_coverage.csv", "kill_switch_events.jsonl",
    "quarantine_manifest.jsonl", "stage_manifest.json", "stage_metrics.json",
    "stage_quality.csv", "CHECKSUMS.sha256",
)
HANDOFF_NAMES = RUNTIME_NAMES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def empty_envelope(run_id: str, artifact_type: str) -> dict[str, Any]:
    return {
        "recordType": "EMPTY_ARTIFACT",
        "artifactType": artifact_type,
        "runId": run_id,
        "schemaVersion": SCHEMA_VERSION,
        "emptyReason": EMPTY_REASON,
        "rowCount": 0,
    }


def write_empty_jsonl(
    path: Path, run_id: str, artifact_type: str, extra: dict[str, Any] | None = None
) -> None:
    payload = empty_envelope(run_id, artifact_type)
    payload.update(extra or {})
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_empty_parquet(
    path: Path, run_id: str, data_version: str, key_name: str, context_name: str
) -> None:
    schema = pa.schema([
        pa.field(key_name, pa.string()),
        pa.field(context_name, pa.string()),
        pa.field("terminalStatus", pa.string()),
        pa.field("canaryRunId", pa.string()),
        pa.field("canaryDataVersion", pa.string()),
        pa.field("schemaVersion", pa.string()),
        pa.field("emptyReason", pa.string()),
    ]).with_metadata({
        b"p4.runId": run_id.encode(),
        b"p4.dataVersion": data_version.encode(),
        b"p4.schemaVersion": SCHEMA_VERSION.encode(),
        b"p4.emptyReason": EMPTY_REASON.encode(),
        b"p4.rowCount": b"0",
    })
    arrays = [pa.array([], type=field.type) for field in schema]
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), path, compression="zstd")


def verify_runtime_checksums(root: Path) -> None:
    missing = [name for name in RUNTIME_NAMES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"runtime artifacts missing: {missing}")
    declared: set[str] = set()
    for line in (root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(maxsplit=1); name = name.strip(); declared.add(name)
        if not SHA256_RE.fullmatch(expected) or sha256_file(root / name) != expected:
            raise ValueError(f"runtime checksum mismatch: {name}")
    expected_names = set(RUNTIME_NAMES) - {"CHECKSUMS.sha256"}
    if declared != expected_names:
        raise ValueError("runtime checksum declaration set mismatch")


def validate_redacted_tree(root: Path) -> dict[str, int]:
    expected = set(HANDOFF_NAMES)
    actual = {path.name for path in root.iterdir() if path.is_file()}
    if actual != expected:
        raise ValueError(f"handoff file set mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    absolute_hits = 0
    secret_hits = 0
    zero_byte = 0
    for path in root.iterdir():
        if not path.is_file():
            continue
        if path.stat().st_size == 0:
            zero_byte += 1
        if path.suffix in {".json", ".jsonl", ".csv", ".sha256"}:
            text = path.read_text(encoding="utf-8-sig", errors="strict")
            absolute_hits += int(bool(ABSOLUTE_PATH_RE.search(text)))
            secret_hits += int(bool(SECRET_RE.search(text)))
    if absolute_hits or secret_hits or zero_byte:
        raise ValueError(
            f"redaction scan failed: absolute={absolute_hits} secret={secret_hits} zeroByte={zero_byte}"
        )
    return {"files": len(actual), "absolutePathHits": absolute_hits, "secretHits": secret_hits, "zeroByteFiles": zero_byte}


def publish(runtime: Path, output: Path, source_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase Git SHA")
    resolved_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=runtime, text=True, capture_output=True, check=True
    ).stdout.strip()
    if source_commit != resolved_head:
        raise ValueError(f"source commit is not current HEAD: expected={resolved_head} observed={source_commit}")
    verify_runtime_checksums(runtime)
    runtime_plan = json.loads((runtime / "canary_plan.json").read_text(encoding="utf-8"))
    runtime_binding = json.loads((runtime / "approval_binding.json").read_text(encoding="utf-8"))
    runtime_stage = json.loads((runtime / "stage_manifest.json").read_text(encoding="utf-8"))
    runtime_metrics = json.loads((runtime / "stage_metrics.json").read_text(encoding="utf-8"))
    run_id = str(runtime_plan["canaryRunId"])
    data_version = f"canary-t0-{run_id.casefold()}"
    output.mkdir(parents=True, exist_ok=True)

    plan = {
        "agentId": "P4-A1-CANARY-CRAWL-ORCHESTRATOR",
        "schemaVersion": SCHEMA_VERSION,
        "branch": "agent/p4-a1-canary-crawl-v1",
        "sourceCommit": source_commit,
        "sourceCommitAtRun": runtime_plan["headCommitAtRun"],
        "sourceRuntimeChecksumsSha256": sha256_file(runtime / "CHECKSUMS.sha256"),
        "canaryRunId": run_id,
        "canaryDataVersion": data_version,
        "canaryStorageRootId": "P4_CANARY_LOCAL_RUNTIME",
        "defectFamily": runtime_plan["defectFamily"],
        "runMode": "fixture-only",
        "status": "CANARY_BLOCKED_BY_POLICY",
        "approvalId": "NONE",
        "canaryScope": {"tier": 0, "mode": "fixture-only", "periodMonths": []},
        "networkCalls": 0,
        "detailRequestCount": 0,
        "assetRequestCount": 0,
        "queryRegistrySha256": runtime_binding["queryRegistrySha256"],
        "sourcePolicyAuditSha256": runtime_binding["sourcePolicyAuditSha256"],
        "sourcePolicyVersion": "p4-linkareer-source-policy-v1",
        "rateLimitPolicyVersion": "p4-linkareer-production-rate-v1",
        "killSwitchPolicyVersion": "p4-linkareer-kill-switch-v1",
        "outputRootRelative": f"crawl/handoffs/canary/{run_id}",
        "analysisPromotionAllowed": False,
        "releasePromotionAllowed": False,
        "externalAtsTransportAllowed": False,
        "browserAutomationAllowed": False,
    }
    write_json(output / "canary_plan.json", plan)
    write_json(output / "approval_binding.json", {
        "schemaVersion": SCHEMA_VERSION,
        "canaryRunId": run_id,
        "approvalId": "NONE",
        "status": "CANARY_APPROVAL_MISSING",
        "networkCalls": 0,
        "approvalArtifactSha256": None,
        "queryRegistrySha256": runtime_binding["queryRegistrySha256"],
        "sourcePolicyAuditSha256": runtime_binding["sourcePolicyAuditSha256"],
        "validationErrors": ["CANARY_APPROVAL_MISSING"],
    })

    for name, artifact_type in (
        ("request_attempt.jsonl", "REQUEST_ATTEMPT"),
        ("request_response_manifest.jsonl", "REQUEST_RESPONSE"),
        ("kill_switch_events.jsonl", "KILL_SWITCH_EVENT"),
        ("quarantine_manifest.jsonl", "QUARANTINE_RECORD"),
    ):
        write_empty_jsonl(output / name, run_id, artifact_type)
    write_empty_jsonl(output / "raw_object_manifest.jsonl", run_id, "RAW_OBJECT", {
        "storageRootId": "P4_CANARY_LOCAL_RUNTIME",
        "objectLocatorRelative": None,
        "compressedSha256": None,
        "contentSha256": None,
        "byteCount": 0,
        "contentByteCount": 0,
    })

    write_empty_parquet(output / "index_results.parquet", run_id, data_version, "requestKey", "periodMonth")
    write_empty_parquet(output / "detail_results.parquet", run_id, data_version, "requestKey", "postingId")
    write_empty_parquet(output / "asset_results.parquet", run_id, data_version, "requestKey", "assetId")

    coverage_rows = [{
        "runId": run_id,
        "dataVersion": data_version,
        "schemaVersion": SCHEMA_VERSION,
        "coverageLayer": layer,
        "plannedCount": 0,
        "terminalCount": 0,
        "coverage": "NOT_EVALUATED",
        "unknownTerminalStatusCount": 0,
        "nullTerminalStatusCount": 0,
        "quarantineIncluded": "true",
        "emptyReason": EMPTY_REASON,
    } for layer in ("MONTH", "PAGE", "POSTING", "ASSET")]
    write_csv(output / "canary_coverage.csv", list(coverage_rows[0]), coverage_rows)

    raw_manifest_sha = sha256_file(output / "raw_object_manifest.jsonl")
    coverage_sha = sha256_file(output / "canary_coverage.csv")
    checkpoint = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "checkpoints": [{
            "checkpointId": f"{run_id}-CP-000",
            "runId": run_id,
            "previousCheckpointSha256": None,
            "createdAtUtc": runtime_stage["createdAtUtc"],
            "completedMonthKeys": [],
            "completedRequestKeys": [],
            "terminalPostingIds": [],
            "terminalAssetIds": [],
            "requestLedgerOffset": 0,
            "rawObjectManifestSha256": raw_manifest_sha,
            "coverageSnapshotSha256": coverage_sha,
            "emptyReason": EMPTY_REASON,
        }],
    }
    write_json(output / "checkpoint_manifest.json", checkpoint)

    write_json(output / "stage_manifest.json", {
        "schemaVersion": SCHEMA_VERSION,
        "stageId": "CANARY-T0-FIXTURE",
        "runId": run_id,
        "dataVersion": data_version,
        "status": "CANARY_BLOCKED_BY_POLICY",
        "createdAtUtc": runtime_stage["createdAtUtc"],
        "runMode": "fixture-only",
        "sourceRuntimeManifestSha256": sha256_file(runtime / "stage_manifest.json"),
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "analysisPromotionAllowed": False,
        "releasePromotionAllowed": False,
    })
    write_json(output / "stage_metrics.json", {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "dataVersion": data_version,
        "status": "CANARY_BLOCKED_BY_POLICY",
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "credentialedApiCalls": 0,
        "fixtureChecks": runtime_metrics["fixtureChecks"],
        "fixtureChecksPassed": runtime_metrics["fixtureChecksPassed"],
        "requestCount": 0,
        "rawObjectCount": 0,
        "quarantinedRows": 0,
        "analysisPromotionAllowed": False,
        "releasePromotionAllowed": False,
        "rawShaCompleteness": "NOT_EVALUATED",
        "detailTerminalCoverage": "NOT_EVALUATED",
        "assetTerminalCoverage": "NOT_EVALUATED",
    })
    quality_rows = [{
        "runId": run_id,
        "dataVersion": data_version,
        "schemaVersion": SCHEMA_VERSION,
        "checkId": row["checkId"],
        "status": row["status"],
        "observed": row["observed"],
        "evidenceMode": "FIXTURE_ONLY",
    } for row in csv.DictReader((runtime / "stage_quality.csv").open(encoding="utf-8-sig", newline=""))]
    write_csv(output / "stage_quality.csv", list(quality_rows[0]), quality_rows)

    checksum_names = sorted(set(HANDOFF_NAMES) - {"CHECKSUMS.sha256"})
    (output / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha256_file(output / name)}  {name}\n" for name in checksum_names),
        encoding="utf-8",
    )
    scan = validate_redacted_tree(output)
    return {
        "runId": run_id,
        "dataVersion": data_version,
        "files": len(HANDOFF_NAMES),
        "sourceCommit": source_commit,
        "sourceRuntimeChecksumsSha256": plan["sourceRuntimeChecksumsSha256"],
        "handoffChecksumsSha256": sha256_file(output / "CHECKSUMS.sha256"),
        "scan": scan,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = publish(args.runtime_root.resolve(), args.output_root.resolve(), args.source_commit)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
