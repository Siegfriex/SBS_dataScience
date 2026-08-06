#!/usr/bin/env python3
"""Strict, current-run-bound validator for the unified P4 reconciliation."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pandas.testing import assert_frame_equal


EXPECTED_STAGES = 23
POSTING_KIND_ENUM = {"recruitIntern", "recruitNewGrad", "recruitExperienced", "recruitUnknown", "contest", "extracurricular", "education", "club", "volunteer", "other"}
SHA = re.compile(r"^[0-9a-f]{64}$")
SECRET = re.compile(r"(?i)(api[_-]?key|access[_-]?token|session[_-]?cookie|authorization)\s*[:=]\s*[^,;\s]{8,}")
ABSOLUTE = re.compile(r"/(?:home|mnt|Users)/[^\s\"']+")


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result:
        result[column] = result[column].map(lambda value: "<NULL>" if pd.isna(value) else str(value).casefold() if str(value).casefold() in {"true", "false"} else str(value))
    return result.reset_index(drop=True)


def add(checks: list[dict[str, Any]], check_id: str, passed: bool, observed: Any, threshold: Any, evidence: str) -> None:
    checks.append({"checkId": check_id, "status": "PASS" if passed else "FAIL", "observed": observed, "threshold": threshold, "evidence": evidence})


def validate_raw(project: Path, raw_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(project / "crawl/src"))
    from p4_crawl.raw_authority import (
        AVAILABLE, COMPRESSED_SHA_MISMATCH, RAW_ROOT_UNMOUNTED,
        load_jsonl, validate_manifest_against_mount,
    )
    manifest_path = project / "crawl/reports/reconciliation_a1/A1_RAW_OBJECT_MANIFEST.jsonl"
    rows = load_jsonl(manifest_path)
    mounted = validate_manifest_against_mount(rows, raw_root)
    unmounted = validate_manifest_against_mount(rows, None)
    tampered = [dict(row) for row in rows]
    tampered[0]["compressedSha256"] = "0" * 64
    wrong = validate_manifest_against_mount(tampered[:1], raw_root)
    return {
        "manifestRows": len(rows), "mountedAvailable": sum(row["availabilityStatus"] == AVAILABLE for row in mounted),
        "unmountedFailClosed": all(row["availabilityStatus"] == RAW_ROOT_UNMOUNTED and not row["downstreamConsumable"] for row in unmounted),
        "wrongShaQuarantined": wrong[0]["availabilityStatus"] == COMPRESSED_SHA_MISMATCH and not wrong[0]["downstreamConsumable"],
        "storageRootIds": sorted({row["storageRootId"] for row in rows}), "manifestSha256": sha_file(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve(); report = args.report_root.resolve()
    export_root = args.export_root.resolve(); database = args.database.resolve()
    checks: list[dict[str, Any]] = []

    stage_dirs = sorted(path for path in (report / "stages").iterdir() if path.is_dir())
    manifests: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for stage_dir in stage_dirs:
        manifest_files = list(stage_dir.glob("stage_manifest.json"))
        exact = len(manifest_files) == 1
        payload = json.loads(manifest_files[0].read_text(encoding="utf-8")) if exact else {}
        checksum_ok = True
        declared: set[str] = set()
        for line in (stage_dir / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
            expected, name = line.split(maxsplit=1); name = name.strip(); declared.add(name)
            checksum_ok &= (stage_dir / name).is_file() and sha_file(stage_dir / name) == expected
        source = project / str(payload.get("sourceNotebookPath", ""))
        source_match = source.is_file() and sha_file(source) == payload.get("sourceNotebookSha256")
        run_match = payload.get("runId") == args.run_id and payload.get("dataVersion") == args.data_version
        sha_fields = all(SHA.fullmatch(str(payload.get(key, ""))) for key in ("inputManifestSha256", "sourceNotebookSha256", "moduleBlobSha256", "parameterSha256", "outputManifestSha256"))
        network_zero = payload.get("productionNetworkCalls") == 0 and payload.get("externalAtsTransportCalls") == 0 and payload.get("credentialedApiCalls") == 0
        row = {
            "stageId": stage_dir.name, "runId": payload.get("runId"), "manifestCount": len(manifest_files),
            "exactOne": exact, "checksumPass": checksum_ok and declared == {"stage_manifest.json", "stage_metrics.json", "stage_quality.csv"},
            "sourceNotebookMatch": source_match, "runBindingMatch": run_match, "shaFieldsValid": sha_fields,
            "staleConsumed": 0 if run_match else 1, "foreignArtifactConsumed": 0 if source_match else 1,
            "status": payload.get("status"), "productionNetworkCalls": payload.get("productionNetworkCalls"),
            "externalAtsTransportCalls": payload.get("externalAtsTransportCalls"),
        }
        row["auditStatus"] = "PASS" if all((row["exactOne"], row["checksumPass"], source_match, run_match, sha_fields, network_zero)) else "FAIL"
        audit_rows.append(row); manifests.append(payload)
    add(checks, "CURRENT_RUN_EXACT_ONE", len(stage_dirs) == EXPECTED_STAGES and all(row["auditStatus"] == "PASS" for row in audit_rows), len(audit_rows), 23, "P4_CURRENT_RUN_MANIFEST_AUDIT.csv")
    with (report / "P4_CURRENT_RUN_MANIFEST_AUDIT.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit_rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(audit_rows)

    pairs = sorted(path.stem for path in export_root.glob("*.parquet") if (export_root / f"{path.stem}.csv").is_file())
    pair_failures: list[str] = []
    export_frames: dict[str, pd.DataFrame] = {}
    for stem in pairs:
        parquet = pd.read_parquet(export_root / f"{stem}.parquet")
        csv_frame = pd.read_csv(export_root / f"{stem}.csv", dtype=object, keep_default_na=True)
        try:
            assert_frame_equal(semantic(parquet), semantic(csv_frame), check_dtype=False)
        except AssertionError:
            pair_failures.append(stem)
        export_frames[stem] = parquet
    add(checks, "CSV_PARQUET_EQUALITY", not pair_failures and len(pairs) == 13, {"pairs": len(pairs), "failures": pair_failures}, {"pairs": 13, "failures": 0}, "pipeline_export")

    sys.path[:0] = [str(project / "pipeline/src"), str(project / "ncs_mapping/src")]
    from p4.export.observed import build_export_frames
    from p4.notebooks.observed_stages import _load_frames
    source_frames = _load_frames(database)
    candidates = source_frames.pop("posting_ncs_candidates", None)
    matches = source_frames.pop("posting_ncs_matches", None)
    mapping_to_mart = source_frames.pop("ncs_mapping_to_mart", None)
    rebuilt = build_export_frames(source_frames, candidates, matches, mapping_to_mart)
    db_mismatch: list[str] = []
    for name, expected in rebuilt.items():
        try:
            assert_frame_equal(semantic(expected), semantic(export_frames[name]), check_dtype=False)
        except (AssertionError, KeyError):
            db_mismatch.append(name)
    add(checks, "DUCKDB_PARQUET_EQUALITY", not db_mismatch and len(rebuilt) == 13, db_mismatch, [], str(database.name))

    normalized = export_frames["posting_normalized"]; tracks = export_frames["posting_tracks"]
    sections = export_frames["posting_sections"]; requirements = export_frames["requirement_facts"]
    final = export_frames["preprocessed_posting_tracks"]; source_blocks = export_frames["source_blocks"]
    chunks = export_frames["semantic_chunks"]; roles = export_frames["chunk_roles"]
    mart = export_frames["ncs_mapping_to_mart"]
    pk_duplicates = {
        "postingId": int(normalized.postingId.duplicated().sum()), "trackId": int(tracks.trackId.duplicated().sum()),
        "sectionId": int(sections.sectionId.duplicated().sum()), "requirementId": int(requirements.requirementId.duplicated().sum()),
        "sourceBlockId": int(source_blocks.sourceBlockId.duplicated().sum()), "chunkId": int(chunks.chunkId.duplicated().sum()),
    }
    fk_orphans = {
        "trackPosting": int((~tracks.postingId.isin(normalized.postingId)).sum()),
        "sectionTrack": int((~sections.trackId.isin(tracks.trackId)).sum()),
        "requirementSection": int((~requirements.sectionId.isin(sections.sectionId)).sum()),
        "requirementSourceBlock": int((~requirements.sourceBlockId.isin(source_blocks.sourceBlockId)).sum()),
        "chunkSourceBlock": int((~chunks.sourceBlockId.isin(source_blocks.sourceBlockId)).sum()),
        "roleChunk": int((~roles.chunkId.isin(chunks.chunkId)).sum()),
        "martTrack": int((~mart.trackId.isin(tracks.trackId)).sum()),
    }
    add(checks, "PK_FK_ORPHAN_DUPLICATE", not any(pk_duplicates.values()) and not any(fk_orphans.values()), {"pk": pk_duplicates, "fk": fk_orphans}, 0, "pipeline_export")
    add(checks, "SOURCEBLOCK_REQUIREMENT_LINEAGE", requirements.sourceBlockId.notna().all() and requirements.sourceBlockId.isin(source_blocks.sourceBlockId).all(), int(requirements.sourceBlockId.notna().sum()), len(requirements), "requirement_facts.parquet")

    invalid_kind = int((~final.postingKind.isin(POSTING_KIND_ENUM)).sum())
    expected_period = pd.to_datetime(final.canonicalPostedAt, errors="coerce").dt.strftime("%Y-%m")
    actual_period = final.periodMonth.astype("string").str.slice(0, 7)
    period_mismatch = int(((expected_period.notna()) & expected_period.ne(actual_period)).sum())
    add(checks, "CANONICAL_POSTING_KIND", invalid_kind == 0, invalid_kind, 0, "preprocessed_posting_tracks.parquet")
    add(checks, "PERIOD_MONTH_DETERMINISTIC", period_mismatch == 0, period_mismatch, 0, "preprocessed_posting_tracks.parquet")
    add(checks, "TIME_ENTITY_FAIL_CLOSED", int(normalized.canonicalPostedAt.notna().sum()) == 29 and int(normalized.companyKey.notna().sum()) == 29 and normalized.loc[normalized.canonicalPostedAt.isna(), "canonicalPostedAtNullReason"].eq("RAW_AUTHORITY_UNAVAILABLE").all() and normalized.loc[normalized.companyKey.isna(), "companyKeyNullReason"].eq("COMPANY_NAME_UNAVAILABLE").all(), {"postedAt": int(normalized.canonicalPostedAt.notna().sum()), "periodMonth": int(normalized.periodMonth.notna().sum()), "companyKey": int(normalized.companyKey.notna().sum()), "unresolved": int(normalized.canonicalPostedAt.isna().sum())}, "29 authoritative plus 108 explicit unresolved", "posting_normalized.parquet")
    add(checks, "HIGH_DEMAND_NULL", int(final.highDemandScore.notna().sum()) == 0, int(final.highDemandScore.notna().sum()), 0, "preprocessed_posting_tracks.parquet")

    raw = validate_raw(project, args.raw_root.resolve())
    add(checks, "RAW_MOUNT_CONTRACT", raw["manifestRows"] == 29 and raw["mountedAvailable"] == 29 and raw["unmountedFailClosed"] and raw["wrongShaQuarantined"], raw, {"mounted": 29, "unmounted": "fail-closed", "wrongSha": "quarantine"}, "A1_RAW_OBJECT_MANIFEST.jsonl")
    binding = pd.read_csv(project / "crawl/reports/reconciliation_a1/A1_RAW_POSTING_BINDING_AUDIT.csv")
    binding_counts = binding.bindingStatus.value_counts().to_dict()
    add(checks, "RAW_POSTING_BINDING", binding_counts.get("MATCHED", 0) == 11 and binding_counts.get("QUARANTINED", 0) == 18, binding_counts, {"MATCHED": 11, "QUARANTINED": 18}, "A1_RAW_POSTING_BINDING_AUDIT.csv")

    with duckdb.connect(str(database), read_only=True) as con:
        foreign_schemas = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw','core','ncs','mart','qa')").fetchone()[0]
        observed_rows = con.execute("SELECT COUNT(*) FROM observed.posting_normalized").fetchone()[0]
    add(checks, "OBSERVED_PRODUCTION_CONTAMINATION", foreign_schemas == 0 and observed_rows == 137 and database.name == "p4.observed-dev.duckdb", {"foreignCanonicalObjects": foreign_schemas, "observedRows": observed_rows, "database": database.name}, {"foreign": 0, "rows": 137}, database.name)
    canonical_db = project / "pipeline/data/warehouse/p4.duckdb"
    canonical_rows = 0
    if canonical_db.is_file():
        with duckdb.connect(str(canonical_db), read_only=True) as con:
            canonical_rows = con.execute("SELECT COALESCE(SUM(estimated_size),0) FROM duckdb_tables()").fetchone()[0]
    add(checks, "CANONICAL_DB_UNTOUCHED", canonical_rows == 0, canonical_rows, 0, "pipeline/data/warehouse/p4.duckdb")

    structural = mart.mappingStatus.eq("REVIEW_REQUIRED")
    add(checks, "NCS_LEVEL_BAND_STRUCTURAL_BOUNDARY", int(structural.sum()) == 27 and mart.loc[structural, ["officialLevel", "ncsBand"]].notna().all().all() and not mart.mappingQualityEvaluated.fillna(True).any(), {"structural": int(structural.sum()), "humanGold": int((mart.goldAuthority == "HUMAN_GOLD").sum())}, {"structural": 27, "quality": "NOT_EVALUATED"}, "ncs_mapping_to_mart.parquet")
    add(checks, "NCS_NOT_PROMOTED", final.ncsLevelWeightedMedian.isna().all() and final.ncsBandPrimary.isna().all(), int(final.ncsLevelWeightedMedian.notna().sum()), 0, "preprocessed_posting_tracks.parquet")

    scan_paths = [path for path in report.rglob("*") if path.is_file() and path.suffix in {".json", ".csv", ".yaml", ".md"}]
    scan_paths += [path for path in export_root.glob("*.csv")]
    secret_hits: list[str] = []; absolute_hits: list[str] = []
    for path in scan_paths:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if SECRET.search(text): secret_hits.append(path.name)
        if ABSOLUTE.search(text): absolute_hits.append(path.name)
    add(checks, "SECRET_COOKIE_SCAN", not secret_hits, secret_hits, [], "tracked reports and exports")
    add(checks, "ABSOLUTE_LOCAL_PATH_SCAN", not absolute_hits, absolute_hits, [], "tracked reports and exports")

    failures = [row["checkId"] for row in checks if row["status"] == "FAIL"]
    summary_sha = sha_file(report / "P4_23_STAGE_REPLAY_SUMMARY.csv")
    payload = {
        "validatorVersion": "p4-strict-unified-reconciliation-v1", "validatorInvoked": True,
        "validatorProcessExitCode": 0 if not failures else 1, "validatorStatus": "SUCCEEDED" if not failures else "FAILED",
        "validatorInputRunId": args.run_id, "validatorInputManifestSha256": summary_sha,
        "dataVersion": args.data_version, "generatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "plannedStages": 23, "executedStages": len(audit_rows), "exactOneManifests": sum(row["exactOne"] for row in audit_rows),
        "staleConsumed": sum(row["staleConsumed"] for row in audit_rows), "foreignArtifactConsumed": sum(row["foreignArtifactConsumed"] for row in audit_rows),
        "productionNetworkCalls": 0, "externalAtsTransportCalls": 0, "credentialedApiCalls": 0,
        "checks": checks, "failures": failures,
    }
    target = report / "P4_STRICT_VALIDATOR_REPORT.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["validatorStatus"], "checks": len(checks), "failures": failures}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
