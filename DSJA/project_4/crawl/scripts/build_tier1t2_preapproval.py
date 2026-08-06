#!/usr/bin/env python3
"""Build sequential Tier 1/2/3 canary proposals without transport or secrets."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRAWL_ROOT = PROJECT_ROOT / "crawl"
REPORT_ROOT = CRAWL_ROOT / "reports/tier1t2_preapproval"
TIER1_REPORT = CRAWL_ROOT / "reports/tier1_preapproval"
TIER1_SOURCE_COMMIT = "c17c7f5bc8c3eb1a9c1d12efb1eeb801f074f61c"
TIER1_SCOPE_SHA = "23dbc556f9d3b88efa9a42dbff0915a7da457ee355c5999c31ce66ab8425d5cb"
TIER1_EVIDENCE_SHA = "35395a82a6f3ecd6d8c518ea9138be776ccfe6c720d2345c366cc0ced6a07f66"
TIER0_HANDOFF_SHA = "6162d3aea6ff3646d4d9cb7ff09d09acf91bbde81a815896096bca82b6f63c42"
SCHEMA_VERSION = "p4-tier1t2-preapproval-v1"
RUN_ID = "TIER1T2_PREAPPROVAL_20260807_01"
DETAIL_SAMPLE_SIZE = 10
INDEX_REQUEST_PROPOSAL = 28

ASSET_FRONTIER = CRAWL_ROOT / (
    "runs/notebooks/observed-dev/MASTER_20260806_01/stages/crawl/notebooks/children/"
    "agent_runs/AGENT1/A1-03-ASSET/asset_frontier.csv"
)
ASSET_METRICS = ASSET_FRONTIER.with_name("asset_routing_metrics.json")
POSTING_MANIFEST = CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01/posting_manifest.csv"
RAW_MANIFEST = CRAWL_ROOT / "observed_inputs/OBSERVED_INPUT_20260806_01/raw_detail_manifest.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"empty evidence forbidden: {path.name}")
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def scan_new_tree() -> dict[str, int]:
    secret = re.compile(
        rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)|"
        rb"(?:api[_-]?key|service[_-]?key|cookie|token)\s*[:=]\s*['\"][^'\"]+",
        re.I,
    )
    absolute = re.compile(rb"/(?:home|mnt|Users)/[^\s,'\"]+")
    raw_signature = re.compile(rb"<(?:!doctype\s+html|html)[^>]*>|__APOLLO_STATE__", re.I)
    result = {"secretCookieKeyFindings": 0, "absolutePathFindings": 0, "rawByteSignatureFindings": 0}
    for path in REPORT_ROOT.iterdir():
        if not path.is_file():
            continue
        content = path.read_bytes()
        result["secretCookieKeyFindings"] += int(bool(secret.search(content)))
        result["absolutePathFindings"] += int(bool(absolute.search(content)))
        result["rawByteSignatureFindings"] += int(bool(raw_signature.search(content)))
    return result


def main() -> int:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    if any(REPORT_ROOT.iterdir()):
        raise RuntimeError("preapproval output is immutable; target directory is not empty")
    if sha256(TIER1_REPORT / "P4_TIER1_SCOPE_PROPOSAL.json") != TIER1_SCOPE_SHA:
        raise RuntimeError("Tier 1 scope proposal drift")
    if sha256(TIER1_REPORT / "EVIDENCE_MANIFEST.sha256") != TIER1_EVIDENCE_SHA:
        raise RuntimeError("Tier 1 evidence manifest drift")

    generated = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    tier1 = json.loads((TIER1_REPORT / "P4_TIER1_SCOPE_PROPOSAL.json").read_text(encoding="utf-8"))
    if tier1["proposedMaxIndexRequests"] != INDEX_REQUEST_PROPOSAL:
        raise RuntimeError("Tier 1 index request proposal drift")

    postings = pd.read_csv(POSTING_MANIFEST, encoding="utf-8-sig", dtype={"sourcePostingId": str})
    assets = pd.read_csv(ASSET_FRONTIER, encoding="utf-8-sig", dtype={"sourcePostingId": str})
    metrics = json.loads(ASSET_METRICS.read_text(encoding="utf-8"))
    raw_rows = load_jsonl(RAW_MANIFEST)
    posting_ids = set(postings["sourcePostingId"])
    per_posting = assets.groupby("sourcePostingId").size()
    all_counts = pd.Series([int(per_posting.get(posting_id, 0)) for posting_id in sorted(posting_ids)])
    hosts = sorted({(urlparse(value).hostname or "").lower() for value in assets["assetUrl"]})
    linkareer_hosted = all(host == "linkareer.com" or host.endswith(".linkareer.com") for host in hosts)
    external_count = int(assets["externalAtsAsset"].astype(str).str.lower().eq("true").sum())
    observed_max = int(all_counts.max())
    proposed_max_assets = DETAIL_SAMPLE_SIZE * observed_max
    average_all = float(all_counts.mean())
    bearing_rate = float((all_counts > 0).mean())
    conditional_mean = float(per_posting.mean())

    raw_sizes = [int(row["bytes"]) for row in raw_rows]
    detail_mean_bytes = sum(raw_sizes) / len(raw_sizes)
    detail_max_bytes = max(raw_sizes)
    detail_upper_bytes = DETAIL_SAMPLE_SIZE * detail_max_bytes
    index_storage_bytes = int(tier1["estimatedStorageBytes"])

    scope = {
        "schemaVersion": SCHEMA_VERSION,
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "runId": RUN_ID,
        "tier1": {
            "candidateScopeId": tier1["candidateScopeId"],
            "periodMonths": tier1["candidatePeriodOrQuery"]["periodMonths"],
            "queryOperations": tier1["candidatePeriodOrQuery"]["queryOperations"],
            "proposedMaxIndexRequests": INDEX_REQUEST_PROPOSAL,
            "status": "AWAITING_USER_TIER1_APPROVAL",
        },
        "tier2": {
            "sampleSize": DETAIL_SAMPLE_SIZE,
            "proposedMaxDetailRequests": DETAIL_SAMPLE_SIZE,
            "sampleStatus": "NOT_EVALUATED_AWAITING_TIER1_DISCOVERY",
            "status": "BLOCKED_UNTIL_TIER1_ACCEPTED_AND_NEW_APPROVAL",
        },
        "tier3": {
            "proposedMaxAssetRequests": proposed_max_assets,
            "status": "BLOCKED_UNTIL_TIER2_ACCEPTED_AND_NEW_APPROVAL",
        },
        "combinedPlanningRequestCeiling": INDEX_REQUEST_PROPOSAL + DETAIL_SAMPLE_SIZE + proposed_max_assets,
        "sequentialApprovalRequired": True,
        "tier1SourceCommit": TIER1_SOURCE_COMMIT,
        "tier1ScopeProposalSha256": TIER1_SCOPE_SHA,
        "tier1EvidenceManifestSha256": TIER1_EVIDENCE_SHA,
        "tier0CanonicalHandoffManifestSha256": TIER0_HANDOFF_SHA,
        "networkCalls": 0,
        "detailCalls": 0,
        "assetCalls": 0,
        "externalAtsTransportCalls": 0,
        "browserAutomationCalls": 0,
        "credentialedApiCalls": 0,
        "generatedAtUtc": generated,
    }
    write_json(REPORT_ROOT / "P4_TIER1T2_SCOPE_PROPOSAL.json", scope)

    sample_contract = {
        "schemaVersion": SCHEMA_VERSION,
        "contractStatus": "NOT_EVALUATED_AWAITING_TIER1_DISCOVERY",
        "sampleFrame": "UNIQUE_POSTING_IDS_FROM_ACCEPTED_TIER1_DISCOVERY_MANIFEST",
        "sampleFrameRows": None,
        "sampleSize": DETAIL_SAMPLE_SIZE,
        "samplingMethod": "DETERMINISTIC_RANDOM_WITHOUT_REPLACEMENT",
        "samplingSeedExpression": "SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)",
        "samplingSeedStatus": "NOT_EVALUATED_AWAITING_REQUIRED_INPUTS",
        "tier1CanaryRunIdInput": None,
        "tier1DiscoveryManifestSha256Input": None,
        "scopeApprovalHashInput": None,
        "replacement": False,
        "terminalFailureReplacementAllowed": False,
        "selectionManifest": "detail_canary_sample_manifest.json",
        "selectionManifestStatus": "NOT_CREATED_BEFORE_TIER1_DISCOVERY",
        "postingIds": [],
        "terminalStatusesPreserved": [
            "FETCHED_VALID", "FETCHED_EMPTY_VALID", "NOT_FOUND", "EXPIRED",
            "POLICY_BLOCKED", "RETRY_EXHAUSTED", "PARSER_QUARANTINED",
        ],
        "ambiguousFallbackAutoSelectionAllowed": False,
        "rawMutationAllowed": False,
        "networkCalls": 0,
        "detailCalls": 0,
        "externalAtsTransportCalls": 0,
    }
    write_json(REPORT_ROOT / "P4_TIER2_DETAIL_SAMPLE_CONTRACT.json", sample_contract)

    asset_estimate = {
        "schemaVersion": SCHEMA_VERSION,
        "proposalStatus": "PROPOSED_NOT_APPROVED",
        "evidenceMode": "CHECKED_IN_OBSERVED_METADATA_ONLY_NO_ASSET_FETCH",
        "evidencePostingRows": len(postings),
        "evidenceAssetCandidateRows": len(assets),
        "assetBearingPostingRows": int((all_counts > 0).sum()),
        "assetBearingPostingRate": bearing_rate,
        "assetCandidatesPerPostingAllMean": average_all,
        "assetCandidatesPerBearingPostingMean": conditional_mean,
        "observedAssetCandidatesPerPostingMaximum": observed_max,
        "detailSampleSize": DETAIL_SAMPLE_SIZE,
        "meanExpectedAssetCandidatesForSample": average_all * DETAIL_SAMPLE_SIZE,
        "proposedMaxAssetRequests": proposed_max_assets,
        "upperBoundMethod": "DETAIL_SAMPLE_SIZE_X_OBSERVED_MAX_CANDIDATES_PER_POSTING",
        "hostEvidence": hosts,
        "linkareerHostedCandidateRows": len(assets) if linkareer_hosted else 0,
        "externalAtsCandidateRows": external_count,
        "metadataCandidatesMetric": metrics["metadataCandidates"],
        "ocrCandidateRows": metrics["ocrCandidates"],
        "assetsFetchedEvidenceRows": metrics["assetsFetched"],
        "assetByteEstimateStatus": "NOT_EVALUATED_NO_FETCHED_ASSET_BYTES",
        "uncertainty": "Observed-development metadata may not represent Tier 1 discoveries; request ceiling uses the observed maximum but is not a population bound.",
        "assetFrontierSha256": sha256(ASSET_FRONTIER),
        "assetRoutingMetricsSha256": sha256(ASSET_METRICS),
        "postingManifestSha256": sha256(POSTING_MANIFEST),
        "networkCalls": 0,
        "assetCalls": 0,
        "externalAtsTransportCalls": 0,
        "ocrExtractionCalls": 0,
        "ncsMappingPromotions": 0,
    }
    write_json(REPORT_ROOT / "P4_TIER3_ASSET_REQUEST_ESTIMATE.json", asset_estimate)

    storage = {
        "schemaVersion": SCHEMA_VERSION,
        "proposalStatus": "STATIC_ESTIMATE_NOT_QUOTA_RESERVATION",
        "tier1IndexEstimatedStorageBytes": index_storage_bytes,
        "observedDetailRawRows": len(raw_rows),
        "observedDetailRawMeanBytes": detail_mean_bytes,
        "observedDetailRawMaxBytes": detail_max_bytes,
        "tier2DetailUpperEstimateBytes": detail_upper_bytes,
        "preAssetKnownUpperEstimateBytes": index_storage_bytes + detail_upper_bytes,
        "tier3AssetStorageBytes": None,
        "tier3AssetStorageStatus": "NOT_EVALUATED_NO_FETCHED_ASSET_BYTES",
        "totalStorageReservationStatus": "BLOCKED_UNTIL_ASSET_SIZE_EVIDENCE_OR_USER_QUOTA",
        "rawStorageMode": "IMMUTABLE_CONTENT_ADDRESSED_EXTERNAL_STORAGE",
        "gitRawBytesAllowed": False,
        "automatedDeletionAllowed": False,
        "rawDetailManifestSha256": sha256(RAW_MANIFEST),
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
    }
    write_json(REPORT_ROOT / "P4_TIER1T2_STORAGE_ESTIMATE.json", storage)

    policies = [
        {"policyId": "TIER1_BINDING", "status": "PASS", "observed": f"scope={tier1['candidateScopeId']}; maxIndex=28"},
        {"policyId": "TIER2_SAMPLE_NOT_PRESELECTED", "status": "PASS", "observed": "postingIds=0; awaiting Tier1 discovery"},
        {"policyId": "TIER2_NO_REPLACEMENT", "status": "PASS", "observed": "sample=10; deterministic; without replacement; terminal failure preserved"},
        {"policyId": "TIER2_AMBIGUOUS_FALLBACK_DENY", "status": "PASS", "observed": "ambiguousAutoSelectionAllowed=false"},
        {"policyId": "TIER3_LINKAREER_HOST_ONLY", "status": "PASS" if linkareer_hosted and external_count == 0 else "FAIL", "observed": f"hosts={hosts}; external={external_count}"},
        {"policyId": "TIER3_ASSET_BYTES", "status": "NOT_EVALUATED", "observed": "assetsFetched=0"},
        {"policyId": "OCR_EXTRACTION_MAPPING", "status": "BLOCKED", "observed": "collect/queue metadata only; extraction=0; mapping=0"},
        {"policyId": "SEQUENTIAL_APPROVAL", "status": "PASS", "observed": "new approval required for every tier"},
        {"policyId": "NETWORK_ZERO", "status": "PASS", "observed": "index=0; detail=0; asset=0; externalATS=0"},
    ]
    for row in policies:
        row.update({"runId": RUN_ID, "networkCalls": 0, "externalAtsTransportCalls": 0})
    write_csv(REPORT_ROOT / "P4_TIER1T2_POLICY_AUDIT.csv", policies)

    packet = f"""# P4 Tier 1/2/3 sequential canary preapproval packet

Status: `PREAPPROVAL_ONLY_NO_NETWORK_AUTHORITY`

## Bound Tier 1 proposal

- Source commit: `{TIER1_SOURCE_COMMIT}`
- Scope: `2026-03`, index-only APQ
- Proposed maximum index requests: `{INDEX_REQUEST_PROPOSAL}`
- Tier 1 approval: `MISSING`

## Tier 2 detail proposal

- Status: `NOT_EVALUATED_AWAITING_TIER1_DISCOVERY`
- Sample size: `{DETAIL_SAMPLE_SIZE}`
- Frame: unique posting IDs from the accepted Tier 1 discovery manifest
- Seed: `SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)`
- Sampling: deterministic random without replacement
- Terminal failure replacement: forbidden
- Posting IDs selected now: `0`
- Proposed maximum detail requests: `{DETAIL_SAMPLE_SIZE}`

Tier 2 needs a new user approval after Tier 1 acceptance. This packet does not
select, invent or authorize any posting ID.

## Tier 3 Linkareer-hosted asset proposal

- Evidence: `{len(assets)}` checked-in metadata candidates across `{len(postings)}` postings
- Asset-bearing postings: `{int((all_counts > 0).sum())}`
- Per-posting mean: `{average_all:.6f}`
- Conditional mean among bearing postings: `{conditional_mean:.6f}`
- Observed maximum per posting: `{observed_max}`
- Proposed maximum asset requests: `{DETAIL_SAMPLE_SIZE} × {observed_max} = {proposed_max_assets}`
- Hosts: `{', '.join(hosts)}`
- External ATS candidates/calls: `0/0`
- Fetched asset byte evidence: `0`; asset storage remains `NOT_EVALUATED`
- OCR: candidate queue metadata only; extraction and mapping calls `0`

Tier 3 needs another new user approval after Tier 2 acceptance. External hosts,
browser automation, OCR extraction, mapping and promotion remain forbidden.

## Storage evidence

- Tier 1 index estimate: `{index_storage_bytes}` bytes
- Tier 2 detail upper estimate: `{detail_upper_bytes}` bytes, using observed max `{detail_max_bytes}` × 10
- Known pre-asset estimate: `{index_storage_bytes + detail_upper_bytes}` bytes
- Asset and total reservation: `NOT_EVALUATED`

## Approval boundary

This document contains proposals only. It does not supply any approved scope,
budget, expiration, rate, retry, source-policy record or network authority.
"""
    (REPORT_ROOT / "P4_TIER1T2_COMBINED_APPROVAL_PACKET.md").write_text(packet, encoding="utf-8")

    scans = scan_new_tree()
    tests = [
        {"testId": "TIER1_SCOPE_SHA_BOUND", "status": "PASS", "observed": TIER1_SCOPE_SHA},
        {"testId": "TIER1_EVIDENCE_SHA_BOUND", "status": "PASS", "observed": TIER1_EVIDENCE_SHA},
        {"testId": "TIER2_POSTING_IDS_NOT_INVENTED", "status": "PASS" if not sample_contract["postingIds"] else "FAIL", "observed": len(sample_contract["postingIds"])},
        {"testId": "TIER2_SEED_NOT_EVALUATED", "status": "PASS" if sample_contract["samplingSeedStatus"].startswith("NOT_EVALUATED") else "FAIL", "observed": sample_contract["samplingSeedStatus"]},
        {"testId": "ASSET_EVIDENCE_ROWS", "status": "PASS" if len(assets) == metrics["metadataCandidates"] else "FAIL", "observed": len(assets)},
        {"testId": "ASSET_HOST_POLICY", "status": "PASS" if linkareer_hosted and external_count == 0 else "FAIL", "observed": hosts},
        {"testId": "SECRET_COOKIE_KEY_SCAN", "status": "PASS" if scans["secretCookieKeyFindings"] == 0 else "FAIL", "observed": scans["secretCookieKeyFindings"]},
        {"testId": "ABSOLUTE_PATH_SCAN", "status": "PASS" if scans["absolutePathFindings"] == 0 else "FAIL", "observed": scans["absolutePathFindings"]},
        {"testId": "RAW_BYTE_SIGNATURE_SCAN", "status": "PASS" if scans["rawByteSignatureFindings"] == 0 else "FAIL", "observed": scans["rawByteSignatureFindings"]},
        {"testId": "NETWORK_ZERO", "status": "PASS", "observed": 0},
    ]
    for row in tests:
        row.update({"runId": RUN_ID, "networkCalls": 0, "externalAtsTransportCalls": 0})
    write_csv(REPORT_ROOT / "P4_TIER1T2_PREAPPROVAL_TEST_SUMMARY.csv", tests)

    expected = {
        "P4_TIER1T2_SCOPE_PROPOSAL.json",
        "P4_TIER2_DETAIL_SAMPLE_CONTRACT.json",
        "P4_TIER3_ASSET_REQUEST_ESTIMATE.json",
        "P4_TIER1T2_STORAGE_ESTIMATE.json",
        "P4_TIER1T2_POLICY_AUDIT.csv",
        "P4_TIER1T2_COMBINED_APPROVAL_PACKET.md",
        "P4_TIER1T2_PREAPPROVAL_TEST_SUMMARY.csv",
    }
    actual = {path.name for path in REPORT_ROOT.iterdir() if path.is_file()}
    if actual != expected:
        raise RuntimeError(f"unexpected artifacts: {sorted(actual ^ expected)}")
    evidence = REPORT_ROOT / "EVIDENCE_MANIFEST.sha256"
    evidence.write_text(
        "\n".join(f"{sha256(REPORT_ROOT / name)}  {name}" for name in sorted(expected)) + "\n",
        encoding="utf-8",
    )
    if any(row["status"] == "FAIL" for row in tests):
        return 1
    print(json.dumps({
        "status": "TIER1T2_PREAPPROVAL_PACKET_READY",
        "branch": git("branch", "--show-current"),
        "tier1MaxIndexRequestsProposal": INDEX_REQUEST_PROPOSAL,
        "tier2MaxDetailRequestsProposal": DETAIL_SAMPLE_SIZE,
        "tier3MaxAssetRequestsProposal": proposed_max_assets,
        "combinedPlanningRequestCeiling": INDEX_REQUEST_PROPOSAL + DETAIL_SAMPLE_SIZE + proposed_max_assets,
        "assetEvidenceRows": len(assets),
        "networkCalls": 0,
        "externalAtsTransportCalls": 0,
        "artifacts": 8,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
