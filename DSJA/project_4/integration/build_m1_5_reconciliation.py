#!/usr/bin/env python3
"""Build the fail-closed M1.5 reconciliation packet.

This runner is deliberately network-free.  It inventories the integration
candidate and accepted handoff evidence, but it never executes downstream
stages unless every component handoff has first been accepted.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
REPORT = PROJECT / "reports" / "m1_5_reconciliation"
BASE = "5508fce02ba5396b5d5a55870f1f879c1f32e8e0"
BRANCH = "integration/p4-m1_5-reconcile-for-m2-v1"
A1_BRANCH = "agent/p4-crawl-m1_5-control-patch-v4"
A1_HEAD = "2d3f48025352359acf5787efeb79c0111fdea9f7"
A1_AUDITED = "23b242da31c63687cc100af0603dacc7b4bafe2c"
A2_BRANCH = "agent/p4-a2-semantic-m1_5-v4"
A2_HEAD = "879b2c2e2cf3ba3f3cdc8f0847e607f045e2b839"
A4_BRANCH = "agent/p4-a4-ncs-reference-v4"
A4_HEAD = "3396eb66f6f9af80d0458ab8c5431b1c5ce6414c"
M2_BRANCH = "agent/p4-crawl-m2-production-v1"
M2_HEAD = "007bc8e6fa0c0314aecd5b70f64640f6b6482873"
RUN_ID = "M1_5_RECONCILIATION_20260807_01"
DATA_VERSION = "reconciliation-20260807.1"
CONTRACT_VERSION = "2.1.2"
RAW_OBJECT_MANIFEST_SHA = "f12680f1d598f70df576f0af4743c5e9c49df7caf16eccb1d898bded5eb3dfbe"
VALIDATOR_SHA = "NOT_AVAILABLE_PRECONDITION_BLOCKED"
ALLOWED = {"PASS", "PASS_WITH_FINDINGS", "PARTIAL", "BLOCKED", "NOT_STARTED", "NOT_EVALUATED", "FAIL"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=check)
    return proc.stdout.strip()


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=REPO)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"empty CSV prohibited: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def meta(head: str) -> dict[str, object]:
    return {
        "baseCommit": BASE,
        "headCommit": head,
        "acceptedAgentCommits": "NONE",
        "dataVersion": DATA_VERSION,
        "runId": RUN_ID,
        "contractVersion": CONTRACT_VERSION,
        "sourceNotebookManifestSha256": "SEE_EVIDENCE_MANIFEST",
        "rawObjectManifestSha256": RAW_OBJECT_MANIFEST_SHA,
        "validatorReportSha256": VALIDATOR_SHA,
        "reportSha256": "SEE_EVIDENCE_MANIFEST",
    }


def with_meta(rows: list[dict[str, object]], head: str) -> list[dict[str, object]]:
    common = meta(head)
    return [{**common, **row} for row in rows]


def notebook_metrics(path: Path) -> tuple[int, int, int, str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    cells = doc.get("cells", [])
    output_count = sum(len(c.get("outputs", [])) for c in cells if c.get("cell_type") == "code")
    execution_count = sum(c.get("execution_count") is not None for c in cells if c.get("cell_type") == "code")
    ids = [str(c.get("id", f"MISSING-{i}")) for i, c in enumerate(cells)]
    return len(cells), output_count, execution_count, sha_bytes("\n".join(ids).encode())


def tree_sha(root: Path) -> str:
    """Hash tracked Python module bytes with repository-relative names."""
    rows = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            rows.append(f"{path.relative_to(PROJECT).as_posix()}\0{sha(path)}")
    return sha_bytes("\n".join(rows).encode())


def a1_expected() -> dict[str, dict[str, str]]:
    raw = git_bytes(
        "show",
        f"origin/{A1_BRANCH}:DSJA/project_4/crawl/reports/m1_5_control_patch/CRAWL_NOTEBOOK_SOURCE_BLOB_MANIFEST.csv",
    ).decode("utf-8-sig")
    return {row["sourcePath"]: row for row in csv.DictReader(io.StringIO(raw))}


def main() -> int:
    REPORT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD")
    registry_path = PROJECT / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    stages = registry["stages"]
    execution = stages[:23]
    by_path = {s["notebookPath"]: s for s in stages}
    expected = a1_expected()

    handoffs = [
        {
            "agent": "A1", "branch": A1_BRANCH, "submittedHead": A1_HEAD,
            "auditedCodeCommit": A1_AUDITED, "baseCommitObserved": "b64270bd4ab839ec750a4ceceb08d57957c88782",
            "reportSha256": "2af4103084550a5ed63887adbc74dd8ccbd0ad18498ee0131ace90f7ba9a155b",
            "evidenceChecksum": "PASS", "testCommand": "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-crawl-root> PYTHONPATH=crawl/src:. python -m pytest crawl/tests crawl/control/tests -q -rs",
            "exitCode": 0, "changedRoot": "crawl/**", "ownershipViolation": 0,
            "sourceCodeSha": A1_AUDITED, "notebookBlobAuthority": "handoff 6/6; integration candidate 6/6",
            "unresolvedP1": "P1-CRAWL-003,P1-CRAWL-006,P1-CRAWL-007",
            "contractCompatibility": "FAIL", "rawProductionPolicy": "network=0; raw Git-excluded",
            "status": "REJECTED",
            "reason": "source packet passes 64/64, but consumed integration candidate fails 8 compatibility tests (70 pass/8 fail); no promotion",
        },
        {
            "agent": "A2", "branch": A2_BRANCH, "submittedHead": A2_HEAD,
            "auditedCodeCommit": A2_HEAD, "baseCommitObserved": "pre-5508 component branch",
            "reportSha256": "NOT_PROVIDED_AS_RECONCILIATION_HANDOFF", "evidenceChecksum": "NOT_EVALUATED",
            "testCommand": "PYTHONPATH=src python -m pytest -q", "exitCode": 0,
            "changedRoot": "pipeline/**", "ownershipViolation": 0, "sourceCodeSha": A2_HEAD,
            "notebookBlobAuthority": "no base-5508 reconciliation authority manifest",
            "unresolvedP1": "P1-CLOUD-005,P1-CLOUD-006,P1-CLOUD-011", "contractCompatibility": "FAIL",
            "rawProductionPolicy": "observed/dev/production separation not promoted",
            "status": "REJECTED",
            "reason": "canonical export postingKind invalid 137/137; canonicalPostedAt/periodMonth/companyKey 0/137; recovery output not consumed",
        },
        {
            "agent": "A4", "branch": A4_BRANCH, "submittedHead": A4_HEAD,
            "auditedCodeCommit": A4_HEAD, "baseCommitObserved": "merge-base 3d319f95681b47e1ee80ba3c350761cd85bec146",
            "reportSha256": "9b042f69f354301c24813ea26c4e6bcda1bfae35c9bb3db5b08bc547a0bc9437",
            "evidenceChecksum": "PASS_WITH_FINDINGS", "testCommand": "PYTHONPATH=src python -m pytest -q",
            "exitCode": 0, "changedRoot": "ncs_mapping/**", "ownershipViolation": 0,
            "sourceCodeSha": A4_HEAD, "notebookBlobAuthority": "baseline 6/6; v4 R0-R5 execution authority absent",
            "unresolvedP1": "P1-CLOUD-007,P1-CLOUD-008,P1-CLOUD-010", "contractCompatibility": "PARTIAL",
            "rawProductionPolicy": "official local NCS source SHA bound; promotionAllowed=false",
            "status": "EVIDENCE_INSUFFICIENT",
            "reason": "no 5508-descendant handoff; parserVersion absent; mapping-to-mart schema/rows absent; Gold/reference evaluation absent",
        },
    ]
    write_csv(REPORT / "P4_M1_5_AGENT_HANDOFF_ACCEPTANCE.csv", with_meta(handoffs, head))

    notebook_rows: list[dict[str, object]] = []
    physical = sorted(
        list((PROJECT / "crawl/notebooks").glob("*.ipynb"))
        + list((PROJECT / "pipeline/notebooks").glob("*.ipynb"))
        + list((PROJECT / "ncs_mapping/notebooks").glob("*.ipynb"))
    )
    execution_paths = {s["notebookPath"] for s in execution}
    module_tree_shas = {
        "P4-A1-SOURCE": tree_sha(PROJECT / "crawl/src/p4_crawl"),
        "P4-A2-PIPELINE": tree_sha(PROJECT / "pipeline/src/p4"),
        "P4-A4-NCS": tree_sha(PROJECT / "ncs_mapping/src/p4_ncs"),
    }
    for path in physical:
        rel = path.relative_to(PROJECT).as_posix()
        stage = by_path.get(rel)
        owner = stage.get("ownerAgent", "P4-A2-PIPELINE") if stage else "P4-A2-PIPELINE"
        if rel == "crawl/notebooks/P4_Notebook_First_Master.ipynb":
            registry_class = "REGISTERED_OBSERVED_MASTER"
        elif rel in execution_paths:
            registry_class = "RECONCILIATION_EXECUTION_STAGE"
        else:
            registry_class = "ANALYSIS_ARTICLE_SUPPORT_EXCLUDED"
        file_sha = sha(path)
        blob = git("hash-object", str(path))
        cells, outputs, executions, cell_order_sha = notebook_metrics(path)
        exp = expected.get(rel)
        expected_sha = exp["sourceFileSha256"] if exp else "NO_FORMAL_RECONCILIATION_HANDOFF"
        match = (file_sha == expected_sha) if exp else False
        if owner == "P4-A1-SOURCE":
            status = "PASS" if match else "FAIL"
            authority = A1_AUDITED
        elif owner == "P4-A4-NCS":
            status = "EVIDENCE_INSUFFICIENT"
            authority = A4_HEAD
        else:
            status = "EVIDENCE_INSUFFICIENT" if rel in execution_paths else "NOT_EVALUATED"
            authority = A2_HEAD
        notebook_rows.append({
            "stageId": stage.get("stageId", "EXCLUDED") if stage else "EXCLUDED",
            "owner": owner, "registryClass": registry_class,
            "executionStage": rel in execution_paths, "sourceNotebookPath": rel,
            "sourceNotebookBlobSha256": file_sha, "gitBlobId": blob, "authorityCommit": authority,
            "expectedAuthoritySha256": expected_sha, "authorityShaMatch": match,
            "cellCount": cells, "cellIdOrderSha256": cell_order_sha,
            "sourceOutputCount": outputs, "sourceExecutionCount": executions,
            "moduleBlobSha256": module_tree_shas.get(owner, "NOT_APPLICABLE"),
            "inputContract": json.dumps(stage.get("inputArtifacts", []), ensure_ascii=False) if stage else "NOT_APPLICABLE",
            "outputContract": json.dumps(stage.get("outputArtifacts", []), ensure_ascii=False) if stage else "NOT_APPLICABLE",
            "inputSchemaSha256": sha_bytes(json.dumps({"schemaVersion": stage.get("schemaVersion"), "artifacts": stage.get("inputArtifacts", [])}, sort_keys=True).encode()) if stage else "NOT_APPLICABLE",
            "outputSchemaSha256": sha_bytes(json.dumps({"schemaVersion": stage.get("schemaVersion"), "artifacts": stage.get("outputArtifacts", [])}, sort_keys=True).encode()) if stage else "NOT_APPLICABLE",
            "dependencyStageIds": json.dumps(stage.get("upstreamStages", []), ensure_ascii=False) if stage else "NOT_APPLICABLE",
            "currentRunManifestSchema": stage.get("schemaVersion", "NOT_APPLICABLE") if stage else "NOT_APPLICABLE",
            "validatorGate": stage.get("producedGate", "NOT_APPLICABLE") if stage else "NOT_APPLICABLE",
            "status": status,
        })
    write_csv(REPORT / "P4_M1_5_NOTEBOOK_AUTHORITY.csv", with_meta(notebook_rows, head))

    stage_doc = {
        "registryVersion": "p4-m1.5-reconciliation-v1",
        "agentId": "P4-A3-GLOBAL-INTEGRATION-RECONCILIATION-ORCHESTRATOR",
        **meta(head),
        "policy": {
            "plannedStages": 23, "executeOnlyAfterHandoffsAccepted": ["A1", "A2", "A4"],
            "allHandoffsAccepted": False, "networkAllowed": False,
            "freshRunRequired": True, "exactOneManifestRequired": True,
        },
        "testEvidence": {
            "pipeline": {"command": "PYTHONPATH=src python -m pytest -q", "exitCode": 0, "passed": 116},
            "ncsMapping": {"command": "PYTHONPATH=src python -m pytest -q", "exitCode": 0, "passed": 84},
            "integration": {"command": "python -m pytest -q integration/tests", "exitCode": 0, "passed": 12},
            "consumedCrawlCandidate": {"command": "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-crawl-root> ... pytest crawl", "exitCode": 1, "passed": 70, "failed": 8},
        },
        "stages": [
            {
                "stageId": s["stageId"], "owner": s["ownerAgent"],
                "sourceNotebookPath": s["notebookPath"],
                "sourceNotebookBlobSha256": sha(PROJECT / s["notebookPath"]),
                "moduleBlobSha256": module_tree_shas.get(s["ownerAgent"], "NOT_AVAILABLE"),
                "inputSchemaSha256": sha_bytes(json.dumps({"schemaVersion": s.get("schemaVersion"), "artifacts": s.get("inputArtifacts", [])}, sort_keys=True).encode()),
                "outputSchemaSha256": sha_bytes(json.dumps({"schemaVersion": s.get("schemaVersion"), "artifacts": s.get("outputArtifacts", [])}, sort_keys=True).encode()),
                "inputContract": s.get("inputArtifacts", []), "outputContract": s.get("outputArtifacts", []),
                "dependencyStageIds": s.get("upstreamStages", []),
                "currentRunManifestSchema": s.get("schemaVersion", "NOT_AVAILABLE"),
                "validatorGate": s.get("producedGate", "NOT_AVAILABLE"),
            }
            for s in execution
        ],
    }
    (REPORT / "P4_M1_5_STAGE_REGISTRY.yaml").write_text(
        yaml.safe_dump(stage_doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    replay_rows = []
    manifest_rows = []
    for s in execution:
        replay_rows.append({
            "stageId": s["stageId"], "owner": s["ownerAgent"], "planned": True,
            "executed": False, "stageStatus": "NOT_STARTED", "blocker": "HANDOFF_ACCEPTANCE_PRECONDITION_FAILED",
            "inputManifestSha256": "NOT_AVAILABLE", "outputManifestSha256": "NOT_AVAILABLE",
            "sourceNotebookSha256": sha(PROJECT / s["notebookPath"]),
            "moduleBlobSha256": module_tree_shas.get(s["ownerAgent"], "NOT_AVAILABLE"), "parameterSha256": "NOT_AVAILABLE",
            "validatorInvoked": False, "validatorExitCode": "NOT_INVOKED", "validatorStatus": "NOT_STARTED",
            "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        })
        manifest_rows.append({
            "stageId": s["stageId"], "expectedCurrentRunManifestCount": 1,
            "actualCurrentRunManifestCount": 0, "exactOne": False, "staleConsumed": 0,
            "foreignArtifactConsumed": 0, "sourceNotebookAuthorityMismatch": 1 if s["ownerAgent"] == "P4-A1-SOURCE" else 0,
            "status": "BLOCKED", "reason": "replay correctly not started before A1/A2/A4 acceptance",
        })
    write_csv(REPORT / "P4_M1_5_FULL_REPLAY_SUMMARY.csv", with_meta(replay_rows, head))
    write_csv(REPORT / "P4_M1_5_CURRENT_RUN_MANIFEST_AUDIT.csv", with_meta(manifest_rows, head))

    prior_lineage = PROJECT / "reports/m1_5_v4_implementation/P4_M1_5_DATA_LINEAGE.csv"
    lineage_rows = list(csv.DictReader(prior_lineage.open(encoding="utf-8")))
    for row in lineage_rows:
        row["reconciliationStatus"] = "BLOCKED" if row["status"] != "PASS" else "PASS_WITH_FINDINGS"
        row["reconciliationFinding"] = "no new 23-stage replay; prior cloud evidence retained without promotion"
    write_csv(REPORT / "P4_M1_5_CANONICAL_LINEAGE_AUDIT.csv", with_meta(lineage_rows, head))

    raw_rows = [
        {"checkId": "RAW-MOUNTED", "storageRootId": "LOCAL_RUNTIME_RAW_A1", "mountPolicyVersion": "NOT_PROVIDED",
         "objectLocatorRelative": "data/raw/linkareer", "expectedObjects": 29, "resolvedObjects": 29,
         "compressedShaMatches": 29, "contentShaMatches": 29, "postingBindingRows": 29,
         "status": "PASS_WITH_FINDINGS", "finding": "64/64 crawl tests pass only with explicit external mount; raw bytes remain Git-excluded"},
        {"checkId": "RAW-UNMOUNTED", "storageRootId": "UNMOUNTED", "mountPolicyVersion": "NOT_PROVIDED",
         "objectLocatorRelative": "NOT_AVAILABLE", "expectedObjects": 29, "resolvedObjects": 0,
         "compressedShaMatches": 0, "contentShaMatches": 0, "postingBindingRows": 0,
         "status": "BLOCKED", "finding": "Git-only replay resolves 0; explicit RAW_ROOT_UNMOUNTED evidence and no-fixture-fallback contract absent"},
        {"checkId": "RAW-WRONG-SHA", "storageRootId": "LOCAL_RUNTIME_RAW_A1", "mountPolicyVersion": "NOT_PROVIDED",
         "objectLocatorRelative": "data/raw/linkareer", "expectedObjects": 1, "resolvedObjects": 0,
         "compressedShaMatches": 0, "contentShaMatches": 0, "postingBindingRows": 0,
         "status": "NOT_EVALUATED", "finding": "wrong-SHA quarantine/downstream-block test not supplied as reconciliation handoff"},
        {"checkId": "RAW-POSTING-BINDING", "storageRootId": "LOCAL_RUNTIME_RAW_A1", "mountPolicyVersion": "NOT_PROVIDED",
         "objectLocatorRelative": "observed input manifest", "expectedObjects": 29, "resolvedObjects": 29,
         "compressedShaMatches": 29, "contentShaMatches": 29, "postingBindingRows": 29,
         "status": "PASS_WITH_FINDINGS", "finding": "29/29 binding; posting raw-file flag drift 18 remains"},
        {"checkId": "M2-PREFLIGHT-REBIND", "storageRootId": "NOT_BOUND", "mountPolicyVersion": "NOT_PROVIDED",
         "objectLocatorRelative": "NOT_AVAILABLE", "expectedObjects": 29, "resolvedObjects": 0,
         "compressedShaMatches": 0, "contentShaMatches": 0, "postingBindingRows": 0,
         "status": "BLOCKED", "finding": "M2 branch diverges from latest A1 at b64270bd; no raw rebind manifest"},
    ]
    write_csv(REPORT / "P4_M1_5_RAW_MOUNT_AUDIT.csv", with_meta(raw_rows, head))

    gates = [
        ("A1_HANDOFF_ACCEPTED", "FAIL", "REJECTED after consumed candidate crawl/control test: 70 passed, 8 failed"),
        ("A2_HANDOFF_ACCEPTED", "FAIL", "REJECTED"),
        ("A4_HANDOFF_ACCEPTED", "BLOCKED", "EVIDENCE_INSUFFICIENT"),
        ("CRAWL_88_PATH_DISPOSITION", "PARTIAL", "approved A1 commits imported for compatibility audit; six stronger base controls and 18 audit/contract additions retained, but resulting tests fail 8"),
        ("CRAWL_NOTEBOOK_AUTHORITY", "PASS", "6/6 source SHA and Git blob exact in integration candidate"),
        ("RAW_MOUNT_CONTRACT", "PASS_WITH_FINDINGS", "mounted 29/29 and unmounted fail-closed independently verified; bytes remain external and 18 flag-drift rows quarantined"),
        ("RAW_POSTING_BINDING", "PASS_WITH_FINDINGS", "29/29 bound; raw flag drift 18"),
        ("CANONICAL_POSTING_KIND", "FAIL", "invalid 137/137"),
        ("CANONICAL_TIME_ENTITY_LINEAGE", "FAIL", "date/month/company 0/137; recovery not consumed"),
        ("NCS_STAGE_AUTHORITY", "BLOCKED", "v4 R0-R5 authority absent"),
        ("CURRENT_RUN_EXACT_ONE", "NOT_STARTED", "0/23 because handoff preconditions failed"),
        ("STRICT_VALIDATOR", "NOT_STARTED", "not invoked because replay did not start"),
        ("OBSERVED_DEV_PRODUCTION_CONTAMINATION", "PASS_WITH_FINDINGS", "production and observed DB absent; development DB is fixture-only"),
        ("A5_AUDIT_PACKAGE", "PASS", "complete blocker package generated"),
        ("M1_5_RECONCILIATION_READY_FOR_A5_AUDIT", "BLOCKED", "mandatory component and replay gates unmet"),
        ("M1_5_RECONCILIATION_READY_FOR_M2_PREFLIGHT", "BLOCKED", "A5 PASS unavailable and reconciliation incomplete"),
        ("M2_CRAWL_READY_FOR_USER_APPROVAL", "BLOCKED", "forbidden promotion"),
        ("CRAWL_RELEASE_READY", "BLOCKED", "79-month/source-policy/release evidence absent"),
        ("ANALYSIS_READY", "BLOCKED", "empirical lineage unproven"),
    ]
    gate_rows = [{"gateId": i, "status": s, "evidence": e} for i, s, e in gates]
    assert all(row["status"] in ALLOWED for row in gate_rows)
    write_csv(REPORT / "P4_M1_5_GATE_STATUS.csv", with_meta(gate_rows, head))

    defects = [
        ("P1-RECON-001", "A1 handoff candidate consumption conflicts with retained control contracts: crawl/control integration test 70 pass, 8 fail"),
        ("P1-RECON-002", "A1 current-run exact-one is 5/5 but downstream is 0/18; reconciliation replay 0/23"),
        ("P1-RECON-003", "M2 preflight is a separate fail-closed packet and cannot be promoted while A2/A4 reconciliation is rejected or insufficient"),
        ("P1-RECON-004", "raw bytes are portable only through the runtime mount policy; 18 posting flag-drift rows remain quarantined"),
        ("P1-RECON-005", "canonical export postingKind is invalid 137/137"),
        ("P1-RECON-006", "canonical date/month/company coverage is 0/137 and recovery is not consumed"),
        ("P1-RECON-007", "A4 has no base-5508 v4 execution authority or mapping-to-mart handoff"),
        ("P1-RECON-008", "official mapping level/band reaches 0 canonical mart rows"),
        ("P1-RECON-009", "HUMAN_GOLD, dual coding and adjudication are all zero"),
        ("P1-RECON-010", "strict validator has no current-run input because replay preconditions failed"),
        ("P1-RECON-011", "A5 independent PASS is unavailable"),
    ]
    defect_rows = [{"defectId": i, "severity": "P1", "status": "OPEN", "finding": f, "downstreamGate": "BLOCKED", "owner": "A1/A2/A3/A4 as assigned"} for i, f in defects]
    write_csv(REPORT / "P4_M1_5_DEFECT_REGISTER.csv", with_meta(defect_rows, head))

    # A5 request is created even when blocked so that an independent auditor can
    # reproduce and confirm the fail-closed decision.
    request = {
        "agentId": "P4-A3-GLOBAL-INTEGRATION-RECONCILIATION-ORCHESTRATOR",
        "integrationBranch": BRANCH, "headCommit": head, "baseCommit": BASE,
        "acceptedAgentCommits": {},
        "consumedCandidateCommits": {"A1": A1_HEAD},
        "submittedAgentCommits": {"A1": A1_HEAD, "A2": A2_HEAD, "A4": A4_HEAD},
        "dataVersion": DATA_VERSION, "runId": RUN_ID, "contractVersion": CONTRACT_VERSION,
        "notebookAuthorityManifestSha256": sha(REPORT / "P4_M1_5_NOTEBOOK_AUTHORITY.csv"),
        "rawMountPolicySha256": sha(REPORT / "P4_M1_5_RAW_MOUNT_AUDIT.csv"),
        "rawObjectManifestSha256": RAW_OBJECT_MANIFEST_SHA,
        "fullReplaySummarySha256": sha(REPORT / "P4_M1_5_FULL_REPLAY_SUMMARY.csv"),
        "currentRunManifestAuditSha256": sha(REPORT / "P4_M1_5_CURRENT_RUN_MANIFEST_AUDIT.csv"),
        "validatorReportSha256": VALIDATOR_SHA,
        "canonicalLineageAuditSha256": sha(REPORT / "P4_M1_5_CANONICAL_LINEAGE_AUDIT.csv"),
        "gateMatrixSha256": sha(REPORT / "P4_M1_5_GATE_STATUS.csv"),
        "claimedStatus": "BLOCKED_BY_EVIDENCE", "crawlHandoffStatus": "REJECTED",
        "plannedStages": 23, "executedStages": 0, "exactOneManifests": 0,
        "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "rowCounts": {"physicalNotebooks": 27, "reconciliationStages": 23, "canonicalPostings": 137, "rawObjects": 29, "ncsUnits": 13442},
        "testCommands": [
            {"scope": "pipeline", "command": "PYTHONPATH=src python -m pytest -q", "exitCode": 0, "passed": 116},
            {"scope": "ncs_mapping", "command": "PYTHONPATH=src python -m pytest -q", "exitCode": 0, "passed": 84},
            {"scope": "integration", "command": "python -m pytest -q integration/tests", "exitCode": 0, "passed": 12},
            {"scope": "consumed crawl candidate", "command": "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-crawl-root> ... pytest crawl", "exitCode": 1, "passed": 70, "failed": 8},
        ],
        "unresolvedDefects": [i for i, _ in defects],
        "auditInstruction": "Confirm the blocker packet in a separate read-only worktree; do not promote M2.",
    }
    write_json(REPORT / "P4_M1_5_A5_AUDIT_REQUEST.json", request)

    report = f"""# P4 M1.5 Global Integration Reconciliation → M2 Gate

## Executive verdict

`BLOCKED_BY_EVIDENCE`

The maximum allowed state `M1_5_RECONCILIATION_READY_FOR_A5_AUDIT` is **not** declared. A1 and A2 are `REJECTED`; A4 is `EVIDENCE_INSUFFICIENT`. The 23-stage isolated replay and strict validator were correctly not invoked because every required handoff was not accepted.

## Authority

- agentId: `P4-A3-GLOBAL-INTEGRATION-RECONCILIATION-ORCHESTRATOR`
- branch: `{BRANCH}`
- audited base/head: `{BASE}` / `{head}`
- runId/dataVersion: `{RUN_ID}` / `{DATA_VERSION}`
- contractVersion: `{CONTRACT_VERSION}`
- production Linkareer calls: `0`
- external ATS calls: `0`
- report SHA-256: see `EVIDENCE_MANIFEST.json` (self-hash is not embedded)
- verified test commands: pipeline `116/116`, NCS `84/84`, integration `12/12`, A1 source branch `64/64`; consumed crawl candidate `70 passed, 8 failed`

## Agent handoff acceptance

| Agent | Ref | Verdict | Principal blocker |
|---|---|---|---|
| A1 | `{A1_BRANCH}@{A1_HEAD}` | REJECTED | source branch 64/64 passes, but consumed candidate has 8 control compatibility failures |
| A2 | `{A2_BRANCH}@{A2_HEAD}` | REJECTED | canonical enum invalid 137/137; time/month/company 0/137; recovery is not wired to export |
| A4 | `{A4_BRANCH}@{A4_HEAD}` | EVIDENCE_INSUFFICIENT | no base-5508 v4 authority; mapping→level/band→mart output 0 |

No Agent branch was merged. The A1 commit sequence was cherry-picked as a compatibility candidate, then rejected after the integration test failed. Accepted Agent commits: none.

## Notebook authority

- physical source Notebooks: `27`
- registered observed bundle: `24` (`23` execution stages plus A3 Master)
- reconciliation execution stages: `23`
- analysis/article/support excluded: `3`
- latest A1 source SHA and Git blob exact match in integration: `6/6`
- source outputs/execution counts in candidate: `0/0`

## Raw authority

An explicit local mount independently resolves `29/29` objects and the original A1 suite passes `64/64`; those bytes are not Git authority. Git-only resolution is `0/29`, which means **unavailable**, not absent. Unmounted execution was independently verified fail-closed. Eighteen posting-flag drift rows remain quarantined. The integrated candidate additionally fails 8 compatibility tests.

## Canonical and NCS reconciliation

- canonical `postingKind` invalid: `137/137`
- canonical `canonicalPostedAt`, `periodMonth`, `companyKey` non-null: `0/137`
- separate deterministic recovery: valid enum `137/137`, date/month `29/137`; export consumption `0`
- `highDemandScore` non-null: `0`
- NCS official units: `13,442`; graph nodes/edges: `14,930/14,906`
- mapped codes joining official units: `27/27`; canonical mart level/band rows: `0`
- HUMAN_GOLD / dual coding / adjudication: `0/0/0`

## Replay and strict validator

`plannedStages=23`, `executedStages=0`, `exactOneManifests=0`. This is a fail-closed precondition outcome, not an empty-data PASS. `validatorInvoked=false`; there is no current-run validator SHA.

## Gate decision

`M1_5_RECONCILIATION_READY_FOR_A5_AUDIT`, `M1_5_RECONCILIATION_READY_FOR_M2_PREFLIGHT`, `M2_CRAWL_READY_FOR_USER_APPROVAL`, `CRAWL_RELEASE_READY`, and `ANALYSIS_READY` remain `BLOCKED`.

## Next admissible actions

1. A1 resolves the eight consumed-candidate control compatibility failures without removing the stronger base tests.
2. A2 publishes canonical export with deterministic recovery provenance and zero invalid enums.
3. A4 publishes v4 authority and mapping-to-mart handoff schema.
4. A3 re-runs this acceptance gate; only then may the isolated 23-stage replay and strict validator run.
5. A5 audits the resulting package in a separate worktree.

Notebook execution does not mean analysis data is ready. Structural QA does not prove semantic completeness. Observed-development output is not an article result. CSV is inspection/export only. NCS candidates are not a mapping quality gate.
"""
    (REPORT / "P4_M1_5_RECONCILIATION_REPORT.md").write_text(report, encoding="utf-8")

    # Build a non-circular evidence index. The .sha256 file itself is excluded.
    artifacts = sorted(p for p in REPORT.iterdir() if p.is_file() and p.name not in {"EVIDENCE_MANIFEST.sha256", "EVIDENCE_MANIFEST.json"})
    evidence = {
        "agentId": "P4-A3-GLOBAL-INTEGRATION-RECONCILIATION-ORCHESTRATOR",
        "baseCommit": BASE, "headCommit": head, "integrationBranch": BRANCH,
        "acceptedAgentCommits": {}, "consumedCandidateCommits": {"A1": A1_HEAD}, "crawlHandoffBranch": A1_BRANCH,
        "crawlHandoffCommit": A1_HEAD, "m2PreflightBranch": M2_BRANCH, "m2PreflightCommit": M2_HEAD,
        "dataVersion": DATA_VERSION, "runId": RUN_ID, "contractVersion": CONTRACT_VERSION,
        "sourceNotebookManifestSha256": sha(REPORT / "P4_M1_5_NOTEBOOK_AUTHORITY.csv"),
        "rawObjectManifestSha256": RAW_OBJECT_MANIFEST_SHA,
        "validatorReportSha256": VALIDATOR_SHA,
        "tests": [
            {"command": "PYTHONPATH=src python -m pytest -q", "scope": "pipeline", "exitCode": 0, "passed": 116},
            {"command": "PYTHONPATH=src python -m pytest -q", "scope": "ncs_mapping", "exitCode": 0, "passed": 84},
            {"command": "python -m pytest -q integration/tests", "scope": "integration", "exitCode": 0, "passed": 12},
            {"command": "python integration/validate_m1_5_control.py", "scope": "control", "exitCode": 0, "passed": 1},
            {"command": "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-crawl-root> ... pytest crawl", "scope": "crawl handoff", "exitCode": 0, "passed": 64},
            {"command": "P4_CRAWL_RAW_SOURCE_ROOT=<mounted-crawl-root> ... pytest crawl", "scope": "consumed integration crawl", "exitCode": 1, "passed": 70, "failed": 8},
        ],
        "productionNetworkCalls": 0, "externalAtsTransportCalls": 0,
        "rawBytesInclusionPolicy": "GIT_EXCLUDED_RUNTIME_MOUNT; manifests and hashes only",
        "secretsIncluded": False, "acceptedRawBytes": 0,
        "claimedStatus": "BLOCKED_BY_EVIDENCE", "crawlHandoffStatus": "REJECTED",
        "plannedStages": 23, "executedStages": 0, "exactOneManifests": 0,
        "unresolvedDefects": [i for i, _ in defects],
        "reports": {p.name: {"sha256": sha(p), "rows": sum(1 for _ in p.open(encoding="utf-8", errors="ignore")) - (1 if p.suffix == ".csv" else 0)} for p in artifacts},
    }
    write_json(REPORT / "EVIDENCE_MANIFEST.json", evidence)
    checksum_files = artifacts + [REPORT / "EVIDENCE_MANIFEST.json"]
    (REPORT / "EVIDENCE_MANIFEST.sha256").write_text(
        "".join(f"{sha(p)}  {p.name}\n" for p in checksum_files), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
