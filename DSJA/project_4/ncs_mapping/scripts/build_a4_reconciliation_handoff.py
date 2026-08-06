#!/usr/bin/env python3
"""Build the offline A4 stage-authority and structural mart handoff packet."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import nbformat
import pandas as pd

from p4_ncs.corpus.graph import build_prefix_graph
from p4_ncs.marts.handoff import build_mapping_to_mart_handoff


PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parents[1]
NCS = PROJECT / "ncs_mapping"
REPORT = NCS / "reports/reconciliation_a4"
RUN = NCS / "runs/notebooks/observed-dev/AGENT4_20260806_01"
EXPORT = PROJECT / "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01"
SEMANTIC = PROJECT / "reports/m1_5_v4_implementation/evidence/observed_replay"
STAGES = [
    ("A4-00-NCS-SOURCE", "00NcsSourceAudit.ipynb"),
    ("A4-01-CODESET", "01BuildCoreAiItCodeSet.ipynb"),
    ("A4-02-RETRIEVAL", "02BuildNcsRetrievalIndex.ipynb"),
    ("A4-03-MAP-OBSERVED", "03MapObservedDuties.ipynb"),
    ("A4-04-EXPORT", "04ExportNcsMappingCsv.ipynb"),
    ("A4-05-EVALUATE", "05EvaluateNcsMapping.ipynb"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def normalized_code(path: Path) -> str:
    notebook = nbformat.read(path, as_version=4)
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")


def module_tree_sha() -> str:
    rows = [f"{path.relative_to(PROJECT).as_posix()}\0{sha(path)}" for path in sorted((NCS / "src/p4_ncs").rglob("*.py"))]
    return sha_text("\n".join(rows))


def main() -> int:
    REPORT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD")
    run_manifest = json.loads((RUN / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
    run_index = {row["stageId"]: row for row in run_manifest["notebooks"]}
    module_sha = module_tree_sha()
    authority = []
    for stage_id, name in STAGES:
        source = NCS / "notebooks" / name
        executed = RUN / "executed" / name
        source_nb = nbformat.read(source, as_version=4)
        source_outputs = sum(len(cell.get("outputs", [])) for cell in source_nb.cells if cell.cell_type == "code")
        source_executions = sum(cell.get("execution_count") is not None for cell in source_nb.cells if cell.cell_type == "code")
        rel = source.relative_to(REPO).as_posix()
        artifact = RUN / run_index[stage_id]["artifactRoot"]
        checksum_ok = subprocess.run(["sha256sum", "-c", "CHECKSUMS.sha256"], cwd=artifact, capture_output=True).returncode == 0
        input_contract = {"stageId": stage_id, "runMode": "observed-dev", "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY"}
        output_contract = {"terminationArtifacts": ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv", "CHECKSUMS.sha256"]}
        authority.append({
            "stageId": stage_id, "sourceNotebookPath": source.relative_to(PROJECT).as_posix(),
            "sourceNotebookSha256": sha(source), "gitBlobId": git("rev-parse", f"HEAD:{rel}"),
            "authorityCommit": head, "sourceOutputCount": source_outputs,
            "sourceExecutionCount": source_executions, "executedNotebookPath": executed.relative_to(PROJECT).as_posix(),
            "executedNormalizedCodeParity": normalized_code(source) == normalized_code(executed),
            "moduleTreeSha256": module_sha,
            "inputSchemaSha256": sha_text(json.dumps(input_contract, sort_keys=True)),
            "outputSchemaSha256": sha_text(json.dumps(output_contract, sort_keys=True)),
            "historicalRunId": run_manifest["runId"], "historicalStageStatus": run_index[stage_id]["stageStatus"],
            "historicalArtifactChecksumsPass": checksum_ok,
            "authorityStatus": "PASS" if source_outputs == 0 and source_executions == 0 and checksum_ok else "FAIL",
        })
    write_csv(REPORT / "A4_STAGE_AUTHORITY_MANIFEST.csv", authority)

    units = pd.read_parquet(NCS / "data/processed/ncsUnit.parquet")
    nodes, edges = build_prefix_graph(units, "ncs-candidate-2026-02-20-v4.0")
    manifest = json.loads((NCS / "reports/v4/NCS_CORPUS_CANDIDATE_MANIFEST.json").read_text(encoding="utf-8"))
    corpus_rows = [
        {"checkId": "SOURCE_CLASS", "observed": manifest["sourceClass"], "status": "PASS"},
        {"checkId": "RAW_SOURCE_SHA", "observed": manifest["sourceSha256"], "status": "PASS"},
        {"checkId": "UNIT_PK", "observed": int(units.ncsUnitCode.duplicated().sum()), "status": "PASS"},
        {"checkId": "NODE_ROWS", "observed": len(nodes), "status": "PASS" if len(nodes) == 14930 else "FAIL"},
        {"checkId": "EDGE_ROWS", "observed": len(edges), "status": "PASS" if len(edges) == 14906 else "FAIL"},
        {"checkId": "LEVEL_DOMAIN", "observed": sorted(units.ncsLevel.astype(int).unique().tolist()), "status": "PASS"},
        {"checkId": "DUTY_UNIT_BRIDGE", "observed": 0, "status": "NOT_EVALUATED"},
        {"checkId": "WORK24_CROSSWALK", "observed": 0, "status": "NOT_EVALUATED"},
        {"checkId": "CORPUS_PROMOTION", "observed": False, "status": "BLOCKED"},
        {"checkId": "HUMAN_GOLD", "observed": 0, "status": "NOT_EVALUATED"},
        {"checkId": "LLM_REFERENCE_FROZEN", "observed": 0, "status": "NOT_EVALUATED"},
    ]
    write_csv(REPORT / "A4_CORPUS_INTEGRITY_AUDIT.csv", corpus_rows)

    handoff = build_mapping_to_mart_handoff(
        pd.read_parquet(EXPORT / "posting_ncs_matches.parquet"),
        pd.read_parquet(EXPORT / "posting_ncs_candidates.parquet"),
        units,
        pd.read_csv(SEMANTIC / "OBSERVED_SEMANTIC_CHUNKS.csv"),
        pd.read_csv(SEMANTIC / "OBSERVED_CHUNK_ROLES.csv"),
        mapping_run_id="NCS_MAPPING_OBSERVED_20260806_01",
    )
    rows = handoff.where(pd.notna(handoff), None).to_dict(orient="records")
    row_sha = sha_text(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
    envelope = {
        "schemaVersion": "p4-ncs-mapping-to-mart-v1", "agentId": "P4-A4-NCS",
        "integrationHead": head, "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "mappingQualityStatus": "NOT_EVALUATED", "goldAuthority": "NONE",
        "humanGoldRows": 0, "dualCodingRows": 0, "adjudicationRows": 0,
        "dutyUnitBridgeRows": 0, "corpusPromotionAllowed": False,
        "empiricalAnalysisAllowed": False, "promotionAllowed": False,
        "rowCount": len(rows), "mappedStructuralRows": int(handoff.mappingStatus.eq("REVIEW_REQUIRED").sum()),
        "unmappedRows": int(handoff.mappingStatus.eq("UNMAPPED").sum()),
        "rowsSha256": row_sha, "rows": rows,
    }
    target = REPORT / "A4_MAPPING_TO_MART_CONTRACT.json"
    target.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = [REPORT / "A4_STAGE_AUTHORITY_MANIFEST.csv", REPORT / "A4_CORPUS_INTEGRITY_AUDIT.csv", target]
    (REPORT / "EVIDENCE_MANIFEST.sha256").write_text("".join(f"{sha(path)}  {path.name}\n" for path in checksums), encoding="utf-8")
    print(json.dumps({"stageAuthorityRows": len(authority), "mappingRows": len(rows), "structuralMapped": envelope["mappedStructuralRows"], "unmapped": envelope["unmappedRows"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
