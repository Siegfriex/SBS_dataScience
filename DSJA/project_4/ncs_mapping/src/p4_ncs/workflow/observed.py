"""Thin orchestration stages for the five Agent 4 M1 notebooks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from p4_ncs.contracts.observed_duty import canonical_json_sha256, load_and_validate_observed_duties
from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary, validate_alias_dictionary
from p4_ncs.mapping.observed_baseline import map_observed_duties
from p4_ncs.quality.stage_artifacts import StageContext, file_record, sha256_file, write_stage_artifacts
from p4_ncs.retrieval.lexical_index import LexicalIndex

STAGES = {
    "A4-00-NCS-SOURCE": "ncs-base-v1",
    "A4-01-CODESET": "core-ai-it-v0.1",
    "A4-02-RETRIEVAL": "ncs-retrieval-v1",
    "A4-03-MAP-OBSERVED": "posting-ncs-candidates-v1",
    "A4-04-EXPORT": "ncs-export-v1",
}
RUN_ID = "NCS_MAPPING_OBSERVED_20260806_01"
DATA_VERSION = "observed-dev-20260806.1"


def _metric(metric_id: str, value: Any, grain: str, status: str = "INFORMATIONAL") -> dict[str, Any]:
    return {
        "metricId": metric_id,
        "value": value,
        "numerator": None,
        "denominator": None,
        "unit": "count" if isinstance(value, int) and not isinstance(value, bool) else "value",
        "grain": grain,
        "unknownHandling": "unknown retained; no empirical inference",
        "status": status,
    }


def _quality(gate: str, rule: str, status: str, observed: Any, threshold: Any, evidence: str) -> dict[str, Any]:
    return {
        "gateId": gate,
        "ruleId": rule,
        "severity": "ERROR" if status == "FAIL" else ("WARNING" if status == "REVIEW_REQUIRED" else "INFO"),
        "status": status,
        "observedValue": observed,
        "threshold": threshold,
        "evidencePath": evidence,
    }


def _root(root: str | Path | None = None) -> Path:
    return Path(root).resolve() if root else Path(__file__).resolve().parents[3]


def _schema_dir(ncs_root: Path, schema_dir: str | Path | None) -> Path | None:
    if schema_dir:
        return Path(schema_dir).resolve()
    if os.environ.get("P4_CONTROL_SCHEMA_DIR"):
        return Path(os.environ["P4_CONTROL_SCHEMA_DIR"]).resolve()
    same_worktree = ncs_root.parent / "crawl" / "control"
    return same_worktree if (same_worktree / "STAGE_MANIFEST.schema.json").exists() else None


def _input_path(ncs_root: Path, duty_input_path: str | Path | None) -> Path:
    if duty_input_path:
        return Path(duty_input_path).resolve()
    if os.environ.get("P4_A2_DUTY_HANDOFF"):
        return Path(os.environ["P4_A2_DUTY_HANDOFF"]).resolve()
    local = ncs_root.parent / "shared" / "handoffs" / "AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
    if local.exists():
        return local.resolve()
    raise FileNotFoundError("set DUTY_INPUT_PATH or P4_A2_DUTY_HANDOFF for A4-03/A4-04")


def _load_sources(ncs_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    units = pd.read_parquet(ncs_root / "data" / "processed" / "ncsUnit.parquet")
    codeset = pd.read_parquet(ncs_root / "data" / "processed" / "coreAiItCodeSet.parquet")
    aliases = load_alias_dictionary(ncs_root / "configs" / "ncs_alias_dictionary.yaml")
    return units, codeset, aliases


def _write_tabular_pair(frame: pd.DataFrame, root: Path, stem: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    parquet_path = root / f"{stem}.parquet"
    csv_path = root / f"{stem}.csv"
    frame.to_parquet(parquet_path, index=False)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    loaded = pd.read_csv(csv_path, dtype="string", keep_default_na=False)
    expected = frame.astype("string").fillna("")
    actual = loaded.astype("string").fillna("")
    pd.testing.assert_frame_equal(expected.reset_index(drop=True), actual.reset_index(drop=True), check_dtype=False)
    return parquet_path, csv_path


def _map_and_persist(ncs_root: Path, duty_input_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, Any, dict[str, Any]]:
    duties, validation, envelope = load_and_validate_observed_duties(duty_input_path)
    units, codeset, aliases = _load_sources(ncs_root)
    bad_aliases = validate_alias_dictionary(aliases, set(codeset["ncsSubCode"].astype(str)))
    if bad_aliases:
        raise ValueError(f"aliases reference unknown NCS subcodes: {bad_aliases}")
    index = LexicalIndex.build(units, codeset)
    candidates, matches = map_observed_duties(
        duties, index, aliases, codeset, data_version=envelope.get("dataVersion", DATA_VERSION), top_k=5
    )
    processed = ncs_root / "data" / "processed" / "observed-dev" / RUN_ID
    processed.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(processed / "posting_ncs_candidates.parquet", index=False)
    matches.to_parquet(processed / "posting_ncs_matches.parquet", index=False)
    return candidates, matches, validation, envelope


def _final_exports(ncs_root: Path, duty_input_path: Path) -> tuple[list[dict[str, Any]], dict[str, int], list[str], Path]:
    candidates, matches, validation, envelope = _map_and_persist(ncs_root, duty_input_path)
    units, codeset, aliases = _load_sources(ncs_root)
    aliases = aliases.assign(
        aliasDictionaryVersion="ncs-alias-dictionary-v0.1",
        codeSetStatus="REVIEW_REQUIRED",
        dataProvenance="OBSERVED_DEVELOPMENT_ONLY",
    )
    summary = pd.DataFrame([{
        "runId": RUN_ID,
        "dutyInputRows": int(len(matches)),
        "candidateRows": int(len(candidates)),
        "mappedDevelopmentRows": int(matches["ncsSubCode"].notna().sum()),
        "unmappedRows": int(matches["ncsSubCode"].isna().sum()),
        "developmentMappedRatio": float(matches["ncsSubCode"].notna().mean()) if len(matches) else None,
        "mappingMode": "LEXICAL_BASELINE",
        "codeSetStatus": "REVIEW_REQUIRED",
        "goldValidatedFlag": False,
        "denseScore": None,
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "finalPrecisionEvaluated": False,
        "finalCoverageEvaluated": False,
    }])
    export_root = ncs_root / "data" / "exports" / "observed-dev" / RUN_ID
    frames = {
        "ncs_units": units,
        "core_ai_it_codes": codeset,
        "ncs_alias_dictionary": aliases,
        "posting_ncs_candidates": candidates,
        "posting_ncs_matches": matches,
        "ncs_mapping_summary": summary,
    }
    grains = {
        "ncs_units": "ncsUnitCode",
        "core_ai_it_codes": "ncsSubCode",
        "ncs_alias_dictionary": "alias plus ncsSubCode",
        "posting_ncs_candidates": "sectionId plus candidateRank",
        "posting_ncs_matches": "sectionId",
        "ncs_mapping_summary": "runId",
    }
    records: list[dict[str, Any]] = []
    exported_paths: dict[str, dict[str, Any]] = {}
    for stem, frame in frames.items():
        parquet_path, csv_path = _write_tabular_pair(frame, export_root, stem)
        records.extend([
            file_record(parquet_path, ncs_root, "A4-04-EXPORT", grains[stem], len(frame), len(frame.columns)),
            file_record(csv_path, ncs_root, "A4-04-EXPORT", grains[stem], len(frame), len(frame.columns)),
        ])
        exported_paths[stem] = {
            "parquet": parquet_path.relative_to(ncs_root.parent).as_posix(),
            "csv": csv_path.relative_to(ncs_root.parent).as_posix(),
            "parquetSha256": sha256_file(parquet_path),
            "csvSha256": sha256_file(csv_path),
            "rows": len(frame),
        }

    handoff_path = ncs_root.parent / "shared" / "handoffs" / "AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff = {
        "agentId": "P4-A4-NCS",
        "recipientAgentId": "P4-A2-PIPELINE",
        "handoffType": "NCS_MAPPING_OBSERVED_DEVELOPMENT",
        "status": "NCS_MAPPING_DEV_READY",
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataVersion": envelope.get("dataVersion", DATA_VERSION),
        "runMode": "observed-dev",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "mappingMode": "LEXICAL_BASELINE",
        "codeSetStatus": "REVIEW_REQUIRED",
        "goldValidatedFlag": False,
        "denseScore": None,
        "inputDutyRows": validation.row_count,
        "inputRowsSha256": validation.rows_sha256,
        "inputRowsSha256Verified": validation.rows_sha256_verified,
        "warnings": list(validation.warning_codes),
        "files": exported_paths,
        "prohibitedClaims": ["FINAL_PRECISION", "FINAL_COVERAGE", "RQ2_B", "DATA_READY_RQ2B"],
    }
    handoff["handoffSha256"] = canonical_json_sha256(handoff)
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records.append(file_record(handoff_path, ncs_root, "A4-04-EXPORT", "handoff", 1, len(handoff)))
    row_counts = {stem: len(frame) for stem, frame in frames.items()}
    return records, row_counts, list(validation.warning_codes), handoff_path


def run_stage(
    stage_id: str,
    root: str | Path | None = None,
    duty_input_path: str | Path | None = None,
    schema_dir: str | Path | None = None,
) -> dict[str, Any]:
    if stage_id not in STAGES:
        raise ValueError(f"unknown stage: {stage_id}")
    ncs_root = _root(root)
    context = StageContext(ncs_root=ncs_root, stage_id=stage_id, schema_version=STAGES[stage_id])
    units, codeset, aliases = _load_sources(ncs_root)
    ncs_sha = sha256_file(ncs_root / "data" / "processed" / "ncsUnit.parquet")
    files: list[dict[str, Any]] = []
    warnings: list[str] = []

    if stage_id == "A4-00-NCS-SOURCE":
        unique_units = int(units["ncsUnitCode"].nunique())
        level_values = sorted(units["ncsLevel"].dropna().astype(int).unique().tolist())
        quality = [
            _quality("NCS_BASE_READY", "NCS_UNIT_ROWS", "PASS" if len(units) == 13442 else "FAIL", len(units), 13442, "ncs_mapping/data/processed/ncsUnit.parquet"),
            _quality("NCS_BASE_READY", "NCS_UNIT_PK", "PASS" if unique_units == len(units) else "FAIL", unique_units, len(units), "ncs_mapping/data/processed/ncsUnit.parquet"),
            _quality("NCS_BASE_READY", "NCS_LEVEL_DOMAIN", "PASS" if level_values == list(range(1, 9)) else "FAIL", str(level_values), "[1..8]", "ncs_mapping/data/processed/ncsUnit.parquet"),
        ]
        rows = {"ncsUnit": len(units), "uniqueNcsUnitCode": unique_units}
        metrics = [_metric("ncsUnitRows", len(units), "ncsUnitCode"), _metric("ncsLevelValues", str(level_values), "ncsLevel")]
    elif stage_id == "A4-01-CODESET":
        included_count = int(codeset["included"].astype(bool).sum())
        quality = [
            _quality("NCS_CODESET_REVIEW_READY", "CODESET_TOTAL", "PASS" if len(codeset) == 120 else "FAIL", len(codeset), 120, "ncs_mapping/data/processed/coreAiItCodeSet.parquet"),
            _quality("NCS_CODESET_REVIEW_READY", "CODESET_INCLUDED", "PASS" if included_count == 69 else "FAIL", included_count, 69, "ncs_mapping/data/processed/coreAiItCodeSet.parquet"),
            _quality("NCS_CODESET_REVIEW_READY", "CODESET_STATUS", "REVIEW_REQUIRED", "REVIEW_REQUIRED", "production freeze prohibited", "ncs_mapping/configs/core_ai_it_codes.yaml"),
        ]
        rows = {"coreCodeSet": len(codeset), "included": included_count, "excluded": len(codeset) - included_count}
        metrics = [_metric("coreCodeRows", len(codeset), "ncsSubCode"), _metric("includedDevelopmentCodes", included_count, "ncsSubCode")]
    elif stage_id == "A4-02-RETRIEVAL":
        index = LexicalIndex.build(units, codeset)
        invalid_aliases = validate_alias_dictionary(aliases, set(codeset["ncsSubCode"].astype(str)))
        index_manifest_path = ncs_root / "data" / "interim" / "observed-dev" / "lexical_index_manifest.json"
        index_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        index_manifest = {
            "mappingMode": "LEXICAL_BASELINE", "documents": len(index.documents),
            "includedSubcategories": int(codeset["included"].astype(bool).sum()),
            "aliasRows": len(aliases), "sameSubcategoryRestriction": True,
            "denseRerankCalled": False, "denseScore": None,
            "codeSetStatus": "REVIEW_REQUIRED", "goldValidatedFlag": False,
        }
        index_manifest_path.write_text(json.dumps(index_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [file_record(index_manifest_path, ncs_root, stage_id, "retrieval index manifest", 1, len(index_manifest))]
        quality = [
            _quality("NCS_RETRIEVAL_READY", "INDEX_NONEMPTY", "PASS" if len(index.documents) else "FAIL", len(index.documents), ">0", "ncs_mapping/data/interim/observed-dev/lexical_index_manifest.json"),
            _quality("NCS_RETRIEVAL_READY", "ALIAS_REFERENCES", "PASS" if not invalid_aliases else "FAIL", len(invalid_aliases), 0, "ncs_mapping/configs/ncs_alias_dictionary.yaml"),
            _quality("NCS_RETRIEVAL_READY", "DENSE_DISABLED", "PASS", False, False, "ncs_mapping/data/interim/observed-dev/lexical_index_manifest.json"),
        ]
        rows = {"lexicalDocuments": len(index.documents), "aliasRows": len(aliases)}
        metrics = [_metric("lexicalDocumentRows", len(index.documents), "ncsUnitCode"), _metric("aliasRows", len(aliases), "alias")]
    elif stage_id == "A4-03-MAP-OBSERVED":
        input_path = _input_path(ncs_root, duty_input_path)
        candidates, matches, validation, _ = _map_and_persist(ncs_root, input_path)
        warnings = list(validation.warning_codes)
        processed = ncs_root / "data" / "processed" / "observed-dev" / RUN_ID
        files = [
            file_record(processed / "posting_ncs_candidates.parquet", ncs_root, stage_id, "sectionId plus candidateRank", len(candidates), len(candidates.columns)),
            file_record(processed / "posting_ncs_matches.parquet", ncs_root, stage_id, "sectionId", len(matches), len(matches.columns)),
        ]
        max_candidates = int(candidates.groupby("sectionId").size().max()) if len(candidates) else 0
        same_sub_ok = bool(candidates.empty or candidates.loc[candidates["matchedNcsUnitCode"].notna()].apply(
            lambda row: str(row["matchedNcsUnitCode"]).startswith(str(row["ncsSubCode"])), axis=1
        ).all())
        quality = [
            _quality("NCS_MAPPING_DEV_READY", "INPUT_ROWS_RECOMPUTED", "PASS", validation.row_count, len(matches), "ncs_mapping/data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/posting_ncs_matches.parquet"),
            _quality("NCS_MAPPING_DEV_READY", "TOP5_CAP", "PASS" if max_candidates <= 5 else "FAIL", max_candidates, "<=5", "ncs_mapping/data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/posting_ncs_candidates.parquet"),
            _quality("NCS_MAPPING_DEV_READY", "UNMAPPED_PRESERVED", "PASS" if len(matches) == validation.row_count else "FAIL", len(matches), validation.row_count, "ncs_mapping/data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/posting_ncs_matches.parquet"),
            _quality("NCS_MAPPING_DEV_READY", "SAME_SUBCATEGORY", "PASS" if same_sub_ok else "FAIL", same_sub_ok, True, "ncs_mapping/data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/posting_ncs_candidates.parquet"),
            _quality("NCS_MAPPING_DEV_READY", "INPUT_ROWS_SHA_DECLARED", "PASS" if validation.rows_sha256_verified else "REVIEW_REQUIRED", validation.rows_sha256_verified, True, "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"),
        ]
        rows = {"dutyInput": validation.row_count, "postingNcsCandidates": len(candidates), "postingNcsMatches": len(matches)}
        metrics = [_metric("dutyInputRows", validation.row_count, "sectionId"), _metric("candidateRows", len(candidates), "sectionId plus candidateRank"), _metric("unmappedRows", int(matches["ncsSubCode"].isna().sum()), "sectionId")]
        ncs_sha = validation.rows_sha256
    else:
        input_path = _input_path(ncs_root, duty_input_path)
        files, rows, warnings, handoff_path = _final_exports(ncs_root, input_path)
        quality = [
            _quality("NCS_MAPPING_EXPORT_READY", "CSV_PARQUET_SEMANTIC_EQUALITY", "PASS", True, True, "ncs_mapping/data/exports/observed-dev/NCS_MAPPING_OBSERVED_20260806_01"),
            _quality("NCS_MAPPING_EXPORT_READY", "HANDOFF_PRESENT", "PASS" if handoff_path.exists() else "FAIL", handoff_path.exists(), True, "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"),
            _quality("NCS_MAPPING_EXPORT_READY", "PRODUCTION_PROMOTION", "REVIEW_REQUIRED", False, False, "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"),
        ]
        metrics = [_metric(f"{name}Rows", count, name) for name, count in rows.items()]
        _, validation, _ = load_and_validate_observed_duties(input_path)
        ncs_sha = validation.rows_sha256

    return write_stage_artifacts(
        context=context, input_manifest_sha256=ncs_sha,
        row_counts={key: int(value) for key, value in rows.items()}, metrics=metrics,
        quality_rows=quality, business_files=files, warnings=warnings,
        schema_dir=_schema_dir(ncs_root, schema_dir),
    )
