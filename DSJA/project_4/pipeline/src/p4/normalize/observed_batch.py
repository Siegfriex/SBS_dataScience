from __future__ import annotations

import gzip
import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from p4.common.hashing import canonical_json_sha256
from p4.common.keys import make_company_key, make_posting_id, make_raw_posting_id, make_section_id, make_track_id
from p4.common.manifest_cursor import advance_cursor, should_process_raw
from p4.normalize.linkareer import adapt_linkareer_source
from p4.parse.linkareer_apollo_cache import extract_activity, find_apollo_cache
from p4.parse.linkareer_next_data import extract_next_data, extract_page_props
from p4.parse.requirements import extract_requirements
from p4.source_blocks.build import build_source_block_bundle
from p4.chunking.semantic import build_semantic_chunk_bundle
from p4.normalize.semantic_recovery import (
    POSTING_KIND_ENUM,
    SEMANTIC_RECOVERY_VERSION,
    canonical_posting_kind,
    recover_authoritative_posted_at,
)


PARSE_VERSION = "observed-dev-parse-20260806.1"
CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_VERSION = "observed-dev-20260806.1"
DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"


def _bool(value: Any) -> bool:
    return False if pd.isna(value) else bool(value)


def _source_id(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _raw_detail_rows(release_root: Path, crawl_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    manifest_path = (
        release_root / "raw_detail_manifest.jsonl"
        if (release_root / "raw_detail_manifest.jsonl").is_file()
        else release_root / "fetch_manifest.jsonl"
    )
    for offset, source_row in enumerate(_read_jsonl(manifest_path)):
        row = dict(source_row)
        if manifest_path.name == "raw_detail_manifest.jsonl":
            row.setdefault("entityType", "detail")
            row.setdefault("requestUrl", row.get("sourceUrl"))
            row.setdefault("contentSha256", row.get("rawSha256"))
        if str(row.get("entityType")).casefold() != "detail":
            continue
        raw_path = crawl_root / str(row.get("rawPath"))
        if not raw_path.is_file():
            continue
        source_id = _source_id(str(row["requestUrl"]))
        with gzip.open(raw_path, "rb") as stream:
            content = stream.read()
        digest = sha256(content).hexdigest()
        if digest != row.get("contentSha256"):
            raise ValueError(f"decompressed raw SHA mismatch: {raw_path}")
        result[source_id] = {**row, "manifestOffset": offset, "absoluteRawPath": str(raw_path), "content": content}
    return result


def _track_type(resolved: list[str]) -> str:
    return resolved[0] if len(resolved) == 1 and resolved[0] in {"entry", "intern", "experienced"} else (
        "mixedUnresolved" if len(resolved) > 1 else "unknown"
    )


def _sections(track_id: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for block in blocks:
        if block["headingCandidate"] or not block["text"]:
            continue
        section_type = block["sectionAssignment"]
        boundary = bool(block["boundaryResolvedFlag"])
        if groups and groups[-1]["sectionType"] == section_type and groups[-1]["boundaryResolvedFlag"] == boundary:
            if block["text"] not in groups[-1]["parts"]:
                groups[-1]["parts"].append(block["text"])
        else:
            groups.append({"sectionType": section_type, "boundaryResolvedFlag": boundary, "parts": [block["text"]]})
    return [
        {
            "sectionId": make_section_id(track_id, ordinal),
            "trackId": track_id,
            "sectionType": group["sectionType"],
            "sectionOrdinal": ordinal,
            "sectionText": "\n".join(group["parts"]),
            "boundaryResolvedFlag": group["boundaryResolvedFlag"],
            "sourceMode": "SSR_ACTIVITY_TEXT",
            "sectionConfidence": 1.0 if group["boundaryResolvedFlag"] else 0.5,
        }
        for ordinal, group in enumerate(groups)
    ]


def build_observed_batch(release_root: str | Path, crawl_root: str | Path) -> dict[str, Any]:
    release_root = Path(release_root)
    crawl_root = Path(crawl_root)
    manifest = pd.read_parquet(release_root / "posting_manifest.parquet")
    sample_path = release_root / "stratified_detail_sample_n126.json"
    sample_rows = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.is_file() else []
    samples = {str(row["id"]): row for row in sample_rows}
    raw_details = _raw_detail_rows(release_root, crawl_root)

    raw_rows: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    posting_semantics: list[dict[str, Any]] = []
    tracks: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    requirements: list[dict[str, Any]] = []
    eligibility: list[dict[str, Any]] = []
    ocr_queue: list[dict[str, Any]] = []
    cursors: list[dict[str, Any]] = []
    parse_failures: list[dict[str, str]] = []
    activity_recovered = 0

    for manifest_row in manifest.to_dict(orient="records"):
        source_id = str(manifest_row["sourcePostingId"])
        sample = samples.get(source_id, {})
        raw = raw_details.get(source_id)
        source_url = f"https://linkareer.com/activity/{source_id}"
        input_sha = str(raw["contentSha256"]) if raw else canonical_json_sha256(sample or manifest_row)
        input_mode = "SSR_RAW_HTML" if raw else "DERIVED_OBSERVED_RECORD"
        raw_posting_id = make_raw_posting_id("linkareer", source_id, input_sha)
        posting_id = make_posting_id("linkareer", source_id)
        detail: dict[str, Any] = {}
        activity: dict[str, Any] = {}
        adapted: dict[str, Any] = {}
        if raw:
            try:
                next_data = extract_next_data(raw["content"].decode("utf-8"))
                cache = find_apollo_cache(extract_page_props(next_data))
                detail = extract_activity(cache, source_id)
                activity = detail["activity"]
                index = {
                    "id": source_id,
                    "title": activity.get("title"),
                    "organizationName": activity.get("organizationName"),
                    "activityTypeId": activity.get("activityTypeID"),
                    "group": activity.get("group"),
                    "createdAt": activity.get("createdAt"),
                    "recruitStartAt": activity.get("recruitStartAt"),
                    "jobTypes": activity.get("jobTypes") or [],
                }
                adapted = adapt_linkareer_source(index, detail)
                activity_recovered += int(adapted["activityTextAvailableFlag"])
                cursors.append(advance_cursor(raw["manifestOffset"], input_sha, "CRAWL_20260806_03", PARSE_VERSION).as_dict())
            except Exception as exc:  # preserve every real input and report the exact failed ID
                parse_failures.append({"sourcePostingId": source_id, "error": f"{type(exc).__name__}: {exc}"})

        title = str(activity.get("title") or sample.get("title") or "")
        company = str(activity.get("organizationName") or "")
        job_types = adapted.get("resolvedJobTypes") or [
            item.casefold().replace("new", "entry")
            for item in str(manifest_row.get("jobTypes") or "").split("|")
            if item and item.casefold() in {"new", "intern", "experienced"}
        ]
        job_types = sorted(set(job_types))
        timestamp = recover_authoritative_posted_at(activity)
        posting_kind = canonical_posting_kind(
            job_types=job_types,
            activity_type_id=activity.get("activityTypeID", 5),
            activity_group=activity.get("group", "recruit"),
        )
        if posting_kind not in POSTING_KIND_ENUM:
            raise ValueError(f"invalid deterministic postingKind: {posting_kind}")
        company_key = make_company_key(company) if company.strip() else None
        posting_semantics.append(
            {
                "sourcePostingId": source_id,
                "canonicalPostedAt": timestamp.canonical_posted_at,
                "periodMonth": timestamp.period_month,
                "canonicalPostedAtAuthoritySource": timestamp.source_field,
                "canonicalPostedAtNullReason": None if timestamp.canonical_posted_at else "RAW_AUTHORITY_UNAVAILABLE",
                "canonicalPostedAtValidationStatus": "VALIDATED" if timestamp.canonical_posted_at else "UNRESOLVED",
                "companyKey": company_key,
                "companyKeyAuthoritySource": "SSR_ACTIVITY.organizationName" if company_key else None,
                "companyKeyNullReason": None if company_key else "COMPANY_NAME_UNAVAILABLE",
                "companyKeyValidationStatus": "VALIDATED" if company_key else "UNRESOLVED",
                "postingKind": posting_kind,
                "postingKindAuthoritySource": "jobTypes+activityTypeID+group",
                "postingKindNullReason": None,
                "postingKindValidationStatus": "VALIDATED",
                "inputArtifactSha256": input_sha,
                "semanticRecoveryVersion": SEMANTIC_RECOVERY_VERSION,
                "dataProvenance": DATA_PROVENANCE,
            }
        )
        raw_rows.append(
            {
                "rawPostingId": raw_posting_id,
                "sourcePostingId": source_id,
                "sourceUrl": source_url,
                "inputSha256": input_sha,
                "inputMode": input_mode,
                "rawPath": str(raw.get("rawPath")) if raw else None,
                "manifestOffset": raw.get("manifestOffset") if raw else None,
                "parseStatus": "SUCCESS" if raw is None or not any(item["sourcePostingId"] == source_id for item in parse_failures) else "FAIL",
            }
        )
        observed_flags = {
            "postingEligibleFlag": bool(
                _bool(manifest_row.get("rq1EligibleFlag"))
                or _bool(manifest_row.get("rq2EligibleFlag"))
                or _bool(manifest_row.get("ncsEligibleFlag"))
            ),
            "rq1EligibleFlag": _bool(manifest_row.get("rq1EligibleFlag")),
            "rq2EligibleFlag": _bool(manifest_row.get("rq2EligibleFlag")),
            "ncsEligibleFlag": _bool(manifest_row.get("ncsEligibleFlag")),
        }
        flags = {key: bool(adapted.get(key, value)) for key, value in observed_flags.items()} if adapted else observed_flags
        body_text = "\n".join(
            block["text"] for block in adapted.get("activityTextBlocks", []) if not block["headingCandidate"]
        )
        normalized_row = {
            "postingId": posting_id,
            "rawPostingId": raw_posting_id,
            "sourcePostingId": source_id,
            "sourceUrl": source_url,
            "titleText": title or None,
            "companyName": company or None,
            "bodyText": body_text or None,
            "activityTypeId": activity.get("activityTypeID", 5),
            "jobTypesRawJson": json.dumps(activity.get("jobTypes") or str(manifest_row.get("jobTypes") or "").split("|"), ensure_ascii=False),
            "resolvedJobTypesJson": json.dumps(job_types, ensure_ascii=False),
            "activityTextAvailableFlag": bool(adapted.get("activityTextAvailableFlag", _bool(manifest_row.get("activityTextAvailable")))),
            "externalApplyFlag": bool(adapted.get("externalApplyFlag", _bool(manifest_row.get("externalApplyFlag")))),
            "externalDetailOnlyFlag": bool(adapted.get("externalDetailOnlyFlag", _bool(manifest_row.get("externalDetailOnlyFlag")))),
            "jobTypeConflictFlag": bool(adapted.get("jobTypeConflictFlag", sample.get("jobTypeConflictFlag", False))),
            **flags,
            "eligibilitySource": "AGENT2_SSR_PARSE" if adapted else "AGENT1_DERIVED_OBSERVED",
            "inputSha256": input_sha,
            "parseVersion": PARSE_VERSION,
            "dataVersion": DATA_VERSION,
            "contractVersion": CONTRACT_VERSION,
            "crawlReleaseId": CRAWL_RELEASE_ID,
            "dataProvenance": DATA_PROVENANCE,
            "empiricalAnalysisAllowed": False,
            "promotionAllowed": False,
        }
        normalized.append(normalized_row)
        track_id = make_track_id(posting_id, 0)
        track = {
            "trackId": track_id,
            "postingId": posting_id,
            "trackType": _track_type(job_types),
            "trackOrdinal": 0,
            "mixedResolvedFlag": len(job_types) == 1,
            "jobCode": None,
            "inputSha256": input_sha,
        }
        tracks.append(track)
        current_sections = _sections(track_id, adapted.get("activityTextBlocks", []))
        sections.extend(current_sections)
        for section in current_sections:
            if section["sectionType"] in {"required", "preferred"}:
                requirements.extend(extract_requirements(section))
        eligibility.append(
            {
                "trackId": track_id,
                "postingId": posting_id,
                **flags,
                "eligibilitySource": normalized_row["eligibilitySource"],
                "dataVersion": DATA_VERSION,
                "contractVersion": CONTRACT_VERSION,
                "crawlReleaseId": CRAWL_RELEASE_ID,
                "dataProvenance": DATA_PROVENANCE,
                "empiricalAnalysisAllowed": False,
                "promotionAllowed": False,
            }
        )
        for candidate in adapted.get("ocrQueue", []):
            ocr_queue.append(
                {
                    "sourcePostingId": source_id,
                    "rawPostingId": raw_posting_id,
                    "assetUrl": candidate["assetUrl"],
                    "assetType": candidate["assetType"],
                    "queueStatus": "ASSET_NOT_FETCHED",
                    "routingReason": candidate["routingReason"],
                    "observedTextChars": candidate["observedTextChars"],
                    "inputSha256": input_sha,
                    "crawlReleaseId": "CRAWL_20260806_03",
                    "parseVersion": PARSE_VERSION,
                }
            )

    frames = {
        "raw_posting": pd.DataFrame(raw_rows),
        "posting_normalized": pd.DataFrame(normalized),
        "posting_semantics": pd.DataFrame(posting_semantics),
        "posting_track": pd.DataFrame(tracks),
        "posting_section": pd.DataFrame(sections),
        "requirement_fact": pd.DataFrame(requirements),
        "eligibility": pd.DataFrame(eligibility),
        "ocr_queue": pd.DataFrame(ocr_queue),
        "manifest_cursor": pd.DataFrame(cursors),
    }
    source_blocks, section_source_blocks = build_source_block_bundle(
        frames["posting_normalized"], frames["posting_track"], frames["posting_section"]
    )
    semantic_chunks, chunk_roles = build_semantic_chunk_bundle(
        frames["posting_section"], section_source_blocks
    )
    if len(frames["requirement_fact"]):
        frames["requirement_fact"] = frames["requirement_fact"].merge(
            section_source_blocks, on="sectionId", how="left", validate="many_to_one"
        )
        if frames["requirement_fact"]["sourceBlockId"].isna().any():
            raise ValueError("every requirement fact requires sourceBlock lineage")
    frames.update(
        {
            "source_block": source_blocks,
            "section_source_block": section_source_blocks,
            "semantic_chunk": semantic_chunks,
            "chunk_role": chunk_roles,
        }
    )
    metrics = {
        "inputPostings": len(manifest),
        "parseSuccess": len(manifest) - len(parse_failures),
        "parseFailure": len(parse_failures),
        "realSsrRaw": len(raw_details),
        "realSsrParseSuccess": len(raw_details) - len(parse_failures),
        "derivedObservedAccepted": len(manifest) - len(raw_details),
        "activityTextRecovered": activity_recovered,
        "embeddedImageRouted": len(ocr_queue),
        "trackCount": len(tracks),
        "trackSplitSuccess": sum(row["trackType"] not in {"unknown", "mixedUnresolved"} for row in tracks),
        "mixedUnresolved": sum(row["trackType"] == "mixedUnresolved" for row in tracks),
        "unknownTrack": sum(row["trackType"] == "unknown" for row in tracks),
        "sectionCount": len(sections),
        "requirementCount": len(requirements),
        "boundaryResolvedSections": sum(row["boundaryResolvedFlag"] for row in sections),
        "requiredPreferredSections": sum(row["sectionType"] in {"required", "preferred"} for row in sections),
        "requiredPreferredBoundaryResolved": sum(
            row["sectionType"] in {"required", "preferred"} and row["boundaryResolvedFlag"] for row in sections
        ),
        "rq1Eligible": sum(row["rq1EligibleFlag"] for row in eligibility),
        "rq2Eligible": sum(row["rq2EligibleFlag"] for row in eligibility),
        "ncsEligible": sum(row["ncsEligibleFlag"] for row in eligibility),
        "ocrQueueRows": len(ocr_queue),
        "ocrAssetsFetched": 0,
        "ocrBenchmarkEligible": False,
        "sourceBlockCount": len(source_blocks),
        "semanticChunkCount": len(semantic_chunks),
        "requirementSourceBlockCoverage": int(frames["requirement_fact"]["sourceBlockId"].notna().sum()),
    }
    return {"frames": frames, "metrics": metrics, "parseFailures": parse_failures}


def deterministic_dev_samples(frames: dict[str, pd.DataFrame], limit: int = 50) -> dict[str, pd.DataFrame]:
    normalized = frames["posting_normalized"].copy()
    tracks = frames["posting_track"].copy()
    sections = frames["posting_section"].copy()
    tasks = {
        "postingKind_dev": normalized[["postingId", "sourcePostingId", "titleText", "inputSha256"]],
        "trackSplit_dev": tracks.merge(normalized[["postingId", "sourcePostingId", "titleText"]], on="postingId", how="left"),
        "boundary_dev": sections.merge(tracks[["trackId", "postingId"]], on="trackId", how="left"),
        "careerClass_dev": tracks.merge(normalized[["postingId", "sourcePostingId", "titleText"]], on="postingId", how="left"),
        "internAccess_dev": tracks.merge(normalized[["postingId", "sourcePostingId", "titleText"]], on="postingId", how="left"),
    }
    result: dict[str, pd.DataFrame] = {}
    for name, frame in tasks.items():
        if frame.empty:
            result[name] = frame.assign(samplePurpose=pd.Series(dtype="string"), reviewLabel=pd.Series(dtype="string"))
            continue
        order_key = frame.apply(
            lambda row: sha256("|".join(map(str, row.tolist())).encode()).hexdigest(), axis=1
        )
        sampled = frame.assign(_order=order_key).sort_values("_order").head(limit).drop(columns="_order")
        result[name] = sampled.assign(samplePurpose="DEV_RULE_IMPROVEMENT_ONLY", reviewLabel=None)
    return result
