"""Offline observed-development operations used by Agent 1 notebooks."""

from __future__ import annotations

import gzip
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from .apq import APQClient
from .assets import build_asset_frontier
from .detail import extract_detail_record
from .manifests import load_jsonl, verify_checksum_file
from .policy import PolicyHttpClient, RateLimiter, SourcePolicyBlocked
from .query_registry import QueryRegistry
from .storage import atomic_write_json, sha256_bytes, write_parquet_atomic


def _safe_url(url: str | None) -> str | None:
    if not url:
        return url
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def require_repository_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path).startswith("~"):
        raise ValueError(f"repository-relative path required: {value}")
    return path


def audit_input_manifest(project_root: Path, relative_path: str, expected_release_id: str) -> dict:
    relative = require_repository_relative(relative_path)
    path = project_root / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    observed_release = payload.get("crawlReleaseId") or payload.get("crawl_release_id") or payload.get("release_id")
    if observed_release != expected_release_id:
        raise ValueError(f"crawl release mismatch: {observed_release}")
    checksum_path = path.parent / "CHECKSUMS.sha256"
    checksum = verify_checksum_file(checksum_path, path.parent)
    if not checksum["ok"]:
        raise ValueError("input manifest checksum verification failed")
    return {
        "path": relative.as_posix(),
        "crawlReleaseId": observed_release,
        "contractVersion": payload.get("contractVersion") or payload.get("contract_version"),
        "checksumCount": len(checksum["passed"]),
        "checksumPassed": True,
        "sha256": sha256_bytes(path.read_bytes()),
    }


@dataclass
class _FixtureResponse:
    payload: dict
    status_code: int = 200

    @property
    def content(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def json(self) -> dict:
        return self.payload


def run_fixture_apq_query(crawl_root: Path, output_root: Path) -> dict:
    """Exercise registry-owned APQ construction against the committed fixture."""

    fixture_path = crawl_root / "fixtures" / "apq" / "CalendarScreen_ActivityCalendarEntries.2026-03.recruit.sample.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    calls: list[dict] = []

    def transport(url: str, **kwargs):
        calls.append({"url": _safe_url(url), "paramsPresent": bool(kwargs.get("params"))})
        return _FixtureResponse(fixture["responseBody"])

    limiter = RateLimiter(1.0, clock=lambda: 0.0, sleeper=lambda _seconds: None, random_uniform=lambda _a, _b: 0.0)
    http = PolicyHttpClient(transport, concurrency=1, limiter=limiter)
    registry = QueryRegistry.load(crawl_root / "configs" / "queryRegistry.yaml")
    operation = fixture["operationName"]
    result = APQClient(http, registry).fetch(operation, fixture["requestVariables"])
    nodes = result.payload["data"]["activityCalendarEntries"]["nodes"]
    rows = []
    for day in nodes:
        for side in ("start", "end"):
            for posting in (day.get(side) or {}).get("nodes", []):
                rows.append({
                    "sourcePostingId": str(posting["id"]),
                    "activityTypeId": int(posting.get("activityTypeID") or 5),
                    "discoverySide": side,
                    "fixturePeriod": "2026-03",
                    "queryHash": result.query_hash,
                })
    discovery = pd.DataFrame(rows).drop_duplicates(["sourcePostingId", "discoverySide"])
    output_root.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(discovery, output_root / "posting_discovery_index.parquet")
    discovery.to_csv(output_root / "posting_discovery_index.csv", index=False, encoding="utf-8-sig")
    audit = {
        "mode": "DRY_RUN_FIXTURE",
        "operationName": operation,
        "queryHash": result.query_hash,
        "transportCalls": len(calls),
        "networkCalls": 0,
        "fixtureDays": len(nodes),
        "discoveryRelations": len(discovery),
        "distinctPostingIds": int(discovery["sourcePostingId"].nunique()),
    }
    atomic_write_json(output_root / "fixture_apq_audit.json", audit)
    return audit


def replay_observed_raw(project_root: Path, observed_root: Path, output_root: Path) -> dict:
    """Parse all verified local raw SSR rows without persisting ActivityText or PII."""

    raw_rows = load_jsonl(observed_root / "raw_detail_manifest.jsonl")
    records = []
    failures = []
    for lineage in raw_rows:
        raw_path = require_repository_relative(lineage["rawPath"])
        path = project_root / "crawl" / raw_path
        try:
            body = gzip.open(path, "rb").read()
            if sha256_bytes(body) != lineage["rawSha256"] or len(body) != int(lineage["bytes"]):
                raise ValueError("raw SHA or bytes mismatch")
            normalized_lineage = {**lineage, "contentSha256": lineage["rawSha256"]}
            record, candidates = extract_detail_record(str(lineage["sourcePostingId"]), body, normalized_lineage)
            record["sourceUrl"] = _safe_url(record.get("sourceUrl"))
            record["externalApplyUrl"] = _safe_url(record.get("externalApplyUrl"))
            record["assetCandidatesJson"] = json.dumps(
                [{**candidate, "assetUrl": _safe_url(candidate.get("assetUrl"))} for candidate in candidates],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            records.append(record)
        except Exception as exc:
            failures.append({"sourcePostingId": lineage.get("sourcePostingId"), "error": f"{type(exc).__name__}: {exc}"})
    output_root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(records).sort_values("sourcePostingId") if records else pd.DataFrame()
    write_parquet_atomic(frame, output_root / "posting_detail_replay.parquet")
    frame.to_csv(output_root / "posting_detail_replay.csv", index=False, encoding="utf-8-sig")
    atomic_write_json(output_root / "raw_replay_failures.json", failures)
    metrics = {
        "rawManifestRows": len(raw_rows),
        "rawReplayPassed": len(records),
        "rawReplayFailed": len(failures),
        "activityTextRecovered": int(frame.get("activityTextAvailable", pd.Series(dtype=bool)).fillna(False).sum()) if not frame.empty else 0,
        "assetCandidateRows": int(frame.get("assetCandidateCount", pd.Series(dtype=int)).fillna(0).sum()) if not frame.empty else 0,
        "rawBodyPersisted": False,
        "managerPiiPersisted": False,
    }
    atomic_write_json(output_root / "raw_replay_metrics.json", metrics)
    return metrics


def route_observed_asset_metadata(detail_replay_path: Path, output_root: Path) -> dict:
    """Route Linkareer-hosted metadata only and prove external ATS zero-call."""

    posting = pd.read_parquet(detail_replay_path)
    candidates = build_asset_frontier(posting)
    if candidates.empty:
        candidates = pd.DataFrame(columns=["sourcePostingId", "assetUrl", "assetType", "sourceField", "status", "externalAtsAsset"])
    else:
        candidates["assetUrl"] = candidates["assetUrl"].map(_safe_url)
    output_root.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(candidates, output_root / "asset_frontier.parquet")
    candidates.to_csv(output_root / "asset_frontier.csv", index=False, encoding="utf-8-sig")
    ocr = candidates[candidates["assetType"].astype(str).str.contains("image", case=False, na=False)].copy()
    write_parquet_atomic(ocr, output_root / "ocr_candidate_manifest.parquet")
    ocr.to_csv(output_root / "ocr_candidate_manifest.csv", index=False, encoding="utf-8-sig")
    (output_root / "asset_manifest.jsonl").write_text("", encoding="utf-8")
    transport_calls = 0

    def forbidden_transport(_url: str, **_kwargs):
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("external ATS transport must never be called")

    try:
        PolicyHttpClient(forbidden_transport).get("https://jobs.example.invalid/posting/1")
    except SourcePolicyBlocked:
        pass
    metrics = {
        "metadataCandidates": len(candidates),
        "ocrCandidates": len(ocr),
        "assetsFetched": 0,
        "externalAtsTransportCalls": transport_calls,
        "routingMode": "METADATA_ONLY",
    }
    atomic_write_json(output_root / "asset_routing_metrics.json", metrics)
    return metrics


def validate_observed_package(observed_root: Path) -> dict:
    handoff = json.loads((observed_root / "HANDOFF.json").read_text(encoding="utf-8"))
    checksum = verify_checksum_file(observed_root / "CHECKSUMS.sha256", observed_root)
    raw_rows = load_jsonl(observed_root / "raw_detail_manifest.jsonl")
    return {
        "checksumPassed": bool(checksum["ok"]),
        "checksumCount": len(checksum["passed"]),
        "postingRows": int(handoff["postingRows"]),
        "rawHtmlRows": len(raw_rows),
        "assetRows": int(handoff["assetRows"]),
        "ncsUnitRows": int(handoff["ncsUnitRows"]),
        "rawCopied": bool(handoff["rawCopied"]),
        "fullCorpus": bool(handoff["fullCorpus"]),
        "empiricalAnalysisAllowed": bool(handoff["empiricalAnalysisAllowed"]),
        "promotionAllowed": bool(handoff["promotionAllowed"]),
        "observedInputReady": bool(checksum["ok"] and len(raw_rows) == 29 and not handoff["fullCorpus"]),
    }


def invoke_agent2_validator(project_root: Path, release_handoff: Path) -> dict:
    """Call Agent 2's validator when integrated; never infer release readiness."""

    pipeline_src = project_root / "pipeline" / "src"
    if not (pipeline_src / "p4" / "contracts" / "release_validation.py").is_file():
        return {
            "validator": "p4.contracts.release_validation.validate_release_gates",
            "status": "NOT_AVAILABLE_IN_AGENT1_BRANCH",
            "executed": False,
            "crawlReleaseReady": False,
        }
    sys.path.insert(0, str(pipeline_src))
    try:
        module = importlib.import_module("p4.contracts.release_validation")
        validation = module.validate_release_gates(release_handoff, expected_contract_version="2.1.2")
        return {
            "validator": "p4.contracts.release_validation.validate_release_gates",
            "status": "EXECUTED",
            "executed": True,
            "crawlReleaseReady": bool(validation.get("fullCorpusAcceptance", {}).get("status") == "PASS"),
            "validation": validation,
        }
    except Exception as exc:
        return {
            "validator": "p4.contracts.release_validation.validate_release_gates",
            "status": "EXECUTION_FAILED",
            "executed": True,
            "crawlReleaseReady": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
