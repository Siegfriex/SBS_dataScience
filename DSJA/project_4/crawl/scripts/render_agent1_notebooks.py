"""Render/check deterministic Agent 1 observed-development notebooks."""

from __future__ import annotations

import argparse
import csv
import difflib
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

CRAWL_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = CRAWL_ROOT / "notebooks"
MATRIX_PATH = CRAWL_ROOT / "reports" / "m1" / "AGENT1_NOTEBOOK_MODULE_CALL_MATRIX.csv"
OUTPUT_ROOT = "crawl/runs/notebooks/observed-dev/AGENT1_20260806_01"
OBSERVED_HANDOFF = "crawl/observed_inputs/OBSERVED_INPUT_20260806_01/HANDOFF.json"
RELEASE_HANDOFF = "crawl/releases/CRAWL_20260806_03/HANDOFF.json"

SPECS = (
    {
        "name": "00RecoverSourceState",
        "stage": "A1-00-RECOVER",
        "schema": "source-policy-run-v1",
        "input": RELEASE_HANDOFF,
        "title": "Recover source state and rebuild the reference-only observed package",
        "calls": "audit_input_manifest;recover_source_state;build_observed_input_package;write_stage_artifacts",
        "operation": '''from p4_crawl.release import build_observed_input_package, recover_source_state

recovery = recover_source_state(config, STAGE_ROOT)
package_root = STAGE_ROOT / "observed_package"
package = build_observed_input_package(config, package_root)
metrics = {**recovery, "observedPackagePostingRows": package["postingRows"], "observedPackageRawHtmlRows": package["rawHtmlRows"]}
quality = [
    quality_row("SOURCE_POLICY_READY", "RAW_LINEAGE", "ERROR", "PASS" if recovery["rawHtmlRows"] == 29 else "FAIL", recovery["rawHtmlRows"], 29, "resume_state.json"),
    quality_row("OBSERVED_PACKAGE_REFERENCE_ONLY", "NO_RAW_COPY", "ERROR", "PASS" if package["rawCopied"] is False else "FAIL", package["rawCopied"], False, "observed_package/HANDOFF.json"),
]
persisted_files = [path for path in STAGE_ROOT.rglob("*") if path.is_file()]''',
        "warning": "Observed input is partial and cannot be promoted to empirical analysis.",
    },
    {
        "name": "01CollectLinkareerIndex",
        "stage": "A1-01-INDEX",
        "schema": "crawl-index-v1",
        "input": OBSERVED_HANDOFF,
        "title": "Exercise the registry-owned Linkareer APQ query in fixture dry-run mode",
        "calls": "audit_input_manifest;run_fixture_apq_query;APQClient.fetch;QueryRegistry.load;write_stage_artifacts",
        "operation": '''from p4_crawl.observed import run_fixture_apq_query

metrics = run_fixture_apq_query(CRAWL_ROOT, STAGE_ROOT)
quality = [
    quality_row("INDEX_FIXTURE_APQ_READY", "REGISTRY_APQ", "ERROR", "PASS" if metrics["transportCalls"] == 1 else "FAIL", metrics["transportCalls"], 1, "fixture_apq_audit.json"),
    quality_row("NO_LIVE_CRAWL_M1", "NETWORK_ZERO", "ERROR", "PASS" if metrics["networkCalls"] == 0 else "FAIL", metrics["networkCalls"], 0, "fixture_apq_audit.json"),
]
persisted_files = [STAGE_ROOT / name for name in ["posting_discovery_index.parquet", "posting_discovery_index.csv", "fixture_apq_audit.json"]]''',
        "warning": "Fixture APQ success is not monthly production coverage.",
    },
    {
        "name": "02CollectPostingDetail",
        "stage": "A1-02-DETAIL",
        "schema": "posting-manifest-v1",
        "input": OBSERVED_HANDOFF,
        "title": "Replay and parse all 29 verified local Linkareer SSR pages",
        "calls": "audit_input_manifest;replay_observed_raw;extract_detail_record;write_stage_artifacts",
        "operation": '''from p4_crawl.observed import replay_observed_raw

OBSERVED_ROOT = INPUT_MANIFEST.parent
metrics = replay_observed_raw(PROJECT_ROOT, OBSERVED_ROOT, STAGE_ROOT)
quality = [
    quality_row("CRAWL_OBSERVED_INPUT_READY", "RAW_REPLAY", "ERROR", "PASS" if metrics["rawReplayPassed"] == 29 and metrics["rawReplayFailed"] == 0 else "FAIL", metrics["rawReplayPassed"], 29, "raw_replay_metrics.json"),
    quality_row("ACTIVITY_TEXT_RECOVERED", "SSR_APOLLO_PARSE", "ERROR", "PASS" if metrics["activityTextRecovered"] == 29 else "FAIL", metrics["activityTextRecovered"], 29, "posting_detail_replay.parquet"),
    quality_row("RAW_PII_NOT_PERSISTED", "PII_POLICY", "ERROR", "PASS" if not metrics["managerPiiPersisted"] else "FAIL", metrics["managerPiiPersisted"], False, "raw_replay_metrics.json"),
]
persisted_files = [STAGE_ROOT / name for name in ["posting_detail_replay.parquet", "posting_detail_replay.csv", "raw_replay_failures.json", "raw_replay_metrics.json"]]''',
        "warning": "Only the 29 observed raw pages are replayed; this is not full-corpus detail coverage.",
    },
    {
        "name": "03CollectPostingAssets",
        "stage": "A1-03-ASSET",
        "schema": "asset-manifest-v1",
        "input": OBSERVED_HANDOFF,
        "title": "Route asset metadata without downloads or external ATS transport",
        "calls": "audit_input_manifest;route_observed_asset_metadata;build_asset_frontier;PolicyHttpClient.get;write_stage_artifacts",
        "operation": '''from p4_crawl.observed import route_observed_asset_metadata

DETAIL_REPLAY = RUN_ROOT / "A1-02-DETAIL" / "posting_detail_replay.parquet"
metrics = route_observed_asset_metadata(DETAIL_REPLAY, STAGE_ROOT)
quality = [
    quality_row("EXTERNAL_ATS_ZERO_CALL", "SOURCE_POLICY", "ERROR", "PASS" if metrics["externalAtsTransportCalls"] == 0 else "FAIL", metrics["externalAtsTransportCalls"], 0, "asset_routing_metrics.json"),
    quality_row("M1_ASSET_METADATA_ONLY", "NO_ASSET_DOWNLOAD", "ERROR", "PASS" if metrics["assetsFetched"] == 0 else "FAIL", metrics["assetsFetched"], 0, "asset_manifest.jsonl"),
    quality_row("CRAWL_ASSET_LINEAGE_READY", "FULL_ASSET_LINEAGE", "WARNING", "NOT_EVALUATED", metrics["assetsFetched"], "full corpus", "asset_routing_metrics.json"),
]
persisted_files = [STAGE_ROOT / name for name in ["asset_frontier.parquet", "asset_frontier.csv", "ocr_candidate_manifest.parquet", "ocr_candidate_manifest.csv", "asset_manifest.jsonl", "asset_routing_metrics.json"]]''',
        "warning": "Asset candidates are metadata-only; no Linkareer asset or external ATS URL is fetched.",
    },
    {
        "name": "04BuildCrawlRelease",
        "stage": "A1-04-RELEASE",
        "schema": "crawl-release-v1",
        "input": OBSERVED_HANDOFF,
        "title": "Validate the observed package and invoke the Agent 2 validator adapter without release promotion",
        "calls": "audit_input_manifest;validate_observed_package;invoke_agent2_validator;write_stage_artifacts",
        "operation": '''from p4_crawl.observed import invoke_agent2_validator, validate_observed_package
from p4_crawl.storage import atomic_write_json

observed_validation = validate_observed_package(INPUT_MANIFEST.parent)
agent2_validation = invoke_agent2_validator(PROJECT_ROOT, CRAWL_ROOT / "releases" / CRAWL_RELEASE_ID / "HANDOFF.json")
atomic_write_json(STAGE_ROOT / "observed_package_validation.json", observed_validation)
atomic_write_json(STAGE_ROOT / "agent2_validator_result.json", agent2_validation)
metrics = {**observed_validation, "agent2ValidatorStatus": agent2_validation["status"], "crawlReleaseReady": False}
quality = [
    quality_row("CRAWL_OBSERVED_INPUT_READY", "OBSERVED_PACKAGE", "ERROR", "PASS" if observed_validation["observedInputReady"] else "FAIL", observed_validation["observedInputReady"], True, "observed_package_validation.json"),
    quality_row("AGENT2_VALIDATOR", "CROSS_AGENT_VALIDATION", "WARNING", "NOT_EVALUATED" if not agent2_validation["executed"] else "PASS", agent2_validation["status"], "integrated validator", "agent2_validator_result.json"),
    quality_row("CRAWL_RELEASE_READY", "PRODUCTION_PROMOTION", "ERROR", "NOT_EVALUATED", False, "full production corpus", "observed_package_validation.json"),
]
persisted_files = [STAGE_ROOT / "observed_package_validation.json", STAGE_ROOT / "agent2_validator_result.json"]''',
        "warning": "CRAWL_RELEASE_READY remains NOT_EVALUATED; observed validation cannot promote a production release.",
    },
)

TITLE_DETAILS = {
    "00RecoverSourceState": {
        "outputs": "resume_state, remaining_months, detail/asset frontier, reference-only observed package",
        "prior": "NOT_EVALUATED",
        "next": "A1-01-INDEX의 source-policy 및 입력 기준",
    },
    "01CollectLinkareerIndex": {
        "outputs": "fixture APQ audit와 posting_discovery_index CSV/Parquet",
        "prior": "SOURCE_POLICY_READY",
        "next": "A1-02-DETAIL의 APQ/query-registry 작동 근거",
    },
    "02CollectPostingDetail": {
        "outputs": "29건 posting_detail_replay CSV/Parquet와 replay QA",
        "prior": "INDEX_FIXTURE_APQ_READY",
        "next": "A1-03-ASSET metadata candidate routing 및 Agent 2 observed parser",
    },
    "03CollectPostingAssets": {
        "outputs": "asset_frontier, OCR candidate manifest, 빈 asset manifest",
        "prior": "CRAWL_OBSERVED_INPUT_READY",
        "next": "A1-04-RELEASE observed package 검증; production asset 수집은 미승격",
    },
    "04BuildCrawlRelease": {
        "outputs": "observed package validation과 Agent 2 validator adapter 결과",
        "prior": "CRAWL_OBSERVED_INPUT_READY",
        "next": "Agent 2 observed-development handoff; CRAWL_RELEASE_READY 선언 금지",
    },
}

PARAMETERS_TEMPLATE = '''RUN_MODE = "observed-dev"
AGENT_ID = "P4-A1-SOURCE"
STAGE_ID = "{stage}"
CONTRACT_VERSION = "2.1.2"
SCHEMA_VERSION = "{schema}"
DATA_VERSION = "observed-dev-20260806.1"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
AS_OF_DATE = "2026-08-06"
INPUT_MANIFEST_PATH = "{input}"
OUTPUT_ROOT = "{output}"
RANDOM_SEED = 20260806
FAIL_ON_GATE = True
EMPIRICAL_ANALYSIS_ALLOWED = False'''

ENVIRONMENT = '''from pathlib import Path
import sys

def locate_project_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "crawl" / "src" / "p4_crawl").is_dir():
            return candidate
        nested = candidate / "DSJA" / "project_4"
        if (nested / "crawl" / "src" / "p4_crawl").is_dir():
            return nested
    raise RuntimeError("Could not locate DSJA/project_4")

PROJECT_ROOT = locate_project_root(Path.cwd())
sys.path.insert(0, str(PROJECT_ROOT / "crawl" / "src"))
from p4_crawl.config import RunConfig
from p4_crawl.observed import require_repository_relative

assert RUN_MODE == "observed-dev"
assert CONTRACT_VERSION == "2.1.2"
assert CRAWL_RELEASE_ID == "CRAWL_20260806_03"
assert EMPIRICAL_ANALYSIS_ALLOWED is False
assert Path(OUTPUT_ROOT).as_posix().startswith("crawl/runs/notebooks/observed-dev/")
require_repository_relative(INPUT_MANIFEST_PATH)
require_repository_relative(OUTPUT_ROOT)

CRAWL_ROOT = PROJECT_ROOT / "crawl"
RUN_ROOT = PROJECT_ROOT / OUTPUT_ROOT
STAGE_ROOT = RUN_ROOT / STAGE_ID
INPUT_MANIFEST = PROJECT_ROOT / INPUT_MANIFEST_PATH
run_id = Path(OUTPUT_ROOT).relative_to("crawl/runs").as_posix()
config = RunConfig(
    project_root=PROJECT_ROOT, run_id=run_id, run_mode=RUN_MODE,
    contract_version=CONTRACT_VERSION, crawl_release_id=CRAWL_RELEASE_ID,
    data_version=DATA_VERSION, as_of_date=AS_OF_DATE, random_seed=RANDOM_SEED,
)
PARAMETERS = {name: globals()[name] for name in [
    "RUN_MODE", "AGENT_ID", "STAGE_ID", "CONTRACT_VERSION", "SCHEMA_VERSION",
    "DATA_VERSION", "CRAWL_RELEASE_ID", "AS_OF_DATE", "INPUT_MANIFEST_PATH",
    "OUTPUT_ROOT", "RANDOM_SEED", "FAIL_ON_GATE", "EMPIRICAL_ANALYSIS_ALLOWED",
]}

def quality_row(gate, rule, severity, status, observed, threshold, evidence):
    return {
        "gateId": gate, "ruleId": rule, "severity": severity, "status": status,
        "observedValue": observed, "threshold": threshold,
        "evidencePath": f"{OUTPUT_ROOT}/{STAGE_ID}/{evidence}",
    }'''

INPUT_AUDIT = '''from p4_crawl.observed import audit_input_manifest

input_audit = audit_input_manifest(PROJECT_ROOT, INPUT_MANIFEST_PATH, CRAWL_RELEASE_ID)
assert input_audit["contractVersion"] == CONTRACT_VERSION
input_audit'''

FINALIZE = '''from p4_crawl.stage import write_stage_artifacts

manifest = write_stage_artifacts(
    config=config, stage_id=STAGE_ID, schema_version=SCHEMA_VERSION,
    started_at=f"{AS_OF_DATE}T00:00:00+09:00", parameters=PARAMETERS,
    input_manifest_path=INPUT_MANIFEST, stage_root=STAGE_ROOT,
    metric_values=metrics, quality_rows=quality, persisted_files=persisted_files,
    warnings=[STAGE_WARNING], branch="agent/p4-crawl-release-v2",
)
if FAIL_ON_GATE and any(row["status"] == "FAIL" for row in quality):
    raise RuntimeError(f"{STAGE_ID} quality gate failed")
{"stageId": STAGE_ID, "status": manifest["status"], "metrics": metrics, "artifacts": manifest["terminationArtifacts"]}'''


def render_notebook(spec: dict) -> str:
    prefix = spec["stage"].lower()
    detail = TITLE_DETAILS[spec["name"]]
    cells = [
        new_markdown_cell(
            f"# {spec['name']}\n\n"
            f"- 목적: {spec['title']}\n"
            "- 담당 Agent: `P4-A1-SOURCE`\n"
            f"- Stage ID: `{spec['stage']}`\n"
            f"- 입력: `{spec['input']}`\n"
            f"- 처리: `{spec['calls']}` 모듈 호출만 수행\n"
            f"- 출력: {detail['outputs']} 및 4개 종료 artifact\n"
            f"- 선행 Gate: `{detail['prior']}`\n"
            f"- 후속 활용: {detail['next']}\n\n"
            "이 Notebook은 orchestration-only이며 empirical analysis와 production promotion을 활성화하지 않는다.",
            id=f"{prefix}-title",
        ),
        new_code_cell(
            PARAMETERS_TEMPLATE.format(stage=spec["stage"], schema=spec["schema"], input=spec["input"], output=OUTPUT_ROOT),
            metadata={"tags": ["parameters"]}, id=f"{prefix}-parameters",
        ),
        new_markdown_cell("## Imports and isolated observed-development environment", id=f"{prefix}-environment-title"),
        new_code_cell(ENVIRONMENT, id=f"{prefix}-environment"),
        new_markdown_cell("## Input and checksum audit", id=f"{prefix}-audit-title"),
        new_code_cell(INPUT_AUDIT, id=f"{prefix}-audit"),
        new_markdown_cell("## Stage module call", id=f"{prefix}-operation-title"),
        new_code_cell(f'STAGE_WARNING = {spec["warning"]!r}\n' + spec["operation"], id=f"{prefix}-operation"),
        new_markdown_cell("## Termination artifacts and gate result", id=f"{prefix}-finalize-title"),
        new_code_cell(FINALIZE, id=f"{prefix}-finalize"),
        new_markdown_cell(
            f"Observed-development interpretation: {spec['warning']} Analysis and production readiness remain disabled.",
            id=f"{prefix}-interpretation",
        ),
    ]
    notebook = new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "p4": {"agentId": "P4-A1-SOURCE", "stageId": spec["stage"], "runMode": "observed-dev"},
        },
    )
    nbformat.validate(notebook)
    return nbformat.writes(notebook, version=4)


def write_matrix() -> None:
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATRIX_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["notebook", "stageId", "schemaVersion", "inputManifest", "moduleCalls", "runMode", "liveNetwork"],
            lineterminator="\n",
        )
        writer.writeheader()
        for spec in SPECS:
            writer.writerow({
                "notebook": f"crawl/notebooks/{spec['name']}.ipynb", "stageId": spec["stage"],
                "schemaVersion": spec["schema"], "inputManifest": spec["input"], "moduleCalls": spec["calls"],
                "runMode": "observed-dev", "liveNetwork": "false",
            })


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--render", action="store_true")
    group.add_argument("--force", action="store_true")
    args = parser.parse_args()
    differences = []
    for spec in SPECS:
        path = NOTEBOOK_ROOT / f"{spec['name']}.ipynb"
        rendered = render_notebook(spec)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != rendered:
            differences.append(path)
            if args.render:
                print("".join(difflib.unified_diff(current.splitlines(True), rendered.splitlines(True), fromfile=str(path), tofile=f"{path} (rendered)")))
            if args.force:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered, encoding="utf-8", newline="\n")
    if args.force:
        write_matrix()
        return 0
    if differences:
        print("Notebook render drift:", *(str(path) for path in differences), sep="\n- ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
