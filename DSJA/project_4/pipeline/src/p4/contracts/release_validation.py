from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from p4.contracts.loader import assess_crawl_release


def _gap(
    release_id: str,
    failed_gate: str,
    required_value: Any,
    observed_value: Any,
    affected_paths: list[str],
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "releaseId": release_id,
        "failedGate": failed_gate,
        "requiredValue": required_value,
        "observedValue": observed_value,
        "affectedPaths": affected_paths,
        "blocking": blocking,
    }


def validate_release_gates(
    handoff_path: str | Path,
    *,
    expected_contract_version: str = "2.1.2",
) -> dict[str, Any]:
    """Separate parser/source conformance from full empirical-corpus acceptance."""
    handoff_path = Path(handoff_path)
    root = handoff_path.parent
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assessment = assess_crawl_release(handoff_path, expected_contract_version)
    release_id = assessment["releaseId"]
    coverage_relative = str(payload.get("coverage_path", payload.get("coveragePath")))
    coverage_path = root / coverage_relative
    coverage = pd.read_parquet(coverage_path) if coverage_path.suffix == ".parquet" else pd.read_csv(coverage_path)
    period = pd.to_datetime(coverage["periodMonth"], errors="coerce")
    source_start = pd.Timestamp(payload.get("source_start", payload.get("sourceStart")))
    source_end = pd.Timestamp(payload.get("source_end", payload.get("sourceEnd")))
    coverage = coverage.loc[period.between(source_start, source_end)].copy()
    coverage_reason = coverage.get("coverageReason", pd.Series(dtype="string")).fillna("").astype(str)
    complete_months = int(coverage_reason.eq("complete").sum())
    target_months = int(len(coverage))
    unverified_months = int(coverage_reason.eq("paginationUnverified").sum())

    manifest_relative = next(
        (
            str(value)
            for value in payload.get("manifest_paths", payload.get("manifestPaths", []))
            if "posting_manifest" in str(value) and str(value).endswith(".parquet")
        ),
        "posting_manifest.parquet",
    )
    posting_manifest = pd.read_parquet(root / manifest_relative)
    observed_postings = int(posting_manifest["sourcePostingId"].astype(str).nunique())
    posting_manifest_raw_only = int(posting_manifest["hasDetailRawHtml"].fillna(False).astype(bool).sum())
    fetch_relative = next(
        (str(value) for value in payload.get("manifest_paths", []) if "fetch_manifest" in str(value)),
        "fetch_manifest.jsonl",
    )
    fetch_rows = [json.loads(line) for line in (root / fetch_relative).read_text(encoding="utf-8").splitlines() if line]
    raw_detail_count = sum(str(row.get("entityType")).casefold() == "detail" for row in fetch_rows)
    raw_detail_unique_ids = len(
        {
            str(row.get("requestUrl") or "").rstrip("/").split("/")[-1]
            for row in fetch_rows
            if str(row.get("entityType")).casefold() == "detail" and row.get("requestUrl")
        }
    )
    gap_text = " ".join(str(value) for value in payload.get("known_gaps", []))
    discovered_match = re.search(r"([\d,]+) distinct posting IDs", gap_text)
    discovered_postings = int(discovered_match.group(1).replace(",", "")) if discovered_match else observed_postings

    gaps: list[dict[str, Any]] = []
    if assessment["contractVersion"] != expected_contract_version:
        gaps.append(
            _gap(release_id, "contractVersion", expected_contract_version, assessment["contractVersion"], ["HANDOFF.json"])
        )
    if not payload.get("head_commit"):
        gaps.append(_gap(release_id, "releaseCommitLineage", "non-empty immutable commit", "", ["HANDOFF.json"]))
    if not assessment["paginationVerified"] or unverified_months:
        gaps.append(
            _gap(
                release_id,
                "monthlyPaginationCompleteness",
                {"paginationVerified": True, "completeMonths": target_months},
                {
                    "paginationVerified": assessment["paginationVerified"],
                    "completeMonths": complete_months,
                    "targetMonths": target_months,
                    "unverifiedMonths": unverified_months,
                },
                ["HANDOFF.json", coverage_relative],
            )
        )
    if assessment["releaseStatus"] not in {"READY", "CRAWL_READY"}:
        gaps.append(
            _gap(
                release_id,
                "releaseStatus",
                ["READY", "CRAWL_READY"],
                assessment["releaseStatus"],
                ["HANDOFF.json"],
            )
        )
    if not assessment["detailRawPerRecordLineageVerified"] or raw_detail_count < observed_postings:
        gaps.append(
            _gap(
                release_id,
                "fullDetailRawLineage",
                {"rawDetailRecords": discovered_postings, "perRecordSha256": True},
                {
                    "discoveredPostingIds": discovered_postings,
                    "observedManifestPostings": observed_postings,
                    "rawDetailManifestRows": raw_detail_count,
                    "postingManifestRawOnlyRows": posting_manifest_raw_only,
                    "perRecordSha256": assessment["detailRawPerRecordLineageVerified"],
                },
                [fetch_relative, manifest_relative],
            )
        )
    asset_relative = next(
        (str(value) for value in payload.get("manifest_paths", []) if "asset_manifest" in str(value)),
        None,
    )
    if asset_relative:
        asset_count = sum(1 for line in (root / asset_relative).read_text(encoding="utf-8").splitlines() if line)
        if asset_count < 50:
            gaps.append(
                _gap(
                    release_id,
                    "ocrAssetAcquisition",
                    {"benchmarkAssetMinimum": 50, "routedAssetsFetched": "all"},
                    {"assetManifestRows": asset_count},
                    [asset_relative],
                )
            )
    terms_status = payload.get("terms_status", payload.get("termsStatus"))
    if terms_status and terms_status != "approved":
        gaps.append(
            _gap(release_id, "sourcePolicyApproval", "approved", terms_status, ["HANDOFF.json"])
        )
    if "required request parameter schema remains unknown" in gap_text:
        gaps.append(
            _gap(
                release_id,
                "ncsKsaRequestSchema",
                "verified request parameters and reproducible KSA response",
                "endpoint valid; request parameter schema unknown",
                ["HANDOFF.json", "ncs_manifest.jsonl"],
            )
        )

    source_pass = bool(
        assessment["checksumPassed"]
        and assessment["contractVersion"] == expected_contract_version
        and payload.get("transparent_client_verified")
        and payload.get("robots_status") == "allowed"
    )
    full_pass = source_pass and not any(item["blocking"] for item in gaps)
    return {
        "releaseId": release_id,
        "contractVersion": assessment["contractVersion"],
        "sourceAdapterConformance": "PASS" if source_pass else "FAIL",
        "fullCorpusAcceptance": "PASS" if full_pass else "FAIL",
        "checksumPassed": assessment["checksumPassed"],
        "checksumCount": assessment["checksumCount"],
        "coverage": {
            "targetMonths": target_months,
            "completeMonths": complete_months,
            "unverifiedMonths": unverified_months,
        },
        "observedBatch": {
            "postingManifestRows": len(posting_manifest),
            "uniquePostingIds": observed_postings,
            "rawDetailManifestRows": raw_detail_count,
            "rawDetailUniquePostingIds": raw_detail_unique_ids,
            "postingManifestRawOnlyRows": posting_manifest_raw_only,
        },
        "failedGates": gaps,
        "empiricalAnalysisAllowed": full_pass,
    }
