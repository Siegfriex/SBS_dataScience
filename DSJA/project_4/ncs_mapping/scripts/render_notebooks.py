"""Deterministically render the six executable Agent 4 notebooks."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_SOURCE_GIT_HEAD = "afac9fd9e1854715759c7d893440cbe89e04c150"
STAGES = [
    ("00NcsSourceAudit.ipynb", "A4-00-NCS-SOURCE", "NCS Source Audit", "Audit 13,442 NCS units, checksum lineage, duplicates, levels, hierarchy codes, and documented name nulls."),
    ("01BuildCoreAiItCodeSet.ipynb", "A4-01-CODESET", "Core AI·IT Code Set", "Deterministically rebuild and review the 120-code set: 69 included and 51 excluded."),
    ("02BuildNcsRetrievalIndex.ipynb", "A4-02-RETRIEVAL", "Lexical Retrieval Index", "Validate aliases and build the same-subcategory lexical index without dense reranking."),
    ("03MapObservedDuties.ipynb", "A4-03-MAP-OBSERVED", "Observed Duty Mapping", "Validate 28 duty rows and materialize lexical top-5 candidates with unmapped preservation."),
    ("04ExportNcsMappingCsv.ipynb", "A4-04-EXPORT", "NCS Mapping Export", "Build six canonical Parquet and UTF-8-SIG inspection CSV pairs."),
    ("05EvaluateNcsMapping.ipynb", "A4-05-EVALUATE", "Gold Evaluation Structure", "Execute the zero-row gold contract and close as NOT_EVALUATED without performance claims."),
]
SCHEMA_VERSIONS = {
    "A4-00-NCS-SOURCE": "ncs-base-v1",
    "A4-01-CODESET": "core-ai-it-v0.1",
    "A4-02-RETRIEVAL": "ncs-retrieval-v1",
    "A4-03-MAP-OBSERVED": "posting-ncs-candidates-v1",
    "A4-04-EXPORT": "ncs-export-v1",
    "A4-05-EVALUATE": "ncs-evaluation-v1",
}
INPUT_MANIFEST_PATHS = {
    "A4-00-NCS-SOURCE": "ncs_mapping/data/processed/ncsUnit.parquet",
    "A4-01-CODESET": "ncs_mapping/data/processed/ncsUnit.parquet",
    "A4-02-RETRIEVAL": "ncs_mapping/configs/ncs_alias_dictionary.yaml",
    "A4-03-MAP-OBSERVED": "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json",
    "A4-04-EXPORT": "ncs_mapping/data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/posting_ncs_candidates.parquet",
    "A4-05-EVALUATE": "ncs_mapping/data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv",
}
TITLE_DETAILS = {
    "A4-00-NCS-SOURCE": ("checksum·중복·level·hierarchy·null 감사", "ncs_units canonical source audit", "NCS_BASE_READY", "core AI·IT codeset build"),
    "A4-01-CODESET": ("core code set deterministic rebuild 및 120/69/51 검증", "core-ai-it-v0.1 review candidate", "NCS_BASE_READY", "lexical retrieval index build"),
    "A4-02-RETRIEVAL": ("alias 검증·lexical index·same-subcategory 제한", "lexical index manifest", "NCS_CODESET_REVIEW_READY", "observed duty top-5 mapping"),
    "A4-03-MAP-OBSERVED": ("28 duty schema/SHA 검증·top-5·unmapped·confidence", "posting_ncs_candidates and posting_ncs_matches", "REQUIREMENT_READY_AND_NCS_RETRIEVAL_READY", "NCS CSV export and Agent 2 handoff"),
    "A4-04-EXPORT": ("6개 canonical Parquet 및 inspection CSV semantic export", "six CSV/Parquet pairs and handoff", "NCS_MAPPING_DEV_READY", "Agent 2 preprocessing integration"),
    "A4-05-EVALUATE": ("zero-row gold 구조 실행 및 NOT_EVALUATED 종료", "null precision/finalCoverage evaluation artifact", "NCS_GOLD_SAMPLE_READY", "future production gold evaluation only"),
}


def _cell_id(stage_id: str, label: str) -> str:
    return hashlib.sha256(f"{stage_id}:{label}".encode()).hexdigest()[:8]


def _parameters(stage_id: str) -> nbformat.NotebookNode:
    source = "\n".join([
        'RUN_MODE = "observed-dev"',
        'AGENT_ID = "P4-A4-NCS"',
        f'STAGE_ID = "{stage_id}"',
        'CONTRACT_VERSION = "2.1.2"',
        f'SCHEMA_VERSION = "{SCHEMA_VERSIONS[stage_id]}"',
        'DATA_VERSION = "observed-dev-20260806.1"',
        'CRAWL_RELEASE_ID = "CRAWL_20260806_03"',
        'AS_OF_DATE = "2026-08-06"',
        f'INPUT_MANIFEST_PATH = "{INPUT_MANIFEST_PATHS[stage_id]}"',
        f'OUTPUT_ROOT = "ncs_mapping/data/runs/observed-dev/NCS_MAPPING_OBSERVED_20260806_01/{stage_id}"',
        'RANDOM_SEED = 20260806',
        'FAIL_ON_GATE = True',
        'EMPIRICAL_ANALYSIS_ALLOWED = False',
        'DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"',
        'PROMOTION_ALLOWED = False',
        'DUTY_INPUT_PATH = ""',
        'GOLD_INPUT_PATH = ""',
        'CONTROL_SCHEMA_DIR = ""',
    ])
    return nbformat.v4.new_code_cell(source, metadata={"tags": ["parameters"]}, id=_cell_id(stage_id, "parameters"))


def _title(stage_id: str, title: str, description: str) -> nbformat.NotebookNode:
    process, output, prior_gate, downstream = TITLE_DETAILS[stage_id]
    source = (
        f"# P4 Agent 4 · {title}\n\n"
        "| 항목 | 명세 |\n"
        "|---|---|\n"
        f"| 목적 | {description} |\n"
        "| 담당 Agent | `P4-A4-NCS` |\n"
        f"| Stage ID | `{stage_id}` |\n"
        f"| 입력 | `{INPUT_MANIFEST_PATHS[stage_id]}` |\n"
        f"| 처리 | {process} |\n"
        f"| 출력 | {output} 및 4개 종료 artifact |\n"
        f"| 선행 Gate | `{prior_gate}` |\n"
        f"| 후속 활용 | {downstream} |\n\n"
        "> Development-only orchestration. Empirical analysis and production promotion are disabled."
    )
    return nbformat.v4.new_markdown_cell(source, id=_cell_id(stage_id, "title"))


def _environment(stage_id: str) -> nbformat.NotebookNode:
    source = (
        "from pathlib import Path\n"
        "import os\n"
        "import sys\n"
        "import pandas as pd\n\n"
        "NCS_ROOT = Path.cwd().resolve()\n"
        "if NCS_ROOT.name != 'ncs_mapping':\n"
        "    raise RuntimeError('run this notebook with cwd=ncs_mapping')\n"
        "sys.path.insert(0, str(NCS_ROOT / 'src'))\n"
        "assert RUN_MODE == 'observed-dev'\n"
        "assert AGENT_ID == 'P4-A4-NCS' and STAGE_ID.startswith('A4-')\n"
        "assert RANDOM_SEED == 20260806 and FAIL_ON_GATE is True\n"
        "assert DATA_PROVENANCE == 'OBSERVED_DEVELOPMENT_ONLY'\n"
        "assert EMPIRICAL_ANALYSIS_ALLOWED is False and PROMOTION_ALLOWED is False\n"
        "resolved_duty_input = DUTY_INPUT_PATH or os.environ.get('P4_A2_DUTY_HANDOFF', '')\n"
        "resolved_gold_input = GOLD_INPUT_PATH or os.environ.get('P4_NCS_GOLD_INPUT', '')\n"
        "resolved_schema_dir = CONTROL_SCHEMA_DIR or os.environ.get('P4_CONTROL_SCHEMA_DIR', '')"
    )
    return nbformat.v4.new_code_cell(source, id=_cell_id(stage_id, "environment"))


def _audit_source(stage_id: str) -> str:
    if stage_id == "A4-00-NCS-SOURCE":
        return (
            "from p4_ncs.quality.stage_artifacts import sha256_file\n\n"
            "ncs_path = NCS_ROOT / 'data/processed/ncsUnit.parquet'\n"
            "ncs_units = pd.read_parquet(ncs_path)\n"
            "input_audit = {\n"
            "    'rows': len(ncs_units),\n"
            "    'parquetSha256': sha256_file(ncs_path),\n"
            "    'duplicateNcsUnitCode': int(ncs_units['ncsUnitCode'].duplicated().sum()),\n"
            "    'levels': sorted(ncs_units['ncsLevel'].dropna().astype(int).unique().tolist()),\n"
            "    'hierarchyCodeNulls': int(ncs_units[['majorCode','middleCode','minorCode','subCode']].isna().sum().sum()),\n"
            "    'hierarchyNameNulls': int(ncs_units[['majorName','middleName','minorName','subName']].isna().sum().sum()),\n"
            "    'rawSha256Distinct': int(ncs_units['rawSha256'].nunique(dropna=True)),\n"
            "}\n"
            "assert input_audit['rows'] == 13_442\n"
            "assert input_audit['duplicateNcsUnitCode'] == 0\n"
            "assert input_audit['levels'] == list(range(1, 9))\n"
            "input_audit"
        )
    if stage_id == "A4-01-CODESET":
        return (
            "from p4_ncs.codeset.core_ai_it import build_core_ai_it_codeset\n\n"
            "ncs_units = pd.read_parquet(NCS_ROOT / 'data/processed/ncsUnit.parquet')\n"
            "rebuilt_codeset = build_core_ai_it_codeset(ncs_units)\n"
            "input_audit = {\n"
            "    'total': len(rebuilt_codeset),\n"
            "    'included': int(rebuilt_codeset['included'].sum()),\n"
            "    'excluded': int((~rebuilt_codeset['included']).sum()),\n"
            "    'codeSetStatus': 'REVIEW_REQUIRED',\n"
            "}\n"
            "assert input_audit == {'total': 120, 'included': 69, 'excluded': 51, 'codeSetStatus': 'REVIEW_REQUIRED'}\n"
            "input_audit"
        )
    if stage_id == "A4-02-RETRIEVAL":
        return (
            "from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary, validate_alias_dictionary\n"
            "from p4_ncs.retrieval.lexical_index import LexicalIndex\n\n"
            "ncs_units = pd.read_parquet(NCS_ROOT / 'data/processed/ncsUnit.parquet')\n"
            "codeset = pd.read_parquet(NCS_ROOT / 'data/processed/coreAiItCodeSet.parquet')\n"
            "aliases = load_alias_dictionary(NCS_ROOT / 'configs/ncs_alias_dictionary.yaml')\n"
            "invalid_aliases = validate_alias_dictionary(aliases, set(codeset['ncsSubCode'].astype(str)))\n"
            "lexical_index = LexicalIndex.build(ncs_units, codeset)\n"
            "probe_hits = lexical_index.search('데이터 분석 모델 개발', top_k=5)\n"
            "input_audit = {'aliases': len(aliases), 'invalidAliases': invalid_aliases, 'documents': len(lexical_index.documents), 'probeTopK': len(probe_hits), 'sameSubcategory': all(hit.matchedNcsUnitCode.startswith(hit.ncsSubCode) for hit in probe_hits)}\n"
            "assert not invalid_aliases and input_audit['probeTopK'] <= 5 and input_audit['sameSubcategory']\n"
            "input_audit"
        )
    if stage_id == "A4-03-MAP-OBSERVED":
        return (
            "from p4_ncs.contracts.observed_duty import load_and_validate_observed_duties\n"
            "from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary\n"
            "from p4_ncs.mapping.observed_baseline import map_observed_duties\n"
            "from p4_ncs.retrieval.lexical_index import LexicalIndex\n\n"
            "if not resolved_duty_input:\n"
            "    raise FileNotFoundError('DUTY_INPUT_PATH or P4_A2_DUTY_HANDOFF is required')\n"
            "duties, duty_validation, duty_envelope = load_and_validate_observed_duties(resolved_duty_input)\n"
            "ncs_units = pd.read_parquet(NCS_ROOT / 'data/processed/ncsUnit.parquet')\n"
            "codeset = pd.read_parquet(NCS_ROOT / 'data/processed/coreAiItCodeSet.parquet')\n"
            "aliases = load_alias_dictionary(NCS_ROOT / 'configs/ncs_alias_dictionary.yaml')\n"
            "candidates_preview, matches_preview = map_observed_duties(duties, LexicalIndex.build(ncs_units, codeset), aliases, codeset, DATA_VERSION, top_k=5)\n"
            "input_audit = {'dutyRows': duty_validation.row_count, 'candidateRows': len(candidates_preview), 'matchRows': len(matches_preview), 'maxTopK': int(candidates_preview.groupby('sectionId').size().max()), 'unmappedRows': int(matches_preview['ncsSubCode'].isna().sum()), 'denseAllNull': bool(matches_preview['denseScore'].isna().all()), 'goldValidatedAny': bool(matches_preview['goldValidatedFlag'].any())}\n"
            "assert input_audit['dutyRows'] == 28 and input_audit['maxTopK'] <= 5\n"
            "assert input_audit['denseAllNull'] and not input_audit['goldValidatedAny']\n"
            "input_audit"
        )
    if stage_id == "A4-04-EXPORT":
        return (
            "from p4_ncs.quality.stage_artifacts import sha256_file\n\n"
            "processed_root = NCS_ROOT / 'data/processed/observed-dev/NCS_MAPPING_OBSERVED_20260806_01'\n"
            "candidate_path = processed_root / 'posting_ncs_candidates.parquet'\n"
            "match_path = processed_root / 'posting_ncs_matches.parquet'\n"
            "input_audit = {'candidateRows': len(pd.read_parquet(candidate_path)), 'matchRows': len(pd.read_parquet(match_path)), 'candidateSha256': sha256_file(candidate_path), 'matchSha256': sha256_file(match_path)}\n"
            "assert input_audit['matchRows'] == 28\n"
            "input_audit"
        )
    return (
        "from p4_ncs.evaluation.gold_evaluation import evaluate_gold_mapping, load_gold_structure\n\n"
        "gold_path = resolved_gold_input or str(NCS_ROOT / 'data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv')\n"
        "gold_structure = load_gold_structure(gold_path)\n"
        "evaluation_preview = evaluate_gold_mapping(gold_structure)\n"
        "input_audit = evaluation_preview.to_dict()\n"
        "assert input_audit['goldRows'] == 0\n"
        "assert input_audit['precision'] is None and input_audit['finalCoverage'] is None\n"
        "assert input_audit['gateStatus'] == 'NOT_EVALUATED'\n"
        "input_audit"
    )


def _build_notebook(filename: str, stage_id: str, title: str, description: str, git_head: str, branch: str) -> nbformat.NotebookNode:
    audit = nbformat.v4.new_code_cell(_audit_source(stage_id), id=_cell_id(stage_id, "input-audit"))
    execute = nbformat.v4.new_code_cell(
        "from p4_ncs.workflow.observed import run_stage\n\n"
        f"stage_manifest = run_stage({stage_id!r}, root=NCS_ROOT, "
        "duty_input_path=resolved_duty_input or None, gold_input_path=resolved_gold_input or None, "
        "schema_dir=resolved_schema_dir or None)\n"
        "stage_manifest",
        id=_cell_id(stage_id, "module-call"),
    )
    terminate = nbformat.v4.new_code_cell(
        "stage_root = NCS_ROOT / 'data/runs' / RUN_MODE / 'NCS_MAPPING_OBSERVED_20260806_01' / stage_manifest['stageId']\n"
        "expected_artifacts = {'stage_manifest.json', 'stage_metrics.json', 'stage_quality.csv', 'CHECKSUMS.sha256'}\n"
        "actual_artifacts = {path.name for path in stage_root.iterdir() if path.is_file()}\n"
        "assert actual_artifacts == expected_artifacts\n"
        "termination_summary = {'stageId': stage_manifest['stageId'], 'status': stage_manifest['status'], 'rowCounts': stage_manifest['rowCounts'], 'artifacts': sorted(actual_artifacts)}\n"
        "termination_summary",
        id=_cell_id(stage_id, "termination"),
    )
    notebook = nbformat.v4.new_notebook(
        cells=[_title(stage_id, title, description), _parameters(stage_id), _environment(stage_id), audit, execute, terminate],
        metadata={
            "agentId": "P4-A4-NCS", "branch": branch, "gitHead": git_head,
            "contractVersion": "2.1.2", "crawlReleaseId": "CRAWL_20260806_03",
            "dataVersion": "observed-dev-20260806.1", "runMode": "observed-dev",
            "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY", "empiricalAnalysisAllowed": False,
            "promotionAllowed": False, "stageId": stage_id, "title": f"P4 Agent 4 · {title}",
            "description": description,
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        },
    )
    nbformat.validate(notebook)
    return notebook


def rendered() -> dict[str, str]:
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    return {
        filename: nbformat.writes(_build_notebook(filename, stage_id, title, description, EXECUTION_SOURCE_GIT_HEAD, branch))
        for filename, stage_id, title, description in STAGES
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--force", action="store_true")
    args = parser.parse_args()
    expected = rendered()
    notebook_dir = ROOT / "notebooks"
    differences = []
    for filename, content in expected.items():
        path = notebook_dir / filename
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            differences.append(filename)
    if args.check:
        if differences:
            print("DIFF " + " ".join(differences))
            return 1
        print("PASS notebooks deterministic")
        return 0
    print(("WOULD_RENDER " if args.render else "RENDER ") + " ".join(differences or ["no changes"]))
    if args.force:
        notebook_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in expected.items():
            (notebook_dir / filename).write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
