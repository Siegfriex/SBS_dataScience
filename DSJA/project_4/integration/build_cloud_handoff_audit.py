#!/usr/bin/env python3
"""Build the fail-closed P4 post-implementation cloud handoff audit."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
REPORT = PROJECT / "reports" / "m1_5_v4_implementation"
EXPORT = PROJECT / "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01"
CRAWL_HANDOFF = Path(
    os.environ.get(
        "P4_CRAWL_HANDOFF_REPORT_ROOT",
        PROJECT / "crawl/reports/m1_5_control_patch",
    )
)
BASE = "aec8dfcb4cb6d57efc5a351874c2c32ba69abc0a"
BRANCH = "audit/p4-m1_5-cloud-handoff-v1"
CRAWL_BRANCH = "agent/p4-crawl-m1_5-control-patch-v4"
CRAWL_BRANCH_HEAD = "2d3f48025352359acf5787efeb79c0111fdea9f7"
CRAWL_AUDITED_HEAD = "23b242da31c63687cc100af0603dacc7b4bafe2c"
RUN_ID = "P4_CLOUD_HANDOFF_AUDIT_20260806_01"
DATA_VERSION = "observed-dev-20260806.1"
SSOT_SHA = "409866c166ce3874ce587ad3b1230bc530c036e9682be01bf3466aa1fd37a05a"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    audit_head = git("rev-parse", "HEAD")
    frames = {name: pd.read_parquet(EXPORT / f"{name}.parquet") for name in [
        "posting_normalized", "posting_tracks", "posting_sections", "requirement_facts",
        "career_access_labels", "posting_ncs_candidates", "posting_ncs_matches",
        "preprocessed_posting_tracks",
    ]}
    pre = frames["preprocessed_posting_tracks"]
    semantic = pd.read_csv(REPORT / "evidence/observed_replay/OBSERVED_SEMANTIC_POSTINGS.csv")
    manifest_sha = sha(EXPORT / "stage_manifest.json")

    crawl_rows = [
        ("crawl patch manifest", "CRAWL_M1_5_PATCH_MANIFEST.json", 1, "PASS", "checksum PASS; audited code HEAD differs from packet branch HEAD by report-only commits"),
        ("validator negative test evidence", "CRAWL_VALIDATOR_NEGATIVE_TESTS.csv", 18, "PASS", "18 rejection cases evidenced"),
        ("current-run manifest audit", "CRAWL_CURRENT_RUN_MANIFEST_AUDIT.csv", 23, "PARTIAL", "A1 exact-one 5/5; downstream exact-one 0/18"),
        ("DAG order proof", "CRAWL_STAGE_TOPOLOGICAL_ORDER.csv", 23, "PASS", "23 stages; 28 edges; cycle/order violation 0"),
        ("raw/posting binding audit", "CRAWL_RAW_POSTING_BINDING_AUDIT.csv", 29, "PASS_WITH_FINDINGS", "29/29 SHA and bytes match; posting flag drift 18"),
        ("fresh observed replay summary", "CRAWL_REPLAY_SUMMARY.csv", 6, "PARTIAL", "00-03 PASS; release and Master EXPECTED_BLOCKED"),
        ("source Notebook blob manifest", "CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv", 6, "PASS", "handoff branch 6/6 blob parity; integration Notebook SHA match 0/6"),
    ]
    consumption = []
    for item, filename, rows, status, finding in crawl_rows:
        path = CRAWL_HANDOFF / filename
        consumption.append({
            "item": item, "crawlHandoffBranch": CRAWL_BRANCH, "crawlBranchHead": CRAWL_BRANCH_HEAD,
            "crawlAuditedCommit": CRAWL_AUDITED_HEAD, "artifact": f"crawl/reports/m1_5_control_patch/{filename}",
            "artifactSha256": sha(path), "rows": rows, "artifactStatus": status,
            "integrationConsumptionStatus": "EVIDENCE_INSUFFICIENT", "finding": finding,
        })
    write_csv(REPORT / "P4_M1_5_CRAWL_HANDOFF_CONSUMPTION.csv", consumption)

    contract_rows = [
        {"checkId": "CONTRACT-CHECKSUM", "scope": "P4_CONTRACT_v2.1.2", "expected": "11 checksum-listed files", "observed": "11 present; 11 checksum PASS", "status": "PASS", "evidence": "shared/contracts/P4_CONTRACT_v2.1.2/CHECKSUMS.sha256"},
        {"checkId": "SEMANTIC-SCHEMAS", "scope": "semantic_ncs_reference/v4.0", "expected": "12 Draft 2020-12 schemas", "observed": "12 present; validator PASS", "status": "PASS", "evidence": "shared/contracts/semantic_ncs_reference/v4.0/schemas"},
        {"checkId": "HANDOFF-RESTORE", "scope": "shared handoffs", "expected": "contract and consumer handoffs present", "observed": "2 contract handoffs and 10 shared handoffs tracked", "status": "PASS", "evidence": "shared/contracts/P4_CONTRACT_v2.1.2; shared/handoffs"},
        {"checkId": "STAGE-REGISTRY", "scope": "integration/report", "expected": "byte-identical registry", "observed": "6 stages; 26 gates; 11 edges; report copy identical", "status": "PASS", "evidence": "integration/SEMANTIC_STAGE_REGISTRY.yaml"},
        {"checkId": "EXPORT-CONTRACT", "scope": "observed canonical export", "expected": "postingKind enum valid and canonicalPostedAt non-null", "observed": "postingKind invalid 137; canonicalPostedAt null 137", "status": "FAIL", "evidence": "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01/preprocessed_posting_tracks.parquet"},
        {"checkId": "SEMANTIC-CONSUMPTION", "scope": "recovery to canonical export", "expected": "recovery values consumed with provenance", "observed": "recovery has valid enum 137 and date 29; canonical export consumes neither", "status": "BLOCKED", "evidence": "reports/m1_5_v4_implementation/evidence/observed_replay/OBSERVED_SEMANTIC_POSTINGS.csv"},
        {"checkId": "MANIFEST-HEAD", "scope": "authority chain", "expected": "branch/source SHA bound to one manifest HEAD", "observed": "observed manifest gitHead=17a9055; integration base=aec8dfc; crawl audited=23b242d", "status": "BLOCKED", "evidence": "pipeline/data/exports/observed-dev/OBSERVED_DEV_20260806_01/stage_manifest.json"},
        {"checkId": "RAW-PROMOTION", "scope": "untracked authority", "expected": "untracked bytes excluded from promotion evidence", "observed": "29 raw bytes verified only from separate local worktree; Git audit worktree contains 0", "status": "BLOCKED", "evidence": "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/raw_detail_manifest.jsonl"},
        {"checkId": "WAREHOUSE-SEPARATION", "scope": "DuckDB", "expected": "p4.duckdb production and p4.observed-dev.duckdb observed kept separate", "observed": "both absent; p4.development.duckdb is a 6-row fixture warehouse", "status": "PASS_WITH_FINDINGS", "evidence": "pipeline/data/warehouse/p4.development.duckdb"},
        {"checkId": "HISTORICAL-STAGE-ARTIFACTS", "scope": "reports/m1_5_v4_implementation/stages", "expected": "historical artifacts not treated as current audit authority", "observed": "stage artifacts retain M1_5_V4_IMPLEMENTATION_20260806_01 and are excluded from the cloud evidence manifest", "status": "PASS_WITH_FINDINGS", "evidence": "reports/m1_5_v4_implementation/stages"},
        {"checkId": "SUPERSEDE-DECISION", "scope": "earlier implementation audit", "expected": "versioned supersede decision", "observed": "P4_M1_5_CLOUD_HANDOFF_MANIFEST.json supersedes earlier readiness wording for promotion decisions; source files retained", "status": "PASS", "evidence": "reports/m1_5_v4_implementation/P4_M1_5_CLOUD_HANDOFF_MANIFEST.json"},
    ]
    write_csv(REPORT / "P4_M1_5_CONTRACT_RECONCILIATION.csv", contract_rows)

    code_sha = {
        "semantic": sha(PROJECT / "pipeline/src/p4/normalize/semantic_recovery.py"),
        "requirements": sha(PROJECT / "pipeline/src/p4/parse/requirements.py"),
        "rq2b": sha(PROJECT / "pipeline/src/p4/marts/rq2b.py"),
        "ncs": sha(PROJECT / "ncs_mapping/src/p4_ncs/corpus/graph.py"),
    }
    lineage = [
        {"edgeId": "L01", "edge": "raw→normalized", "key": "sourcePostingId", "inputRows": 29, "outputRows": 137, "matchedRows": 29, "lossRows": 0, "orphanRows": 108, "duplicateRows": 0, "sourceSha256": "f12680f1d598f70df576f0af4743c5e9c49df7caf16eccb1d898bded5eb3dfbe", "codeSha256": code_sha["semantic"], "dataVersion": DATA_VERSION, "runId": RUN_ID, "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "raw bytes untracked; recovery output not consumed by canonical export"},
        {"edgeId": "L02", "edge": "normalized→track", "key": "postingId", "inputRows": 137, "outputRows": 137, "matchedRows": 137, "lossRows": 0, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_normalized.parquet"), "codeSha256": sha(PROJECT / "pipeline/src/p4/normalize/tracks.py"), "dataVersion": DATA_VERSION, "runId": "OBSERVED_DEV_20260806_01-A2-11-EXPORT-QA", "manifestSha256": manifest_sha, "status": "PASS", "finding": "structural join proven"},
        {"edgeId": "L03", "edge": "track→section", "key": "trackId", "inputRows": 137, "outputRows": 84, "matchedRows": 84, "lossRows": 109, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_tracks.parquet"), "codeSha256": sha(PROJECT / "pipeline/src/p4/parse/sections.py"), "dataVersion": DATA_VERSION, "runId": "OBSERVED_DEV_20260806_01-A2-11-EXPORT-QA", "manifestSha256": manifest_sha, "status": "PASS_WITH_FINDINGS", "finding": "84 sections belong to 28 tracks; 109 tracks have no section"},
        {"edgeId": "L04", "edge": "section→requirement", "key": "sectionId", "inputRows": 84, "outputRows": 35, "matchedRows": 35, "lossRows": 56, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_sections.parquet"), "codeSha256": code_sha["requirements"], "dataVersion": DATA_VERSION, "runId": RUN_ID, "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "canonical export has 35 facts; v4 replay produces 41 and is not consumed"},
        {"edgeId": "L05", "edge": "requirement→eligibility", "key": "sectionId→trackId→postingId", "inputRows": 35, "outputRows": 137, "matchedRows": 35, "lossRows": 0, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "requirement_facts.parquet"), "codeSha256": sha(PROJECT / "pipeline/src/p4/label/career.py"), "dataVersion": DATA_VERSION, "runId": "OBSERVED_DEV_20260806_01-A2-11-EXPORT-QA", "manifestSha256": manifest_sha, "status": "BLOCKED", "finding": "structural FK passes; canonical time/entity contract fails"},
        {"edgeId": "L06", "edge": "eligibility→NCS candidate", "key": "trackId", "inputRows": 55, "outputRows": 128, "matchedRows": 27, "lossRows": 28, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "career_access_labels.parquet"), "codeSha256": sha(PROJECT / "ncs_mapping/src/p4_ncs/retrieval/candidate_retrieval.py"), "dataVersion": DATA_VERSION, "runId": "OBSERVED_DEV_20260806_01-A2-11-EXPORT-QA", "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "55 eligible tracks but candidates cover 27"},
        {"edgeId": "L07", "edge": "candidate→mapping/abstain", "key": "trackId+sectionId", "inputRows": 128, "outputRows": 28, "matchedRows": 27, "lossRows": 0, "orphanRows": 1, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_ncs_candidates.parquet"), "codeSha256": sha(PROJECT / "ncs_mapping/src/p4_ncs/mapping/observed_baseline.py"), "dataVersion": DATA_VERSION, "runId": "OBSERVED_DEV_20260806_01-A2-11-EXPORT-QA", "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "27 mapped + 1 unmapped; 27 eligible tracks have no explicit decision row"},
        {"edgeId": "L08", "edge": "mapping→level/band", "key": "matchedNcsUnitCode→ncsUnitCode", "inputRows": 27, "outputRows": 0, "matchedRows": 27, "lossRows": 27, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_ncs_matches.parquet"), "codeSha256": code_sha["ncs"], "dataVersion": DATA_VERSION, "runId": RUN_ID, "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "all 27 codes official; canonical mart level/band remains null"},
        {"edgeId": "L09", "edge": "level/band→mart", "key": "trackId", "inputRows": 27, "outputRows": 0, "matchedRows": 0, "lossRows": 27, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": sha(EXPORT / "posting_ncs_matches.parquet"), "codeSha256": code_sha["rq2b"], "dataVersion": DATA_VERSION, "runId": RUN_ID, "manifestSha256": manifest_sha, "status": "LINEAGE_UNPROVEN", "finding": "RQ2-B implementation tested; empirical mart not built"},
        {"edgeId": "L10", "edge": "mart→RQ dataset", "key": "periodMonth+jobCohort+sourceRole", "inputRows": 0, "outputRows": 0, "matchedRows": 0, "lossRows": 0, "orphanRows": 0, "duplicateRows": 0, "sourceSha256": "NOT_AVAILABLE", "codeSha256": code_sha["rq2b"], "dataVersion": DATA_VERSION, "runId": RUN_ID, "manifestSha256": manifest_sha, "status": "BLOCKED", "finding": "no empirical RQ dataset; empty evidence is NOT_EVALUATED"},
    ]
    write_csv(REPORT / "P4_M1_5_DATA_LINEAGE.csv", lineage)

    ncs_manifest = json.loads((PROJECT / "ncs_mapping/reports/v4/NCS_CORPUS_CANDIDATE_MANIFEST.json").read_text())
    ncs_rows = [
        {"checkId": "NCS-SOURCE-BINDING", "layer": "source", "implementation": "PASS", "execution": "PASS", "evaluation": "PASS", "rows": 13442, "status": "PASS", "evidence": f"raw source SHA={ncs_manifest['sourceSha256']}; normalized SHA={ncs_manifest['normalizedArtifactSha256']}"},
        {"checkId": "NCS-CORPUS-RELEASE", "layer": "corpus", "implementation": "PASS", "execution": "PASS", "evaluation": "NOT_EVALUATED", "rows": 13442, "status": "PASS_WITH_FINDINGS", "evidence": "candidate manifest; promotionAllowed=false; parserVersion absent"},
        {"checkId": "NCS-HIERARCHY", "layer": "graph", "implementation": "PASS", "execution": "PASS", "evaluation": "PASS", "rows": 14930, "status": "PASS", "evidence": "14930 nodes; 14906 edges; level 1..8 and band tests PASS"},
        {"checkId": "NCS-DUTY-UNIT-BRIDGE", "layer": "bridge", "implementation": "PASS", "execution": "NOT_EVALUATED", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "NOT_EVALUATED", "evidence": "no duty-unit bridge rows"},
        {"checkId": "WORK24-CROSSWALK", "layer": "crosswalk", "implementation": "PASS", "execution": "NOT_EVALUATED", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "NOT_EVALUATED", "evidence": "MATCHED/UNMATCHED/AMBIGUOUS/INVALID schema implemented; no rows"},
        {"checkId": "R0", "layer": "alias exact", "implementation": "PASS", "execution": "FIXTURE_ONLY", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "PARTIAL", "evidence": "hybrid.py aliasExact tests"},
        {"checkId": "R1", "layer": "char TF-IDF 3-5", "implementation": "PASS", "execution": "FIXTURE_ONLY", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "PARTIAL", "evidence": "feature contract tests"},
        {"checkId": "R2", "layer": "word TF-IDF 1-2/BM25", "implementation": "PASS", "execution": "FIXTURE_ONLY", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "PARTIAL", "evidence": "BM25 unit tests"},
        {"checkId": "R3", "layer": "dense reranker", "implementation": "PARTIAL", "execution": "NOT_EVALUATED", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "NOT_EVALUATED", "evidence": "adapter fails closed; pinned model absent"},
        {"checkId": "R4", "layer": "crosswalk/hierarchy backoff", "implementation": "PASS", "execution": "FIXTURE_ONLY", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "PARTIAL", "evidence": "hierarchy fixture test; Work24 rows 0"},
        {"checkId": "R5", "layer": "reference/calibration selection", "implementation": "PASS", "execution": "NOT_EVALUATED", "evaluation": "NOT_EVALUATED", "rows": 0, "status": "NOT_EVALUATED", "evidence": "no HUMAN_GOLD or LLM_REFERENCE release"},
    ]
    write_csv(REPORT / "P4_M1_5_NCS_CORPUS_AUDIT.csv", ncs_rows)
    gold_rows = [
        {"labelAuthority": "HUMAN_GOLD", "rowCount": 0, "dualCodingCount": 0, "adjudicationCount": 0, "metricStatus": "NOT_EVALUATED", "precision": "", "recall": "", "f1": "", "coverage": "", "status": "NOT_EVALUATED", "evidence": "ncs_mapping/data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv"},
        {"labelAuthority": "LLM_REFERENCE_FROZEN", "rowCount": 0, "dualCodingCount": 0, "adjudicationCount": 0, "metricStatus": "NOT_EVALUATED", "precision": "", "recall": "", "f1": "", "coverage": "", "status": "NOT_EVALUATED", "evidence": "reference schema only; no release"},
        {"labelAuthority": "MODEL_ACCEPTED", "rowCount": 0, "dualCodingCount": 0, "adjudicationCount": 0, "metricStatus": "NOT_EVALUATED", "precision": "", "recall": "", "f1": "", "coverage": "", "status": "NOT_EVALUATED", "evidence": "never auto-promoted to reference"},
    ]
    write_csv(REPORT / "P4_M1_5_GOLD_STATUS.csv", gold_rows)

    test_rows = [
        {"suiteId": "T-CRAWL-INTEGRATION", "command": "PYTHONPATH=src python -m pytest -q control/tests tests", "workdir": "crawl", "passed": 37, "failed": 1, "exitCode": 1, "status": "FAIL", "finding": "Git-only worktree lacks 29 ignored raw files"},
        {"suiteId": "T-CRAWL-HANDOFF", "command": "P4_CRAWL_RAW_SOURCE_ROOT=<local-crawl-root> PYTHONPATH=crawl/src:. python -m pytest crawl/tests crawl/control/tests -q -rs", "workdir": "crawl handoff branch", "passed": 64, "failed": 0, "exitCode": 0, "status": "PASS_WITH_FINDINGS", "finding": "independently rerun with explicit local raw mount; raw remains excluded from Git"},
        {"suiteId": "T-PIPELINE", "command": "PYTHONPATH=src python -m pytest -q", "workdir": "pipeline", "passed": 116, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "canonical artifact semantic defects remain outside test gate"},
        {"suiteId": "T-NCS", "command": "PYTHONPATH=src python -m pytest -q", "workdir": "ncs_mapping", "passed": 84, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "real reference evaluation NOT_EVALUATED"},
        {"suiteId": "T-INTEGRATION", "command": "python -m pytest -q integration/tests", "workdir": "project_4", "passed": 10, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "control implementation only"},
        {"suiteId": "T-CONTROL-VALIDATOR", "command": "python integration/validate_m1_5_control.py", "workdir": "project_4", "passed": 1, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "12 schemas; 6 endpoints; 6 stages; 26 gates; 11 edges"},
        {"suiteId": "T-CONTRACT-CHECKSUM", "command": "sha256sum -c CHECKSUMS.sha256", "workdir": "shared/contracts/P4_CONTRACT_v2.1.2", "passed": 11, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "all contract artifacts present"},
        {"suiteId": "T-CSV-PARQUET", "command": "schema-aware pandas equality audit", "workdir": "observed export", "passed": 8, "failed": 0, "exitCode": 0, "status": "PASS_WITH_FINDINGS", "finding": "ncsSubCode requires schema-aware string dtype to avoid float inference"},
        {"suiteId": "T-PK-FK", "command": "key-level pandas audit", "workdir": "observed export", "passed": 17, "failed": 0, "exitCode": 0, "status": "PASS", "finding": "8 PK and 9 FK checks; duplicate/orphan 0"},
    ]
    write_csv(REPORT / "P4_M1_5_TEST_SUMMARY.csv", test_rows)

    components = [
        {"component": "crawl handoff", "implementationStatus": "PASS", "executionStatus": "PARTIAL", "evaluationStatus": "PARTIAL", "promotionStatus": "BLOCKED", "headCommit": CRAWL_BRANCH_HEAD, "auditedCommit": CRAWL_AUDITED_HEAD, "finding": "mandatory packet present; not consumed by integration; three P1 blockers"},
        {"component": "pipeline", "implementationStatus": "PASS", "executionStatus": "PASS_WITH_FINDINGS", "evaluationStatus": "FAIL", "promotionStatus": "BLOCKED", "headCommit": "879b2c2e2cf3ba3f3cdc8f0847e607f045e2b839", "auditedCommit": BASE, "finding": "116 tests pass; canonical export enum/time recovery not integrated"},
        {"component": "control/contracts", "implementationStatus": "PASS", "executionStatus": "PASS", "evaluationStatus": "PARTIAL", "promotionStatus": "BLOCKED", "headCommit": "b20bdf5403fd679aaa0341cab7f0d5718c330124", "auditedCommit": BASE, "finding": "registry valid; authority heads diverge"},
        {"component": "ncs_mapping", "implementationStatus": "PASS", "executionStatus": "PARTIAL", "evaluationStatus": "NOT_EVALUATED", "promotionStatus": "BLOCKED", "headCommit": "3396eb66f6f9af80d0458ab8c5431b1c5ce6414c", "auditedCommit": BASE, "finding": "corpus candidate built; bridge/crosswalk/gold/calibration absent"},
        {"component": "cloud handoff audit", "implementationStatus": "PASS", "executionStatus": "PASS", "evaluationStatus": "PARTIAL", "promotionStatus": "BLOCKED", "headCommit": audit_head, "auditedCommit": BASE, "finding": "cross-component lineage unproven; claimed status PARTIAL"},
    ]
    write_csv(REPORT / "P4_M1_5_COMPONENT_STATUS.csv", components)

    gates = pd.read_csv(REPORT / "P4_M1_5_GATE_STATUS.csv")
    updates = {
        "OBSERVED_SNAPSHOT_FROZEN": ("BLOCKED", "manifest HEADs diverge; v4 recovery not consumed"),
        "MASTER_ORCHESTRATION_PATCHED": ("PASS_WITH_FINDINGS", "code proof exists; full 23-stage current-run execution absent"),
        "CURRENT_RUN_ARTIFACT_BOUND": ("BLOCKED", "A1 5/5 exact-one; downstream 0/18"),
        "TIME_SEMANTICS_READY": ("BLOCKED", "canonical export date 0/137; separate recovery 29/137"),
        "CANONICAL_ENUM_READY": ("BLOCKED", "canonical export postingKind invalid 137/137"),
        "RAW_LINEAGE_READY": ("BLOCKED", "29 raw hashes verify externally; untracked bytes and flag drift 18"),
        "DETERMINISTIC_SEMANTIC_BASE_READY": ("BLOCKED", "implementation/replay exists but canonical export does not consume it"),
        "NCS_CANONICAL_CORPUS_READY": ("BLOCKED", "candidate corpus bound; parserVersion, bridge and crosswalk missing"),
    }
    for gate, (status, evidence) in updates.items():
        gates.loc[gates.gateId.eq(gate), ["status", "evidence"]] = [status, evidence]
    gates["runId"] = RUN_ID
    gates.to_csv(REPORT / "P4_M1_5_GATE_STATUS.csv", index=False)

    defects = [
        ("P1-CLOUD-001", "crawl audited handoff source differs from integration in 88 crawl paths and 6/6 Notebook bytes"),
        ("P1-CLOUD-002", "current-run exact-one authority is A1 5/5 but downstream 0/18"),
        ("P1-CLOUD-003", "immutable release HANDOFF lacks head, source Notebook SHA and validator artifact SHA"),
        ("P1-CLOUD-004", "pipeline does not consume ActivityText fallback contract/evidence fields"),
        ("P1-CLOUD-005", "canonical export has invalid postingKind 137 and canonicalPostedAt null 137"),
        ("P1-CLOUD-006", "p4.observed-dev.duckdb is absent; p4.development.duckdb is only a 6-row fixture"),
        ("P1-CLOUD-007", "55 eligible tracks yield 28 decision rows; level/band propagated rows are 0"),
        ("P1-CLOUD-008", "HUMAN_GOLD, dual coding and adjudication counts are 0"),
        ("P1-CLOUD-009", "29 raw bytes are untracked local authority and unavailable in Git-only worktree"),
        ("P1-CLOUD-010", "NCS corpus manifest lacks parserVersion; duty bridge and Work24 crosswalk have 0 rows"),
        ("P1-CLOUD-011", "canonical requirement facts 35 differ from v4 recovered facts 41"),
    ]
    defect_rows = [{"defectId": i, "severity": "P1", "status": "OPEN", "finding": f, "downstreamGate": "BLOCKED", "evidence": "see reconciliation/lineage/crawl/NCS audit"} for i, f in defects]
    write_csv(REPORT / "P4_M1_5_DEFECT_REGISTER.csv", defect_rows)

    # API, temporal and RQ2-B files remain factual; add explicit execution boundaries.
    api = pd.read_csv(REPORT / "P4_M1_5_API_CONTRACT_STATUS.csv")
    api["implementationStatus"] = "PASS"
    api["executionStatus"] = "NOT_EVALUATED"
    api["evaluationStatus"] = "NOT_EVALUATED"
    api.to_csv(REPORT / "P4_M1_5_API_CONTRACT_STATUS.csv", index=False)

    rq = pd.read_csv(REPORT / "P4_M1_5_RQ2B_AGGREGATION_AUDIT.csv")
    rq["lineageStatus"] = ["PASS", "PASS", "PASS", "PASS", "PASS", "BLOCKED"]
    rq["empiricalClaimAllowed"] = False
    rq.to_csv(REPORT / "P4_M1_5_RQ2B_AGGREGATION_AUDIT.csv", index=False)

    report_text = f"""# P4 Project-Wide Post-Implementation Audit & Cloud Handoff

## Verdict

`PARTIAL`

The implementation modules are testable, but the cloud handoff cannot promote data or analysis gates. The current integration commit `{BASE}` has not consumed the independently audited crawl handoff source at `{CRAWL_AUDITED_HEAD}`. Canonical observed exports also do not consume the v4 semantic recovery output.

## Authority chain

- agentId: `P4-PROJECTWIDE-IMPLEMENTATION-ORCHESTRATOR`
- audit branch: `{BRANCH}`
- audited integration base: `{BASE}`
- crawl handoff branch/head: `{CRAWL_BRANCH}` / `{CRAWL_BRANCH_HEAD}`
- crawl audited code commit: `{CRAWL_AUDITED_HEAD}`
- dataVersion: `{DATA_VERSION}`
- runId: `{RUN_ID}`
- SSOT SHA-256: `{SSOT_SHA}`

## Crawl consumption verdict

`EVIDENCE_INSUFFICIENT`

All seven mandatory handoff artifacts exist and checksum correctly. Nevertheless, full current-run authority is only 5/23 stages, the immutable release handoff has three missing provenance values, and the integration checkout differs from the audited crawl handoff in 88 crawl paths and all six source Notebook bytes. No merge or promotion was performed.

## Contract and pipeline reconciliation

- Base contract checksum: 11/11 PASS.
- Semantic schemas/control registry: 12 schemas, 6 stages, 26 gates, 11 edges; PASS.
- Pipeline tests: 116/116 PASS; NCS tests: 84/84 PASS.
- CSV/Parquet schema-aware equality: 8/8 pairs PASS; `ncsSubCode` requires explicit string dtype.
- PK/FK: 8 PK and 9 FK checks PASS; duplicate/orphan count 0.
- Canonical export: `postingKind` invalid 137/137; `canonicalPostedAt`, `periodMonth`, `companyKey` non-null 0/137.
- Separate deterministic recovery: valid enum 137/137 and authoritative time 29/137, but it is not consumed by the canonical export.
- `highDemandScore` non-null: 0.
- `p4.duckdb`: absent. `p4.observed-dev.duckdb`: absent. `p4.development.duckdb` contains six fixture postings and is neither production nor the observed release.

## NCS and Gold reconciliation

- Official source/normalized corpus binding: 13,442/13,442 rows bound to raw SHA `d7033327...`.
- Graph: 14,930 nodes and 14,906 edges; official level/band populated for 13,442 units.
- Observed mapped codes: 27/27 join official unit codes, but canonical mart level/band rows are 0.
- Duty-unit bridge: 0. Work24 crosswalk: 0. Corpus manifest parserVersion: missing.
- HUMAN_GOLD: 0; dual coding: 0; adjudication: 0; LLM_REFERENCE_FROZEN: 0.
- Precision, recall, F1 and reference coverage: `NOT_EVALUATED`.

## Cross-component result

Only `normalized→track` is fully proven. Other downstream edges are `PASS_WITH_FINDINGS`, `LINEAGE_UNPROVEN`, or `BLOCKED`; therefore `DATA_READY_RQ2B`, analytical mart promotion, and RQ dataset construction remain blocked.

## Forbidden promotions

`CRAWL_RELEASE_READY`, `PRODUCTION_PREPROCESSED_DATA_READY`, `DATA_READY_RQ1_RQ2A`, `DATA_READY_RQ2B`, and `ANALYSIS_READY` are not declared. Production network crawl approval remains a user decision.
"""
    (REPORT / "P4_M1_5_IMPLEMENTATION_REPORT.md").write_text(report_text, encoding="utf-8")

    unresolved = [i for i, _ in defects]
    required_names = [
        "P4_M1_5_IMPLEMENTATION_REPORT.md", "P4_M1_5_COMPONENT_STATUS.csv", "P4_M1_5_GATE_STATUS.csv",
        "P4_M1_5_DEFECT_REGISTER.csv", "P4_M1_5_DECISION_REGISTER.csv", "P4_M1_5_DATA_LINEAGE.csv",
        "P4_M1_5_STAGE_REGISTRY.yaml", "P4_M1_5_CONTRACT_RECONCILIATION.csv",
        "P4_M1_5_CRAWL_HANDOFF_CONSUMPTION.csv", "P4_M1_5_API_CONTRACT_STATUS.csv",
        "P4_M1_5_NCS_CORPUS_AUDIT.csv", "P4_M1_5_GOLD_STATUS.csv", "P4_M1_5_TEMPORAL_SPLIT_AUDIT.csv",
        "P4_M1_5_RQ2B_AGGREGATION_AUDIT.csv", "P4_M1_5_TEST_SUMMARY.csv", "P4_M1_5_USER_DECISION_PACKET.md",
    ]
    report_shas = {name: sha(REPORT / name) for name in required_names}
    handoff = {
        "manifestVersion": "p4-cloud-handoff-v1", "agentId": "P4-PROJECTWIDE-IMPLEMENTATION-ORCHESTRATOR",
        "baseCommit": BASE, "headCommit": audit_head, "headCommitMeaning": "audited integration input plus audit generator; report publication commit is intentionally external to avoid self-referential Git SHA",
        "integrationBranch": BRANCH, "crawlHandoffBranch": CRAWL_BRANCH, "crawlHandoffBranchHead": CRAWL_BRANCH_HEAD,
        "crawlHandoffCommit": CRAWL_AUDITED_HEAD, "dataVersion": DATA_VERSION, "runId": RUN_ID,
        "claimedStatus": "PARTIAL", "crawlHandoffStatus": "EVIDENCE_INSUFFICIENT",
        "reportSha256": report_shas, "testCommands": test_rows, "productionNetworkCalls": 0,
        "rawBytesInclusionPolicy": "RAW_BYTES_GIT_EXCLUDED; 29 local bytes independently hash-verified; not promotion evidence",
        "rawBytesIncluded": False, "secretsIncluded": False, "unresolvedDefects": unresolved,
    }
    write_json(REPORT / "P4_M1_5_CLOUD_HANDOFF_MANIFEST.json", handoff)

    manifest_files = [REPORT / name for name in required_names] + [REPORT / "P4_M1_5_CLOUD_HANDOFF_MANIFEST.json"]
    (REPORT / "EVIDENCE_MANIFEST.sha256").write_text(
        "".join(f"{sha(path)}  {path.name}\n" for path in manifest_files), encoding="utf-8"
    )
    print(json.dumps({"status": "PARTIAL", "crawlHandoffStatus": "EVIDENCE_INSUFFICIENT", "reports": len(manifest_files), "unresolvedP1": len(unresolved)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
