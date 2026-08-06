#!/usr/bin/env python3
"""Build the deterministic, non-production M1.5 v4 implementation evidence bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import yaml


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
REPORT = PROJECT / "reports" / "m1_5_v4_implementation"
OBSERVED = REPORT / "evidence" / "observed_replay"
TEMPORAL = REPORT / "evidence" / "temporal"
RUN_ID = "M1_5_V4_IMPLEMENTATION_20260806_01"
AS_OF = "2026-08-06"
SSOT_SHA = "409866c166ce3874ce587ad3b1230bc530c036e9682be01bf3466aa1fd37a05a"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build_temporal_placeholders() -> None:
    """Emit typed zero-row artifacts; empty evidence remains NOT_EVALUATED."""
    TEMPORAL.mkdir(parents=True, exist_ok=True)
    schemas = {
        "split_manifest.parquet": ["referenceTaskId", "periodMonth", "split", "duplicateGroupId", "postingId", "companyKey"],
        "calibration_models.parquet": ["calibrationModelId", "fitSplit", "fitPeriodStart", "fitPeriodEnd", "status"],
    }
    for name, columns in schemas.items():
        pd.DataFrame({column: pd.Series(dtype="string") for column in columns}).to_parquet(TEMPORAL / name, index=False)
    write_csv(TEMPORAL / "leakage_audit.csv", [{"status": "NOT_EVALUATED", "rowCount": 0, "violationCount": 0, "reason": "NO_REFERENCE_ROWS"}])
    write_csv(TEMPORAL / "risk_coverage.csv", [{"status": "NOT_EVALUATED", "rowCount": 0, "reason": "NO_CALIBRATION_MODEL"}])
    write_csv(TEMPORAL / "reliability_bins.csv", [{"status": "NOT_EVALUATED", "rowCount": 0, "reason": "NO_2025_REFERENCE_LABELS"}])


def main() -> int:
    REPORT.mkdir(parents=True, exist_ok=True)
    summary = json.loads((OBSERVED / "OBSERVED_M1_5_SUMMARY.json").read_text(encoding="utf-8"))
    implementation_head = git("rev-parse", "HEAD")
    build_temporal_placeholders()

    shutil.copyfile(PROJECT / "integration" / "SEMANTIC_STAGE_REGISTRY.yaml", REPORT / "P4_M1_5_STAGE_REGISTRY.yaml")
    corpus = json.loads((PROJECT / "ncs_mapping" / "reports" / "v4" / "NCS_CORPUS_CANDIDATE_MANIFEST.json").read_text())

    components = [
        {"component": "crawl", "ownerAgent": "P4-A1-SOURCE", "implementationStatus": "PASS", "promotionStatus": "BLOCKED", "componentHead": "5a78cac2158ec6b62b28af0a8970ced66812225d", "integrationCommit": "d548b7f", "tests": "38 PASS", "evidence": "crawl/control/tests; crawl/tests"},
        {"component": "pipeline", "ownerAgent": "P4-A2-PIPELINE", "implementationStatus": "PASS", "promotionStatus": "BLOCKED", "componentHead": "879b2c2e2cf3ba3f3cdc8f0847e607f045e2b839", "integrationCommit": "a2fe4fe", "tests": "116 PASS", "evidence": "pipeline/tests; observed_replay"},
        {"component": "control", "ownerAgent": "P4-A3-CONTROL", "implementationStatus": "PASS", "promotionStatus": "PASS_WITH_FINDINGS", "componentHead": "b20bdf5", "integrationCommit": "1b5bc1c", "tests": "10 PASS; validator PASS", "evidence": "integration/validate_m1_5_control.py"},
        {"component": "ncs_mapping", "ownerAgent": "P4-A4-NCS", "implementationStatus": "PASS", "promotionStatus": "BLOCKED", "componentHead": "3396eb66f6f9af80d0458ab8c5431b1c5ce6414c", "integrationCommit": "d147880", "tests": "84 PASS", "evidence": "ncs_mapping/tests; NCS_CORPUS_CANDIDATE_MANIFEST.json"},
        {"component": "independent_audit", "ownerAgent": "P4-A5-AUDIT", "implementationStatus": "PASS_WITH_FINDINGS", "promotionStatus": "NOT_EVALUATED", "componentHead": "179fd9d", "integrationCommit": "71d5c76", "tests": "32 control + 116 pipeline + 84 NCS PASS; crawl 15/16 (raw portability)", "evidence": "P4_M1_5_INDEPENDENT_AUDIT.md"},
    ]
    write_csv(REPORT / "P4_M1_5_COMPONENT_STATUS.csv", components)

    gate_status = {
        "NCS_API_CONTRACT_PROBED": ("NOT_EVALUATED", "credential/network not used; synthetic fixtures only"),
        "WORK24_API_CONTRACT_PROBED": ("NOT_EVALUATED", "credential/network not used; synthetic fixtures only"),
        "API_ERROR_CONTRACT_READY": ("PASS", "8 success/empty/auth/parameter fixtures; parser tests PASS"),
        "API_SECRET_LOGGING_ZERO": ("PASS", "redaction and negative-path tests PASS"),
        "OBSERVED_SNAPSHOT_FROZEN": ("PASS_WITH_FINDINGS", "isolated observed replay built; not production authority"),
        "MASTER_ORCHESTRATION_PATCHED": ("PASS", "topological current-run plan tests PASS"),
        "VALIDATOR_FAIL_CLOSED": ("PASS", "negative-path control tests PASS"),
        "CURRENT_RUN_ARTIFACT_BOUND": ("PASS", "single-manifest and blob provenance tests PASS"),
        "RUNTIME_DEPENDENCIES_LOCKED": ("PASS", "integration venv exact lock validated"),
        "TIME_SEMANTICS_READY": ("BLOCKED", f"authoritative coverage {summary['canonicalPostedAtCount']}/{summary['expectedPostingRows']} < 0.98"),
        "CANONICAL_ENUM_READY": ("PASS", "invalid postingKind/requirementType/obligation = 0"),
        "RAW_LINEAGE_READY": ("BLOCKED", f"declared/physical raw mismatch = {summary['rawExistenceMismatchCount']}"),
        "DETERMINISTIC_SEMANTIC_BASE_READY": ("PASS_WITH_FINDINGS", "deterministic no-imputation implementation and replay complete"),
        "OCR_PILOT_READY": ("NOT_EVALUATED", "Linkareer-hosted asset bytes = 0"),
        "SOURCE_BLOCK_READY": ("PASS", f"source blocks={summary['sourceBlockRows']}; FK orphan=0"),
        "SECTION_STRUCTURE_PILOT_READY": ("PASS", f"semantic chunks={summary['semanticChunkRows']}; FK orphan=0"),
        "OCR_MAPPING_ELIGIBILITY_READY": ("PASS", "OCR-ineligible accepted mappings=0"),
        "REFERENCE_SCHEMA_READY": ("BLOCKED", "implementation tests PASS; dependency stages blocked"),
        "LLM_AGENT_RUNTIME_READY": ("BLOCKED", "no pinned model/prompt runtime evidence"),
        "PROMPT_MODEL_REGISTRY_READY": ("BLOCKED", "no approved model/prompt artifact"),
        "LLM_REFERENCE_PILOT_READY": ("BLOCKED", "no LLM_REFERENCE_FROZEN sample"),
        "NCS_CANONICAL_CORPUS_READY": ("BLOCKED", "candidate manifest built; bridge/crosswalk absent; dependencies blocked"),
        "NCS_RETRIEVAL_BENCHMARK_READY": ("BLOCKED", "implementation tests PASS; no fixed real benchmark/reference"),
        "CALIBRATION_READY": ("BLOCKED", "no 2025 reference labels; zero-row artifact is NOT_EVALUATED"),
        "SELECTIVE_PREDICTION_READY": ("BLOCKED", "implementation tests PASS; no fitted calibration model"),
        "TEMPORAL_AUDIT_FRAME_READY": ("BLOCKED", "split policy tests PASS; no reference rows"),
    }
    registry = yaml.safe_load((PROJECT / "integration" / "SEMANTIC_STAGE_REGISTRY.yaml").read_text())
    gates = []
    for stage in registry["stages"]:
        for gate in stage["gates"]:
            status, evidence = gate_status[gate]
            gates.append({"stageId": stage["stageId"], "gateId": gate, "status": status, "evidence": evidence, "runId": RUN_ID})
    write_csv(REPORT / "P4_M1_5_GATE_STATUS.csv", gates)

    defects = [
        {"defectId": "M15-P1-001", "severity": "P1", "status": "BLOCKED", "finding": "authoritative posted timestamp coverage is 29/137", "evidence": "evidence/observed_replay/OBSERVED_M1_5_SUMMARY.json"},
        {"defectId": "M15-P1-002", "severity": "P1", "status": "BLOCKED", "finding": "raw declared/physical mismatch is 18", "evidence": "evidence/observed_replay/OBSERVED_SEMANTIC_POSTINGS.csv"},
        {"defectId": "M15-P1-003", "severity": "P1", "status": "NOT_EVALUATED", "finding": "30 OCR candidate rows but zero asset bytes", "evidence": "evidence/observed_replay/OBSERVED_OCR_OFFLINE_PILOT.csv"},
        {"defectId": "M15-P1-004", "severity": "P1", "status": "NOT_EVALUATED", "finding": "NCS and Work24 live API credentials/probes unavailable", "evidence": "P4_M1_5_API_CONTRACT_STATUS.csv"},
        {"defectId": "M15-P1-005", "severity": "P1", "status": "NOT_EVALUATED", "finding": "human reference, pinned dense model, 2025 calibration and 2026 audit rows absent", "evidence": "P4_M1_5_REFERENCE_STATUS.csv"},
        {"defectId": "M15-P1-006", "severity": "P1", "status": "BLOCKED", "finding": "58 of 79 production pagination months remain unverified", "evidence": "shared/ssot/PROJECT4_DEFECT_REGISTER.csv"},
        {"defectId": "M15-P2-001", "severity": "P2", "status": "PASS_WITH_FINDINGS", "finding": "standalone local LLM/NCS blueprint v2.0 file not found; content is integrated into v4 SSOT", "evidence": "shared/ssot/v4.0/P4_final_design_v4.0.md"},
        {"defectId": "M15-P2-002", "severity": "P2", "status": "PASS_WITH_FINDINGS", "finding": "historical executed bundle contains an absolute path; new bundle uses repository-relative paths", "evidence": "reports/orchestrator/NOTEBOOK_RUNTIME_INVENTORY.csv"},
        {"defectId": "M15-P2-003", "severity": "P2", "status": "PASS_WITH_FINDINGS", "finding": "ignored raw SSR bytes are local authority and are not portable in Git; tracked replay outputs remain checksum-verifiable", "evidence": "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/raw_detail_manifest.jsonl"},
    ]
    write_csv(REPORT / "P4_M1_5_DEFECT_REGISTER.csv", defects)

    decisions = [
        {"decisionId": "D-M2-001", "phase": "M2", "status": "USER_DECISION_REQUIRED", "question": "production Linkareer crawl을 실행할 것인가", "recommendation": "현재 보류; source-policy 승인과 key custody 후 실행"},
        {"decisionId": "D-M2-002", "phase": "M2", "status": "USER_DECISION_REQUIRED", "question": "source-policy human approval record를 확정할 것인가", "recommendation": "승인자/시각/범위/kill switch를 서명 기록으로 동결"},
        {"decisionId": "D-SEC-001", "phase": "M2", "status": "USER_DECISION_REQUIRED", "question": "API key 회전·보관·runtime injection 책임자를 정할 것인가", "recommendation": "회전 후 secret store 단일 주입; 로그/manifest 저장 금지"},
        {"decisionId": "D-M3-001", "phase": "M3", "status": "USER_DECISION_REQUIRED", "question": "core AI·IT cohort와 통신/방송 포함 범위를 동결할 것인가", "recommendation": "69 included/51 excluded를 검토하고 별도 signed release로 동결"},
        {"decisionId": "D-DISC-001", "phase": "article", "status": "USER_DECISION_REQUIRED", "question": "LLM_REFERENCE 사용 사실과 한계를 기사에 공개할 것인가", "recommendation": "HUMAN_GOLD와 구분해 방법론/한계에 명시"},
    ]
    write_csv(REPORT / "P4_M1_5_DECISION_REGISTER.csv", decisions)

    lineage = [
        {"layer": "SSOT", "authority": "Markdown bytes + SHA", "artifact": "shared/ssot/v4.0/P4_final_design_v4.0.md", "rows": 1725, "sha256": SSOT_SHA, "status": "PASS"},
        {"layer": "raw", "authority": "raw bytes + manifest", "artifact": "crawl/data/raw", "rows": 29, "sha256": "per-file manifest", "status": "PASS_WITH_FINDINGS"},
        {"layer": "observed semantic", "authority": "DuckDB/Parquet processing contract; CSV inspection", "artifact": "reports/m1_5_v4_implementation/evidence/observed_replay/OBSERVED_SEMANTIC_POSTINGS.csv", "rows": 137, "sha256": sha(OBSERVED / "OBSERVED_SEMANTIC_POSTINGS.csv"), "status": "BLOCKED"},
        {"layer": "source block", "authority": "deterministic replay", "artifact": "reports/m1_5_v4_implementation/evidence/observed_replay/OBSERVED_SOURCE_BLOCKS.csv", "rows": summary["sourceBlockRows"], "sha256": sha(OBSERVED / "OBSERVED_SOURCE_BLOCKS.csv"), "status": "PASS"},
        {"layer": "NCS corpus candidate", "authority": "reference manifest", "artifact": "ncs_mapping/reports/v4/NCS_CORPUS_CANDIDATE_MANIFEST.json", "rows": corpus["rowCounts"]["ncsAbilityUnit"], "sha256": sha(PROJECT / "ncs_mapping" / "reports" / "v4" / "NCS_CORPUS_CANDIDATE_MANIFEST.json"), "status": "PASS_WITH_FINDINGS"},
        {"layer": "calibration", "authority": "model registry", "artifact": "reports/m1_5_v4_implementation/evidence/temporal/calibration_models.parquet", "rows": 0, "sha256": sha(TEMPORAL / "calibration_models.parquet"), "status": "NOT_EVALUATED"},
        {"layer": "RQ2-B mart", "authority": "DuckDB/Parquet", "artifact": "pipeline/src/p4/marts/rq2b.py", "rows": 0, "sha256": sha(PROJECT / "pipeline" / "src" / "p4" / "marts" / "rq2b.py"), "status": "NOT_EVALUATED"},
    ]
    write_csv(REPORT / "P4_M1_5_DATA_LINEAGE.csv", lineage)

    api_rows = []
    api_registry = yaml.safe_load((PROJECT / "integration" / "API_CONTRACT_REGISTRY.yaml").read_text())
    for endpoint in api_registry["endpoints"]:
        provider = "ncs" if endpoint["provider"] == "NCS_OPENAPI" else "work24"
        api_rows.append({"apiContractId": endpoint["apiContractId"], "provider": endpoint["provider"], "endpointPath": endpoint["endpointPath"], "registryStatus": endpoint["contractStatus"], "fixtureCases": 4, "fixtureClass": "SYNTHETIC_CONTRACT_FIXTURE", "parserTest": "PASS", "liveProbeStatus": "NOT_EVALUATED", "credentialLogged": 0, "fixtureRoot": f"ncs_mapping/data/raw/api_fixtures/{provider}"})
    write_csv(REPORT / "P4_M1_5_API_CONTRACT_STATUS.csv", api_rows)
    write_csv(REPORT / "P4_M1_5_NCS_CORPUS_DIFF.csv", [{"fromVersion": "NONE", "toVersion": corpus["ncsCorpusVersion"], "status": "NOT_EVALUATED", "reason": "NO_COMPARABLE_PRIOR_V4_CORPUS_RELEASE", "abilityUnitRows": 13442, "nodeRows": 14930, "edgeRows": 14906, "bridgeRows": 0, "crosswalkRows": 0, "promotionAllowed": False}])
    write_csv(REPORT / "P4_M1_5_REFERENCE_STATUS.csv", [
        {"artifact": "reference output schema", "implementationStatus": "PASS", "executionStatus": "NOT_EVALUATED", "rows": 0, "authority": "LLM_REFERENCE_FROZEN only after independent human validation"},
        {"artifact": "Labeler/Critic/Adjudicator", "implementationStatus": "PASS", "executionStatus": "NOT_EVALUATED", "rows": 0, "authority": "MODEL_ACCEPTED never auto-promoted"},
        {"artifact": "prompt/model registry", "implementationStatus": "PARTIAL", "executionStatus": "NOT_EVALUATED", "rows": 0, "authority": "pinned artifacts absent"},
    ])
    write_csv(REPORT / "P4_M1_5_TEMPORAL_SPLIT_AUDIT.csv", [{"splitPolicy": "development=2020-2024;validation=2025;audit=2026YTD", "rowCount": 0, "leakageCount": 0, "status": "NOT_EVALUATED", "reason": "NO_REFERENCE_ROWS; 2026 not used for tuning"}])
    write_csv(REPORT / "P4_M1_5_RQ2B_AGGREGATION_AUDIT.csv", [
        {"rule": "Python-SQL equality", "status": "PASS", "observed": "targeted test PASS", "productionRows": 0},
        {"rule": "DUTY main; sourceRole separated", "status": "PASS", "observed": "unit test PASS", "productionRows": 0},
        {"rule": "multi-label 1/k", "status": "PASS", "observed": "unit test PASS", "productionRows": 0},
        {"rule": "trackId x ncsUnitCode primary dedup", "status": "PASS", "observed": "unit test PASS", "productionRows": 0},
        {"rule": "ABSTAIN/UNMAPPED/OUT_OF_SCOPE denominator", "status": "PASS", "observed": "unit test PASS", "productionRows": 0},
        {"rule": "production mart promotion", "status": "NOT_EVALUATED", "observed": "no accepted production mappings", "productionRows": 0},
    ])

    stage_status = {"M1.5-P": "PARTIAL", "M1.5-0": "PASS_WITH_FINDINGS", "M1.5-A": "BLOCKED", "M1.5-B": "BLOCKED", "M1.5-C": "BLOCKED", "M1.5-D": "BLOCKED"}
    stage_evidence = {
        "M1.5-P": ["P4_M1_5_API_CONTRACT_STATUS.csv", "../../ncs_mapping/reports/api_probe"],
        "M1.5-0": ["P4_M1_5_GATE_STATUS.csv", "../../integration/SEMANTIC_STAGE_REGISTRY.yaml"],
        "M1.5-A": ["evidence/observed_replay/OBSERVED_M1_5_SUMMARY.json", "evidence/observed_replay/OBSERVED_SEMANTIC_POSTINGS.csv"],
        "M1.5-B": ["evidence/observed_replay/OBSERVED_OCR_OFFLINE_PILOT.csv", "evidence/observed_replay/OBSERVED_SOURCE_BLOCKS.csv"],
        "M1.5-C": ["P4_M1_5_REFERENCE_STATUS.csv"],
        "M1.5-D": ["P4_M1_5_NCS_CORPUS_DIFF.csv", "P4_M1_5_TEMPORAL_SPLIT_AUDIT.csv", "P4_M1_5_RQ2B_AGGREGATION_AUDIT.csv"],
    }
    for stage in registry["stages"]:
        stage_id = stage["stageId"]
        root = REPORT / "stages" / stage_id
        root.mkdir(parents=True, exist_ok=True)
        stage_gates = [row for row in gates if row["stageId"] == stage_id]
        manifest = {"runId": RUN_ID, "stageId": stage_id, "stageName": stage["name"], "runMode": "OFFLINE_OBSERVED_IMPLEMENTATION_AUDIT", "status": stage_status[stage_id], "implementationGitHead": implementation_head, "authoritySsotSha256": SSOT_SHA, "productionLinkareerNetworkCalls": 0, "liveApiProbeCalls": 0, "articleNumbersGenerated": 0, "currentRunManifestCount": 1, "evidencePaths": stage_evidence[stage_id]}
        write_json(root / "stage_manifest.json", manifest)
        write_json(root / "stage_metrics.json", {"runId": RUN_ID, "stageId": stage_id, "gateCount": len(stage_gates), "statusCounts": {status: sum(row["status"] == status for row in stage_gates) for status in sorted({row["status"] for row in stage_gates})}, "observedPostingRows": 137 if stage_id in {"M1.5-A", "M1.5-B"} else 0})
        write_csv(root / "stage_quality.csv", stage_gates)
        names = ["stage_manifest.json", "stage_metrics.json", "stage_quality.csv"]
        (root / "CHECKSUMS.sha256").write_text("".join(f"{sha(root / name)}  {name}\n" for name in names), encoding="utf-8")

    packet_lines = ["# P4 M1.5 v4.0 User Decision Packet", "", "상태: `USER_DECISION_REQUIRED`", "", "기술 구현·offline 테스트는 자동 진행했습니다. 아래 항목만 사용자 결정이 필요합니다.", ""]
    detail = {
        "D-M2-001": ("production Linkareer crawl 실제 실행을 승인할 것인가?", "현재 호출 0; 58/79개월 pagination 미검증", "A 승인 / B 조건부 승인 / C 보류", "C 보류", "source-policy와 credential custody 선행", "연기 가능"),
        "D-M2-002": ("source-policy human approval record를 확정할 것인가?", "kill switch 코드는 PASS, 인간 승인 기록은 없음", "A 서명 승인 / B 조건부 승인 / C 보류", "A", "운영 권한과 중단조건을 감사 가능하게 고정", "M2 전까지만 연기 가능"),
        "D-SEC-001": ("API key 회전·보관·runtime injection 정책을 승인할 것인가?", "사용 가능한 NCS/Work24 credential 없음; 노출 0", "A secret store+회전 / B 현행 유지 / C API 미사용", "A", "키를 artifact와 분리하고 live probe를 통제", "live probe 전까지만 연기 가능"),
        "D-M3-001": ("core AI·IT cohort 범위를 동결할 것인가?", "candidate code set은 있으나 human freeze 없음", "A 69/51안 동결 / B 통신02 포함 / C 방송03 포함 후 재검토", "A를 검토 후 signed release", "분모와 NCS 분석 범위의 사전고정", "M3 전까지 연기 가능"),
        "D-DISC-001": ("LLM_REFERENCE 사용 사실과 한계를 기사에 공개할 것인가?", "현재 HUMAN_GOLD 0, LLM reference 실행 0", "A 본문+방법론 공개 / B 방법론만 / C 사용 안 함", "A", "HUMAN_GOLD와 혼동 방지", "기사 작성 전까지 연기 가능"),
    }
    for row in decisions:
        q, evidence, options, rec, reason, defer = detail[row["decisionId"]]
        packet_lines += [f"## {row['decisionId']}", "", f"질문: {q}", "", f"현재 증거: {evidence}", "", f"선택지: {options}", "", f"권고안: {rec}", "", f"권고 이유: {reason}", "", f"선택별 영향: 승인 시 해당 단계 실행 권한이 열리고, 보류 시 구현·offline QA만 유지됩니다.", "", f"결정 연기 가능 여부: {defer}", ""]
    (REPORT / "P4_M1_5_USER_DECISION_PACKET.md").write_text("\n".join(packet_lines) + "\n", encoding="utf-8")

    report_md = f"""# P4 M1.5 v4.0 Implementation Report

## Executive verdict

`P4_M1_5_IMPLEMENTATION_READY_FOR_INDEPENDENT_AUDIT`

이 판정은 코드·schema·offline fixture·tests·observed replay가 독립감사에 넘길 수 있다는 뜻이다. production 데이터 또는 분석 준비 완료를 뜻하지 않는다.

## Authority

- Project root: `DSJA/project_4`
- SSOT: `shared/ssot/v4.0/P4_final_design_v4.0.md`
- SSOT SHA-256: `{SSOT_SHA}`
- Implementation evidence Git HEAD: `{implementation_head}`
- Run ID: `{RUN_ID}`

## Verified implementation

- Legacy baselines after fetch: A1 remote `3ad43c39` (local `00b2e6b`, ahead 2/behind 10), A2 `9a0571db`, A3 `b64270bd`, A4 `7a9feccc`, A5 audit baseline `3a5bd066`.
- M1.5 component heads: A1 `5a78cac2`, A2 `879b2c2e`, A3 `b20bdf5`, A4 `3396eb66`; each component branch was pushed with 0/0 remote divergence.
- Documentation authority branch: `docs/p4-final-design-v4` at `9a5e49d7`, remote parity 0/0.
- Control: 12 schemas, 6 stages, 26 gates, 11 dependency edges; validator PASS.
- Crawl: fail-closed validator, topology/current-run binding, ActivityText fallback, source-policy kill switches; 38 tests PASS.
- Pipeline: deterministic semantic/OCR/structure/RQ2-B contract; 116 tests PASS.
- NCS: API/corpus/retrieval/reference/temporal/calibration implementation; 84 tests PASS.
- Independent Agent 5 audit: PASS_WITH_FINDINGS; tracked manifests/checksums PASS, with ignored raw-byte portability recorded.
- API fixtures: 8 synthetic success/empty/auth/parameter fixtures. Live calls 0; live probe NOT_EVALUATED.
- NCS candidate corpus: 13,442 units, 14,930 nodes, 14,906 edges; bridge/crosswalk 0; promotionAllowed=false.

## Observed replay

- postings: {summary['postingRows']}
- authoritative dates: {summary['canonicalPostedAtCount']}/{summary['expectedPostingRows']} ({summary['canonicalPostedAtCoverage']:.2%})
- period mismatch: {summary['periodMonthMismatchCount']}
- invalid canonical enums: 0
- raw SSR: {summary['rawManifestRows']}; raw SHA mismatch: {summary['rawShaMismatchCount']}; declared/existence mismatch: {summary['rawExistenceMismatchCount']}
- requirement facts: {summary['requirementFactRows']}; source blocks: {summary['sourceBlockRows']}; semantic chunks: {summary['semanticChunkRows']}
- OCR candidates: {summary['ocrCandidateRows']} rows / {summary['ocrCandidatePostingCount']} postings; asset bytes: {summary['ocrAssetBytesAvailableCount']}
- production Linkareer calls: 0; live API probes: 0; article numbers: 0

## Gate interpretation

M1.5-P is PARTIAL, M1.5-0 is PASS_WITH_FINDINGS, and M1.5-A through D remain BLOCKED or NOT_EVALUATED where evidence is absent. `highDemandScore` remains NULL. No production or analysis promotion is made.

Notebook이 실행됐다는 것은 분석데이터가 준비됐다는 뜻이 아니다.

구조적 QA 통과는 의미적 변수 완성도를 보장하지 않는다.

Observed-development 결과는 기사 결과가 아니다.

CSV는 canonical source가 아니다.

NCS candidate 생성은 NCS mapping 품질게이트 통과가 아니다.

## Roadmap

M1 snapshot freeze → M1.5 semantic QA → M2 full crawl → production preprocess → M3 gold/reference → analysis → article.
"""
    (REPORT / "P4_M1_5_IMPLEMENTATION_REPORT.md").write_text(report_md, encoding="utf-8")

    evidence_files = sorted(path for path in REPORT.rglob("*") if path.is_file() and path.name != "EVIDENCE_MANIFEST.sha256")
    external_evidence = [
        PROJECT / "integration" / "API_CONTRACT_REGISTRY.yaml",
        PROJECT / "integration" / "SEMANTIC_STAGE_REGISTRY.yaml",
        PROJECT / "shared" / "contracts" / "api_contract" / "v4.0" / "AUTHORITY.json",
        PROJECT / "ncs_mapping" / "reports" / "api_probe" / "NCS_OFFLINE_PROBE_STATUS.json",
        PROJECT / "ncs_mapping" / "reports" / "api_probe" / "WORK24_OFFLINE_PROBE_STATUS.json",
        PROJECT / "ncs_mapping" / "reports" / "v4" / "NCS_CORPUS_CANDIDATE_MANIFEST.json",
    ]
    manifest_lines = [f"{sha(path)}  {path.relative_to(REPORT).as_posix()}\n" for path in evidence_files]
    manifest_lines += [f"{sha(path)}  {os.path.relpath(path, REPORT)}\n" for path in external_evidence]
    (REPORT / "EVIDENCE_MANIFEST.sha256").write_text("".join(manifest_lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "reportFiles": len(evidence_files) + 1, "implementationHead": implementation_head}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
