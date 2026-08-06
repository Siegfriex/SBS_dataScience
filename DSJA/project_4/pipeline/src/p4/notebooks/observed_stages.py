from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd

from p4.common.hashing import canonical_json_sha256, sha256_file
from p4.contracts.duty_input import validate_observed_duty_input_handoff
from p4.contracts.ncs_handoff import validate_agent4_ncs_handoff
from p4.contracts.release_validation import validate_observed_input_package, validate_release_gates
from p4.dedup.reposts import assign_observed_singleton_groups
from p4.export.observed import build_export_frames, export_observed_frames, validate_export_bundle
from p4.export.observed import RUN_TIMESTAMP
from p4.normalize.observed_batch import (
    CONTRACT_VERSION,
    CRAWL_RELEASE_ID,
    DATA_PROVENANCE,
    DATA_VERSION,
    PARSE_VERSION,
    build_observed_batch,
)
from p4.warehouse.connection import connect
from p4.warehouse.observed import bootstrap_observed_warehouse, observed_inventory, replace_observed_table


OBSERVED_TABLES = (
    "raw_posting",
    "posting_normalized",
    "posting_semantics",
    "posting_track",
    "posting_section",
    "requirement_fact",
    "eligibility",
    "posting_dedup",
    "career_access_label",
    "ocr_queue",
    "manifest_cursor",
    "posting_ncs_candidates",
    "posting_ncs_matches",
)

STAGE_CONTRACT = {
    "00ContractAndInputAudit": ("A2-00-CONTRACT-AUDIT", "agent2-audit-v1", "CONTRACT_LINKED"),
    "01LoadCrawlRelease": ("A2-01-LOAD", "p4-contract-2.1.2", "INPUT_LOADED"),
    "02ParseAndNormalize": ("A2-02-PARSE", "p4-contract-2.1.2", "PARSE_READY"),
    "03OcrAndSectionRecovery": ("A2-03-OCR", "p4-contract-2.1.2", "OCR_READY"),
    "04SplitTracks": ("A2-04-TRACK", "p4-contract-2.1.2", "TRACK_READY"),
    "05ExtractRequirements": ("A2-05-REQUIREMENT", "p4-contract-2.1.2", "REQUIREMENT_READY"),
    "06Deduplicate90Days": ("A2-06-DEDUP", "p4-contract-2.1.2", "DEDUP_READY"),
    "07LabelCareerAccess": ("A2-07-LABEL", "p4-contract-2.1.2", "LABEL_DEV_READY"),
    "08LoadAndPrepareNcs": ("A2-08-NCS-LOAD", "ncs-agent4-acceptance-v1", "NCS_BASE_READY"),
    "09MapPostingToNcs": ("A2-09-NCS-MAP", "ncs-agent4-acceptance-v1", "NCS_MAPPING_DEV_READY"),
    "10ExportPreprocessedCsv": ("A2-10-EXPORT", "preprocessing-export-v1", "PREPROCESSED_EXPORT_BUILT"),
    "11PreprocessedDataQa": ("A2-11-EXPORT-QA", "preprocessing-qa-v1", "PREPROCESSED_CSV_READY"),
}

QUALITY_COLUMNS = ["gateId", "ruleId", "severity", "status", "observedValue", "threshold", "evidencePath"]
TERMINATION_ARTIFACTS = ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return f"EXTERNAL_INPUT/{path.name}"


def _write_duty_handoff(project_root: Path, frames: dict[str, pd.DataFrame]) -> Path:
    duty = frames["posting_section"].query("sectionType == 'duty'").merge(
        frames["posting_track"][["trackId", "postingId", "jobCode"]], on="trackId", how="left"
    ).merge(
        frames["posting_normalized"][["postingId", "titleText", "ncsEligibleFlag", "inputSha256"]],
        on="postingId",
        how="left",
    )
    rows = [
        {
            "trackId": row.trackId,
            "sectionId": row.sectionId,
            "evidenceText": row.sectionText,
            "jobTitle": row.titleText,
            "jobCode": row.jobCode if row.jobCode is not None else None,
            "ncsEligibleFlag": bool(row.ncsEligibleFlag),
            "parseVersion": PARSE_VERSION,
            "inputSha256": row.inputSha256,
        }
        for row in duty.itertuples(index=False)
    ]
    payload = {
        "agentId": "P4-A2-PIPELINE",
        "recipientAgentId": "P4-A4-NCS",
        "handoffType": "DUTY_INPUT_OBSERVED_DEVELOPMENT",
        "status": DATA_PROVENANCE,
        "contractVersion": CONTRACT_VERSION,
        "crawlReleaseId": CRAWL_RELEASE_ID,
        "dataVersion": DATA_VERSION,
        "parseVersion": PARSE_VERSION,
        "grain": "sectionId",
        "empiricalUseAllowed": False,
        "promotionAllowed": False,
        "rowCount": len(rows),
        "rowsSha256": "",
        "rows": rows,
    }
    from p4.common.hashing import canonical_json_sha256

    payload["rowsSha256"] = canonical_json_sha256(rows)
    target = project_root / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
    _write_json(target, payload)
    validate_observed_duty_input_handoff(target)
    return target


def _load_frames(database: Path) -> dict[str, pd.DataFrame]:
    with connect(database, read_only=True) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='observed'"
            ).fetchall()
        }
        return {
            name: connection.execute(f"SELECT * FROM observed.{name}").fetchdf()
            for name in OBSERVED_TABLES
            if name != "manifest_cursor" and name in existing
        }


def _build_observed(project_root: Path, release_root: Path, crawl_root: Path) -> tuple[dict[str, Any], dict[str, pd.DataFrame], Path]:
    batch = build_observed_batch(release_root, crawl_root)
    frames = batch["frames"]
    database = project_root / "pipeline/data/warehouse/p4.observed-dev.duckdb"
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        if database.name != "p4.observed-dev.duckdb":
            raise ValueError("refusing to replace a non-observed warehouse")
        database.unlink()
    bootstrap_observed_warehouse(database, PARSE_VERSION)
    for table_name, frame in frames.items():
        replace_observed_table(database, table_name, frame)
    _write_duty_handoff(project_root, frames)
    return batch, frames, database


def _frames_semantic_sha256(frames: dict[str, pd.DataFrame]) -> str:
    payload = {
        name: frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
        for name, frame in sorted(frames.items())
    }
    return canonical_json_sha256(payload)


def _git_identity(project_root: Path) -> tuple[str, str]:
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=project_root, text=True).strip() or "DETACHED_HEAD"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root, text=True).strip()
    return branch, head


def _canonical_database_inventory(database: Path) -> dict[str, Any]:
    """Count canonical objects and persisted rows without treating DDL as data."""
    if not database.is_file():
        return {"objectCount": 0, "tableCount": 0, "viewCount": 0, "totalRowCount": 0, "zeroRows": True}
    canonical_schemas = {"raw", "core", "ncs", "mart", "qa"}
    with connect(database, read_only=True) as connection:
        objects = connection.execute(
            "SELECT table_schema, table_name, table_type "
            "FROM information_schema.tables "
            "WHERE table_schema IN ('raw','core','ncs','mart','qa') "
            "ORDER BY table_schema, table_name"
        ).fetchall()
        base_tables = [row for row in objects if str(row[2]).upper() == "BASE TABLE"]
        total_rows = 0
        for schema_name, table_name, _ in base_tables:
            quoted_schema = '"' + str(schema_name).replace('"', '""') + '"'
            quoted_table = '"' + str(table_name).replace('"', '""') + '"'
            total_rows += int(connection.execute(f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}").fetchone()[0])
    return {
        "objectCount": len(objects),
        "tableCount": len(base_tables),
        "viewCount": len(objects) - len(base_tables),
        "totalRowCount": total_rows,
        "zeroRows": total_rows == 0,
    }


def _quality_contract_rows(stage: str, rows: list[dict[str, Any]], evidence_path: str) -> pd.DataFrame:
    _, _, produced_gate = STAGE_CONTRACT[stage]
    contracted: list[dict[str, Any]] = []
    for row in rows or [{"check": "stage_completed", "status": "PASS", "observed": True}]:
        raw_status = str(row.get("status") or "NOT_EVALUATED")
        status = raw_status if raw_status in {"PASS", "FAIL", "NOT_EVALUATED", "REVIEW_REQUIRED"} else "REVIEW_REQUIRED"
        contracted.append(
            {
                "gateId": produced_gate,
                "ruleId": str(row.get("check") or row.get("ruleId") or "stage_completed"),
                "severity": "ERROR" if status == "FAIL" else "INFO" if status == "PASS" else "WARNING",
                "status": status,
                "observedValue": str(row.get("observed", row.get("observedValue", ""))),
                "threshold": str(row.get("threshold", "PASS")),
                "evidencePath": evidence_path,
            }
        )
    return pd.DataFrame(contracted, columns=QUALITY_COLUMNS)


def _metrics_contract(stage: str, metrics: dict[str, Any]) -> dict[str, Any]:
    stage_id, _, _ = STAGE_CONTRACT[stage]
    records: list[dict[str, Any]] = []

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in sorted(value.items(), key=lambda item: str(item[0])):
                visit(f"{prefix}.{key}" if prefix else str(key), child)
            return
        scalar = value
        if isinstance(value, (list, tuple, set)):
            scalar = json.dumps(list(value), ensure_ascii=False, sort_keys=True, default=str)
        if not isinstance(scalar, (str, int, float, bool)) and scalar is not None:
            scalar = str(scalar)
        unit = "flag" if isinstance(scalar, bool) else "count" if isinstance(scalar, int) else "value"
        records.append(
            {
                "metricId": prefix or "stage",
                "value": scalar,
                "numerator": None,
                "denominator": None,
                "unit": unit,
                "grain": "stage",
                "unknownHandling": "null preserved; zero denominator is NOT_EVALUATED",
                "status": "INFORMATIONAL",
            }
        )

    visit("", metrics)
    return {
        "metricsVersion": "stage-metrics-v1",
        "runId": f"OBSERVED_DEV_20260806_01-{stage_id}",
        "runMode": "observed-dev",
        "stageId": stage_id,
        "contractVersion": CONTRACT_VERSION,
        "crawlReleaseId": CRAWL_RELEASE_ID,
        "dataVersion": DATA_VERSION,
        "dataProvenance": DATA_PROVENANCE,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "generatedAt": RUN_TIMESTAMP,
        "metrics": records,
    }


def _file_record(path: Path, record_root: Path, stage_id: str) -> dict[str, Any]:
    rows: int | None = None
    columns: int | None = None
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
        rows, columns = len(frame), len(frame.columns)
    elif path.suffix == ".csv":
        frame = pd.read_csv(path)
        rows, columns = len(frame), len(frame.columns)
    return {
        "path": _relative(path, record_root),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "columns": columns,
        "format": path.suffix.lstrip(".") or "binary",
        "grain": path.stem,
        "nullablePolicy": "schema-defined nulls preserved",
        "sourceStage": stage_id,
        "dataProvenance": DATA_PROVENANCE,
    }


def _manifest_contract(
    project_root: Path,
    release_root: Path,
    stage: str,
    quality: pd.DataFrame,
    output_paths: list[Path],
    record_root: Path,
    row_counts: dict[str, int],
) -> dict[str, Any]:
    stage_id, schema_version, produced_gate = STAGE_CONTRACT[stage]
    branch, head = _git_identity(project_root)
    statuses = set(quality["status"])
    status = "FAILED" if "FAIL" in statuses else "NOT_EVALUATED" if statuses <= {"NOT_EVALUATED", "REVIEW_REQUIRED"} else "SUCCEEDED"
    parameter_sha = canonical_json_sha256(
        {
            "runMode": "observed-dev",
            "contractVersion": CONTRACT_VERSION,
            "crawlReleaseId": CRAWL_RELEASE_ID,
            "dataVersion": DATA_VERSION,
            "randomSeed": 20260806,
            "stageId": stage_id,
        }
    )
    manifest = {
        "manifestVersion": "stage-manifest-v1",
        "runId": f"OBSERVED_DEV_20260806_01-{stage_id}",
        "runMode": "observed-dev",
        "stageId": stage_id,
        "status": status,
        "agentId": "P4-A2-PIPELINE",
        "branch": branch,
        "gitHead": head,
        "contractVersion": CONTRACT_VERSION,
        "schemaVersion": schema_version,
        "dataVersion": DATA_VERSION,
        "crawlReleaseId": CRAWL_RELEASE_ID,
        "dataProvenance": DATA_PROVENANCE,
        "startedAt": RUN_TIMESTAMP,
        "completedAt": RUN_TIMESTAMP,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "inputManifestSha256": sha256_file(release_root / "HANDOFF.json"),
        "parameterSha256": parameter_sha,
        "rowCounts": row_counts,
        "gateResults": [
            {
                "gateId": produced_gate,
                "status": "FAIL" if status == "FAILED" else "NOT_EVALUATED" if status == "NOT_EVALUATED" else "PASS",
                "evidencePath": "stage_quality.csv",
            }
        ],
        "warnings": quality.loc[quality["status"].isin(["REVIEW_REQUIRED", "NOT_EVALUATED"]), "ruleId"].astype(str).tolist(),
        "errors": quality.loc[quality["status"].eq("FAIL"), "ruleId"].astype(str).tolist(),
        "files": [_file_record(path, record_root, stage_id) for path in output_paths if path.is_file()],
        "terminationArtifacts": TERMINATION_ARTIFACTS,
        "dataPolicies": {
            "canonicalStorage": "DUCKDB_PARQUET",
            "csvPurpose": "HUMAN_INSPECTION_EXPORT",
            "eligibilityColumns": ["postingEligibleFlag", "rq1EligibleFlag", "rq2EligibleFlag", "ncsEligibleFlag"],
            "highDemandScore": "ALL_NULL",
        },
    }
    if stage in {"10ExportPreprocessedCsv", "11PreprocessedDataQa"}:
        manifest["mappingPolicy"] = {
            "mappingMode": "LEXICAL_BASELINE",
            "codeSetStatus": "REVIEW_REQUIRED",
            "goldValidatedFlag": False,
            "denseScore": None,
        }
    return manifest


def _validate_control_artifacts(control_root: Path | None, manifest: dict[str, Any], metrics: dict[str, Any], quality: pd.DataFrame) -> None:
    if control_root is None or not control_root.is_dir():
        return
    checker = jsonschema.FormatChecker()
    for filename, payload in (("STAGE_MANIFEST.schema.json", manifest), ("STAGE_METRICS.schema.json", metrics)):
        schema = json.loads((control_root / filename).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=checker).validate(payload)
    if list(quality.columns) != QUALITY_COLUMNS:
        raise ValueError("stage_quality.csv columns do not match Notebook execution contract")
    allowed = {"PASS", "FAIL", "NOT_EVALUATED", "REVIEW_REQUIRED"}
    if not set(quality["status"]).issubset(allowed):
        raise ValueError("stage_quality.csv contains an invalid status")


def _stage_artifacts(
    project_root: Path,
    pipeline_root: Path,
    release_root: Path,
    control_root: Path | None,
    stage: str,
    metrics: dict[str, Any],
    quality_rows: list[dict[str, Any]],
    output_paths: list[Path],
    run_root: Path | None = None,
) -> dict[str, Any]:
    stage_root = (run_root or pipeline_root / "runs/notebooks/observed-dev/AGENT2_20260806_01") / "artifacts" / stage
    stage_root.mkdir(parents=True, exist_ok=True)
    quality = _quality_contract_rows(stage, quality_rows, "stage_quality.csv")
    quality_path = stage_root / "stage_quality.csv"
    quality.to_csv(quality_path, index=False, encoding="utf-8-sig")
    metrics_path = stage_root / "stage_metrics.json"
    metrics_payload = _metrics_contract(stage, metrics)
    _write_json(metrics_path, metrics_payload)
    row_counts = {
        key: int(value)
        for key, value in metrics.items()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }
    manifest = _manifest_contract(
        project_root,
        release_root,
        stage,
        quality,
        output_paths,
        pipeline_root,
        row_counts,
    )
    manifest_path = stage_root / "stage_manifest.json"
    _write_json(manifest_path, manifest)
    _validate_control_artifacts(control_root, manifest, metrics_payload, quality)
    checksum_targets = [manifest_path, metrics_path, quality_path]
    checksums_path = stage_root / "CHECKSUMS.sha256"
    checksums_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    return {
        "stageManifest": _relative(manifest_path, pipeline_root),
        "stageMetrics": _relative(metrics_path, pipeline_root),
        "stageQuality": _relative(quality_path, pipeline_root),
        "checksums": _relative(checksums_path, pipeline_root),
        "qualityStatus": "PASS" if manifest["status"] == "SUCCEEDED" else "FAIL",
    }


def run_observed_stage(
    stage: str,
    project_root: str | Path,
    release_root: str | Path,
    crawl_root: str | Path,
    output_root: str | Path | None = None,
    control_root: str | Path | None = None,
    ncs_handoff_path: str | Path | None = None,
    ncs_project_root: str | Path | None = None,
    run_root: str | Path | None = None,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    pipeline = project / "pipeline"
    release = Path(release_root).resolve()
    crawl = Path(crawl_root).resolve()
    database = pipeline / "data/warehouse/p4.observed-dev.duckdb"
    output = Path(output_root).resolve() if output_root else pipeline / "data/exports/observed-dev/OBSERVED_DEV_20260806_01"
    control = Path(control_root).resolve() if control_root else project / "crawl/control"
    ncs_handoff = Path(ncs_handoff_path).resolve() if ncs_handoff_path else project / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"
    ncs_project = Path(ncs_project_root).resolve() if ncs_project_root else project
    notebook_run_root = Path(run_root).resolve() if run_root else pipeline / "runs/notebooks/observed-dev/AGENT2_20260806_01"
    metrics: dict[str, Any] = {"stage": stage}
    quality: list[dict[str, Any]] = []
    outputs: list[Path] = []

    if stage == "00ContractAndInputAudit":
        handoff_payload = json.loads((release / "HANDOFF.json").read_text(encoding="utf-8"))
        validation = (
            validate_observed_input_package(release / "HANDOFF.json")
            if handoff_payload.get("packageId") == "OBSERVED_INPUT_20260806_01"
            else validate_release_gates(release / "HANDOFF.json")
        )
        metrics.update(validation)
        canonical_database = pipeline / "data/warehouse/p4.duckdb"
        canonical_inventory = _canonical_database_inventory(canonical_database)
        metrics["canonicalDatabaseObjectCount"] = canonical_inventory["objectCount"]
        metrics["canonicalDatabaseTableCount"] = canonical_inventory["tableCount"]
        metrics["canonicalDatabaseViewCount"] = canonical_inventory["viewCount"]
        metrics["canonicalDatabaseRowCount"] = canonical_inventory["totalRowCount"]
        quality.append({"check": "source_adapter_conformance", "status": validation["sourceAdapterConformance"], "observed": validation["sourceAdapterConformance"]})
        quality.append({"check": "empirical_analysis_disabled", "status": "PASS" if not validation["empiricalAnalysisAllowed"] else "FAIL", "observed": validation["empiricalAnalysisAllowed"]})
        quality.append({"check": "canonical_database_zero", "status": "PASS" if canonical_inventory["zeroRows"] else "FAIL", "observed": canonical_inventory["totalRowCount"]})
    elif stage == "01LoadCrawlRelease":
        batch = build_observed_batch(release, crawl)
        frames = batch["frames"]
        if database.exists():
            database.unlink()
        bootstrap_observed_warehouse(database, PARSE_VERSION)
        replace_observed_table(database, "raw_posting", frames["raw_posting"])
        metrics.update({
            "inputPostings": batch["metrics"]["inputPostings"],
            "rawPostingRows": len(frames["raw_posting"]),
            "realSsrRaw": batch["metrics"]["realSsrRaw"],
            "derivedObservedAccepted": batch["metrics"]["derivedObservedAccepted"],
            "warehouseInventory": observed_inventory(database),
        })
        quality.append({"check": "raw_posting_loaded", "status": "PASS" if len(frames["raw_posting"]) == 137 else "FAIL", "observed": len(frames["raw_posting"])})
        quality.append({"check": "observed_warehouse_isolated", "status": "PASS", "observed": database.name})
    elif stage == "02ParseAndNormalize":
        batch = build_observed_batch(release, crawl)
        frames = batch["frames"]
        for name in ("posting_normalized", "posting_semantics", "manifest_cursor", "eligibility"):
            replace_observed_table(database, name, frames[name])
        metrics.update(batch["metrics"])
        metrics["parseFailures"] = batch["parseFailures"]
        metrics["warehouseInventory"] = observed_inventory(database)
        metrics["warehouseSemanticSha256"] = _frames_semantic_sha256(frames)
        quality.append({"check": "parse_failures", "status": "PASS" if not batch["parseFailures"] else "FAIL", "observed": len(batch["parseFailures"])})
        quality.append({"check": "posting_rows", "status": "PASS" if len(frames["posting_normalized"]) == len(frames["raw_posting"]) else "FAIL", "observed": len(frames["posting_normalized"])})
    elif stage == "03OcrAndSectionRecovery":
        batch = build_observed_batch(release, crawl)
        frames = batch["frames"]
        replace_observed_table(database, "posting_section", frames["posting_section"])
        replace_observed_table(database, "ocr_queue", frames["ocr_queue"])
        metrics.update({"sectionRows": len(frames["posting_section"]), "ocrQueueRows": len(frames["ocr_queue"]), "ocrAssetsFetched": 0, "ocrMode": "ROUTING_ONLY", "warehouseInventory": observed_inventory(database)})
        quality.append({"check": "ocr_routing_only", "status": "PASS" if frames["ocr_queue"].get("queueStatus", pd.Series(dtype=str)).eq("ASSET_NOT_FETCHED").all() else "FAIL", "observed": "ROUTING_ONLY"})
        quality.append({"check": "section_materialized", "status": "PASS" if len(frames["posting_section"]) == 84 else "FAIL", "observed": len(frames["posting_section"])})
    elif stage == "04SplitTracks":
        batch = build_observed_batch(release, crawl)
        tracks = batch["frames"]["posting_track"]
        replace_observed_table(database, "posting_track", tracks)
        metrics.update({"trackRows": len(tracks), "trackTypes": tracks["trackType"].value_counts(dropna=False).to_dict(), "warehouseInventory": observed_inventory(database)})
        quality.append({"check": "track_pk", "status": "PASS" if not tracks["trackId"].duplicated().any() else "FAIL", "observed": int(tracks["trackId"].duplicated().sum())})
    elif stage == "05ExtractRequirements":
        batch = build_observed_batch(release, crawl)
        frames = batch["frames"]
        replace_observed_table(database, "requirement_fact", frames["requirement_fact"])
        duty_path = _write_duty_handoff(project, frames)
        duty = validate_observed_duty_input_handoff(duty_path)
        outputs.append(duty_path)
        metrics.update({"requirementRows": len(frames["requirement_fact"]), "dutyRows": duty["rowCount"], "dutyRowsSha256": duty["rowsSha256"], "warehouseInventory": observed_inventory(database)})
        quality.append({"check": "requirement_evidence", "status": "PASS" if frames["requirement_fact"]["sectionId"].notna().all() else "FAIL", "observed": len(frames["requirement_fact"])})
        quality.append({"check": "duty_handoff", "status": "PASS" if duty["rowCount"] == 28 else "FAIL", "observed": duty["rowCount"]})
    elif stage == "06Deduplicate90Days":
        source = _load_frames(database)
        dedup = assign_observed_singleton_groups(source["posting_track"])
        replace_observed_table(database, "posting_dedup", dedup)
        metrics.update({"dedupRows": len(dedup), "duplicateGroups": dedup["duplicateGroupId"].nunique(), "repostEdgesInferred": 0, "dedupMode": "OBSERVED_SINGLETON_NO_CORPUS_INFERENCE", "warehouseInventory": observed_inventory(database)})
        quality.append({"check": "observed_no_corpus_inference", "status": "PASS" if dedup["canonicalRecordFlag"].all() else "FAIL", "observed": int(dedup["canonicalRecordFlag"].sum())})
    elif stage == "07LabelCareerAccess":
        source = _load_frames(database)
        label_frames = build_export_frames(source)
        labels = label_frames["career_access_labels"]
        replace_observed_table(database, "career_access_label", labels)
        metrics.update({"labelRows": len(labels), "careerClasses": labels["careerClass"].value_counts(dropna=False).to_dict(), "internAccessClasses": labels["internAccessClass"].value_counts(dropna=False).to_dict(), "warehouseInventory": observed_inventory(database)})
        quality.append({"check": "label_track_coverage", "status": "PASS" if labels["trackId"].nunique() == len(source["posting_track"]) else "FAIL", "observed": labels["trackId"].nunique()})
    elif stage in {"08LoadAndPrepareNcs", "09MapPostingToNcs"}:
        accepted = validate_agent4_ncs_handoff(ncs_handoff, ncs_project)
        duty_path = project / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
        duty = validate_observed_duty_input_handoff(duty_path)
        if accepted["payload"]["inputRowsSha256"] != duty["rowsSha256"]:
            raise ValueError("Agent4 input rows SHA does not match the Agent2 duty handoff")
        metrics.update(
            {
                "agent4HandoffSha256": accepted["handoffSha256"],
                "ncsUnitRows": len(accepted["frames"]["ncs_units"]),
                "coreCodeRows": len(accepted["frames"]["core_ai_it_codes"]),
                "coreIncludedRows": int(accepted["frames"]["core_ai_it_codes"]["included"].fillna(False).astype(bool).sum()),
                "candidateRows": accepted["candidateRows"],
                "matchRows": accepted["matchRows"],
                "unmappedRows": accepted["unmappedRows"],
            }
        )
        quality.append({"check": "agent4_handoff_self_sha", "status": "PASS", "observed": accepted["handoffSha256"]})
        quality.append({"check": "agent4_input_rows_sha", "status": "PASS", "observed": duty["rowsSha256"]})
        quality.append({"check": "ncs_source_rows", "status": "PASS" if len(accepted["frames"]["ncs_units"]) == 13442 else "FAIL", "observed": len(accepted["frames"]["ncs_units"])})
        quality.append({"check": "core_code_review_set", "status": "PASS" if len(accepted["frames"]["core_ai_it_codes"]) == 120 else "FAIL", "observed": len(accepted["frames"]["core_ai_it_codes"])})
        if stage == "09MapPostingToNcs":
            for name in ("posting_ncs_candidates", "posting_ncs_matches"):
                frame = accepted["frames"][name]
                replace_observed_table(database, name, frame)
            inventory = observed_inventory(database)
            metrics["warehouseInventory"] = inventory
            acceptance_path = project / "shared/handoffs/AGENT2_NCS_MAPPING_ACCEPTANCE_OBSERVED_DEV.json"
            acceptance_payload = {
                "agentId": "P4-A2-PIPELINE",
                "sourceAgentId": "P4-A4-NCS",
                "status": "NCS_MAPPING_DEV_ACCEPTED",
                "contractVersion": CONTRACT_VERSION,
                "crawlReleaseId": CRAWL_RELEASE_ID,
                "dataVersion": DATA_VERSION,
                "dataProvenance": DATA_PROVENANCE,
                "empiricalAnalysisAllowed": False,
                "promotionAllowed": False,
                "sourceHandoffSha256": accepted["handoffSha256"],
                "candidateRows": accepted["candidateRows"],
                "matchRows": accepted["matchRows"],
                "unmappedRows": accepted["unmappedRows"],
                "mappingMode": "LEXICAL_BASELINE",
                "codeSetStatus": "REVIEW_REQUIRED",
                "goldValidatedFlag": False,
                "denseScore": None,
            }
            acceptance_payload["acceptanceSha256"] = canonical_json_sha256(acceptance_payload)
            _write_json(acceptance_path, acceptance_payload)
            outputs.append(acceptance_path)
            quality.append({"check": "agent4_mapping_tables_loaded", "status": "PASS", "observed": {"candidates": inventory.get("posting_ncs_candidates"), "matches": inventory.get("posting_ncs_matches")}})
    elif stage == "10ExportPreprocessedCsv":
        source_frames = _load_frames(database)
        candidates = source_frames.pop("posting_ncs_candidates", None)
        matches = source_frames.pop("posting_ncs_matches", None)
        export_frames = build_export_frames(source_frames, candidates, matches)
        export_meta = export_observed_frames(export_frames, output)
        metrics.update(export_meta)
        outputs.extend(sorted(output.glob("*.parquet")))
        outputs.extend(sorted(output.glob("*.csv")))
        outputs.append(output / "CHECKSUMS.sha256")
        quality.append({"check": "preprocessed_export", "status": "PASS", "observed": len(export_frames["preprocessed_posting_tracks"])})
    elif stage == "11PreprocessedDataQa":
        export_frames = {
            path.stem: pd.read_parquet(path)
            for path in output.glob("*.parquet")
        }
        quality_frame, summary = validate_export_bundle(export_frames, output)
        quality_path = output / "stage_quality.csv"
        summary_path = output / "data_quality_summary.csv"
        pd.DataFrame([summary]).to_csv(summary_path, index=False, encoding="utf-8-sig")
        quality_contract = _quality_contract_rows(stage, quality_frame.to_dict(orient="records"), "stage_quality.csv")
        quality_contract.to_csv(quality_path, index=False, encoding="utf-8-sig")
        row_counts = {name: len(frame) for name, frame in export_frames.items()}
        bundle_metrics_path = output / "stage_metrics.json"
        bundle_metrics = _metrics_contract(stage, {**summary, "rowCounts": row_counts})
        _write_json(bundle_metrics_path, bundle_metrics)
        data_artifacts = [
            path for path in sorted(output.iterdir())
            if path.is_file() and path.name not in TERMINATION_ARTIFACTS
        ]
        bundle_manifest_path = output / "stage_manifest.json"
        bundle_manifest = _manifest_contract(
            project,
            release,
            stage,
            quality_contract,
            data_artifacts,
            output,
            row_counts,
        )
        _write_json(bundle_manifest_path, bundle_manifest)
        _validate_control_artifacts(control, bundle_manifest, bundle_metrics, quality_contract)
        checksum_targets = [
            path for path in sorted(output.iterdir())
            if path.is_file() and path.name != "CHECKSUMS.sha256"
        ]
        (output / "CHECKSUMS.sha256").write_text(
            "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_targets),
            encoding="utf-8",
        )
        metrics.update(summary)
        outputs.extend([quality_path, summary_path, bundle_metrics_path, bundle_manifest_path, output / "CHECKSUMS.sha256"])
        quality.extend(quality_frame.to_dict(orient="records"))
    else:
        raise ValueError(f"unknown observed stage: {stage}")
    return _stage_artifacts(project, pipeline, release, control, stage, metrics, quality, outputs, notebook_run_root)


def audit_observed_stage_inputs(
    stage: str,
    *,
    project_root: str | Path,
    release_root: str | Path,
    ncs_handoff_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read-only preflight used by every source Notebook before mutation."""
    project = Path(project_root).resolve()
    release = Path(release_root).resolve()
    required = [release / "HANDOFF.json", release / "posting_manifest.parquet"]
    if stage in {"08LoadAndPrepareNcs", "09MapPostingToNcs"}:
        required.append(Path(ncs_handoff_path).resolve() if ncs_handoff_path else project / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json")
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing stage inputs: {missing}")
    return {
        "stage": stage,
        "requiredInputCount": len(required),
        "missingInputCount": 0,
        "inputNames": [path.name for path in required],
        "runMode": "observed-dev",
        "dataProvenance": DATA_PROVENANCE,
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
    }


def _stage_runner(stage: str):
    def execute(**kwargs: Any) -> dict[str, Any]:
        return run_observed_stage(stage, **kwargs)
    execute.__name__ = f"run_{stage}_stage"
    return execute


run_contract_and_input_audit_stage = _stage_runner("00ContractAndInputAudit")
run_load_crawl_release_stage = _stage_runner("01LoadCrawlRelease")
run_parse_and_normalize_stage = _stage_runner("02ParseAndNormalize")
run_ocr_and_section_recovery_stage = _stage_runner("03OcrAndSectionRecovery")
run_split_tracks_stage = _stage_runner("04SplitTracks")
run_extract_requirements_stage = _stage_runner("05ExtractRequirements")
run_deduplicate_90_days_stage = _stage_runner("06Deduplicate90Days")
run_label_career_access_stage = _stage_runner("07LabelCareerAccess")
run_load_and_prepare_ncs_stage = _stage_runner("08LoadAndPrepareNcs")
run_map_posting_to_ncs_stage = _stage_runner("09MapPostingToNcs")
run_export_preprocessed_csv_stage = _stage_runner("10ExportPreprocessedCsv")
run_preprocessed_data_qa_stage = _stage_runner("11PreprocessedDataQa")
