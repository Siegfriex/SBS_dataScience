"""Observed input packaging and guarded crawl-release assembly."""

from __future__ import annotations

import csv
import gzip
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pandas as pd

from .assets import build_asset_frontier
from .config import AGENT_ID, AGENT_NAME, CONTRACT_VERSION, RunConfig, TARGET_MONTHS
from .frontier import build_detail_frontier, persist_frontier
from .manifests import load_jsonl, verify_checksum_file, write_checksums
from .storage import atomic_write_json, sha256_bytes, sha256_file, write_parquet_atomic

OBSERVED_PACKAGE_ID = "OBSERVED_INPUT_20260806_01"
OBSERVED_CREATED_AT = "2026-08-06T17:10:00+09:00"


def _validated_raw_detail_rows(config: RunConfig) -> tuple[list[dict], list[dict]]:
    fetch_rows = load_jsonl(config.release_root / "fetch_manifest.jsonl")
    verified: list[dict] = []
    rejected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source in fetch_rows:
        if source.get("entityType") != "detail":
            continue
        relative = str(source.get("rawPath") or "")
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or posix.parts[:4] != ("data", "raw", "linkareer", "detail"):
            rejected.append({"sourceUrl": source.get("requestUrl"), "rawPath": relative, "reason": "notRealRawDetailPath"})
            continue
        path = config.crawl_root / relative
        if not path.is_file():
            rejected.append({"sourceUrl": source.get("requestUrl"), "rawPath": relative, "reason": "missing"})
            continue
        try:
            body = gzip.open(path, "rb").read()
        except (OSError, EOFError) as exc:
            rejected.append({"sourceUrl": source.get("requestUrl"), "rawPath": relative, "reason": type(exc).__name__})
            continue
        actual = sha256_bytes(body)
        if actual != source.get("contentSha256") or len(body) != int(source.get("bytes") or -1):
            rejected.append({"sourceUrl": source.get("requestUrl"), "rawPath": relative, "reason": "shaOrBytesMismatch"})
            continue
        match = re.search(r"/activity/(\d+)", str(source.get("requestUrl") or ""))
        row = {
            "sourcePostingId": match.group(1) if match else None,
            "sourceUrl": source.get("requestUrl"),
            "rawPath": relative,
            "rawSha256": actual,
            "bytes": len(body),
            "httpStatus": source.get("httpStatus"),
            "fetchedAt": source.get("fetchedAt"),
            "collectorVersion": source.get("collectorVersion"),
        }
        key = (row["sourcePostingId"] or "", relative)
        if key not in seen:
            seen.add(key)
            verified.append(row)
    verified.sort(key=lambda row: (int(row["sourcePostingId"] or 0), row["rawPath"]))
    return verified, rejected


def _ncs_source_rows(config: RunConfig) -> list[dict]:
    rows = load_jsonl(config.release_root / "ncs_manifest.jsonl")
    result = []
    for source in rows:
        row = dict(source)
        for field in ("rawPath", "utf8NormalizedPath"):
            relative = row.get(field)
            if not relative:
                continue
            path = config.release_root / relative
            row[field] = f"releases/{config.crawl_release_id}/{relative}"
            if path.is_file():
                prefix = "raw" if field == "rawPath" else "utf8Normalized"
                row[f"{prefix}Sha256"] = sha256_file(path)
                row[f"{prefix}Bytes"] = path.stat().st_size
        result.append(row)
    return result


def build_observed_input_package(
    config: RunConfig,
    output_root: Path | None = None,
) -> dict:
    """Build a deterministic, reference-only package; never copy raw HTML."""

    if config.run_mode != "observed-dev":
        raise RuntimeError("Observed input package requires runMode=observed-dev")
    release_check = verify_checksum_file(config.release_root / "CHECKSUMS.sha256", config.release_root)
    if not release_check["ok"]:
        raise RuntimeError("Source crawl release checksum failed")
    output_root = output_root or config.crawl_root / "observed_inputs" / OBSERVED_PACKAGE_ID
    output_root.mkdir(parents=True, exist_ok=True)

    posting = pd.read_parquet(config.release_root / "posting_manifest.parquet")
    posting_rows = len(posting)
    posting_ids = posting["sourcePostingId"].astype(str).nunique()
    if posting_rows != posting_ids:
        raise RuntimeError("posting manifest sourcePostingId is not unique")
    raw_rows, rejected_raw = _validated_raw_detail_rows(config)
    asset_rows = len(load_jsonl(config.release_root / "asset_manifest.jsonl"))
    ncs_rows = _ncs_source_rows(config)

    shutil.copyfile(config.release_root / "posting_manifest.parquet", output_root / "posting_manifest.parquet")
    shutil.copyfile(config.release_root / "posting_manifest.csv", output_root / "posting_manifest.csv")
    (output_root / "raw_detail_manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in raw_rows),
        encoding="utf-8",
        newline="\n",
    )
    (output_root / "ncs_source_manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ncs_rows),
        encoding="utf-8",
        newline="\n",
    )
    known_gaps = {
        "fullCorpus": False,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "unverifiedMonthCount": 58,
        "verifiedMonthCount": 21,
        "rawHtmlCoverage": {"postingRows": posting_rows, "rawHtmlRows": len(raw_rows)},
        "assetRows": asset_rows,
        "rejectedNonRawDetailReferences": rejected_raw,
        "notes": [
            "Observed-development input is not the full Linkareer population.",
            "Raw HTML is referenced by crawl-root-relative path and checksum; it is not copied into this package.",
            "Three masked fixture references in the source fetch manifest are excluded from rawHtmlRows.",
            "NCS core code set and mapping remain review-required development inputs.",
        ],
    }
    atomic_write_json(output_root / "known_gaps.json", known_gaps)
    handoff = {
        "agentId": AGENT_ID,
        "agentName": AGENT_NAME,
        "packageId": OBSERVED_PACKAGE_ID,
        "sourceCrawlReleaseId": config.crawl_release_id,
        "crawlReleaseId": config.crawl_release_id,
        "contractVersion": CONTRACT_VERSION,
        "runMode": "observed-dev",
        "dataVersion": config.data_version,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "fullCorpus": False,
        "postingManifestRows": posting_rows,
        "postingRows": posting_rows,
        "rawHtmlRows": len(raw_rows),
        "assetRows": asset_rows,
        "ncsUnitRows": next((row.get("recordCount") for row in ncs_rows if row.get("datasetId") == "15083321"), None),
        "rawCopied": False,
        "createdAt": OBSERVED_CREATED_AT,
        "artifacts": [
            "posting_manifest.parquet",
            "posting_manifest.csv",
            "raw_detail_manifest.jsonl",
            "ncs_source_manifest.jsonl",
            "known_gaps.json",
        ],
    }
    atomic_write_json(output_root / "HANDOFF.json", handoff)
    write_checksums(output_root, handoff["artifacts"] + ["HANDOFF.json"])
    return handoff


def recover_source_state(config: RunConfig) -> dict:
    """Materialize Notebook 00 outputs from the baseline and prior checkpoints."""

    config.ensure_run_layout()
    coverage = pd.read_csv(config.release_root / "monthly_coverage.csv", encoding="utf-8-sig", dtype={"periodMonth": str})
    target = coverage[coverage["periodMonth"].isin(TARGET_MONTHS)].copy()
    remaining = target[target["coverageStatus"].eq("unverified")].copy()
    remaining.to_csv(config.run_root / "state" / "remaining_months.csv", index=False, encoding="utf-8-sig")

    posting = pd.read_parquet(config.release_root / "posting_manifest.parquet")
    raw_rows, rejected = _validated_raw_detail_rows(config)
    raw_by_id = {str(row["sourcePostingId"]): {"contentSha256": row["rawSha256"], **row} for row in raw_rows}
    frontier_path = config.run_root / "state" / "detail_frontier.parquet"
    previous = pd.read_parquet(frontier_path) if frontier_path.exists() else None
    frontier = build_detail_frontier(set(posting["sourcePostingId"].astype(str)), raw_by_id, previous=previous)
    persist_frontier(frontier, frontier_path)

    assets = build_asset_frontier(posting)
    asset_path = config.run_root / "state" / "asset_frontier.parquet"
    if assets.empty:
        assets = pd.DataFrame(columns=["sourcePostingId", "assetUrl", "assetType", "sourceField", "status", "externalAtsAsset"])
    write_parquet_atomic(assets, asset_path)
    assets.to_csv(asset_path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    state = {
        "status": "ONBOARDING_RECOVERED",
        "crawlReleaseId": config.crawl_release_id,
        "contractVersion": config.contract_version,
        "postingRows": len(posting),
        "rawHtmlRows": len(raw_rows),
        "assetRows": 0,
        "completeMonths": int(target["coverageStatus"].eq("complete").sum()),
        "remainingMonths": len(remaining),
        "detailFrontierStates": frontier["status"].value_counts().to_dict(),
        "assetFrontierRows": len(assets),
        "rejectedRawReferences": rejected,
    }
    atomic_write_json(config.run_root / "state" / "resume_state.json", state)
    return state


def crawl_release_readiness(config: RunConfig) -> dict:
    coverage = pd.read_csv(config.release_root / "monthly_coverage.csv", encoding="utf-8-sig")
    unverified = int(coverage["coverageStatus"].eq("unverified").sum())
    raw_rows, rejected = _validated_raw_detail_rows(config)
    blockers = []
    if unverified:
        blockers.append(f"{unverified} months remain unverified")
    if rejected:
        blockers.append(f"{len(rejected)} detail references are not real raw HTML")
    if not load_jsonl(config.release_root / "asset_manifest.jsonl"):
        blockers.append("asset lineage is empty")
    blockers.append("Agent 2 validator has not passed")
    return {
        "crawlReleaseId": config.crawl_release_id,
        "rawHtmlRows": len(raw_rows),
        "unverifiedMonths": unverified,
        "releaseReady": False,
        "status": "PRODUCTION_CRAWL_BLOCKED",
        "blockers": blockers,
    }
