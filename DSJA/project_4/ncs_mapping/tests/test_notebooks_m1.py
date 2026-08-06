import ast
import json
from pathlib import Path

import nbformat

NCS_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    "00NcsSourceAudit.ipynb",
    "01BuildCoreAiItCodeSet.ipynb",
    "02BuildNcsRetrievalIndex.ipynb",
    "03MapObservedDuties.ipynb",
    "04ExportNcsMappingCsv.ipynb",
    "05EvaluateNcsMapping.ipynb",
]

COMMON_PARAMETER_NAMES = {
    "RUN_MODE", "AGENT_ID", "STAGE_ID", "CONTRACT_VERSION", "SCHEMA_VERSION",
    "DATA_VERSION", "CRAWL_RELEASE_ID", "AS_OF_DATE", "INPUT_MANIFEST_PATH",
    "OUTPUT_ROOT", "RANDOM_SEED", "FAIL_ON_GATE", "EMPIRICAL_ANALYSIS_ALLOWED",
}


def test_notebooks_are_thin_clean_and_parseable():
    for name in EXPECTED:
        notebook = nbformat.read(NCS_ROOT / "notebooks" / name, as_version=4)
        nbformat.validate(notebook)
        assert len(notebook.cells) == 6
        assert notebook.cells[0].cell_type == "markdown"
        assert notebook.cells[0].source.startswith("# P4 Agent 4")
        assert notebook.cells[1].cell_type == "code"
        assert "parameters" in notebook.cells[1].metadata.get("tags", [])
        parameter_tree = ast.parse(notebook.cells[1].source)
        assigned = {
            target.id
            for node in parameter_tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
        }
        assert COMMON_PARAMETER_NAMES.issubset(assigned)
        assert 'RUN_MODE = "observed-dev"' in notebook.cells[1].source
        assert 'AGENT_ID = "P4-A4-NCS"' in notebook.cells[1].source
        assert "RANDOM_SEED = 20260806" in notebook.cells[1].source
        assert "FAIL_ON_GATE = True" in notebook.cells[1].source
        assert 'DATA_PROVENANCE = "OBSERVED_DEVELOPMENT_ONLY"' in notebook.cells[1].source
        assert "EMPIRICAL_ANALYSIS_ALLOWED = False" in notebook.cells[1].source
        assert "PROMOTION_ALLOWED = False" in notebook.cells[1].source
        assert all(cell.get("execution_count") is None for cell in notebook.cells if cell.cell_type == "code")
        assert all(not cell.get("outputs") for cell in notebook.cells if cell.cell_type == "code")
        for cell in notebook.cells:
            if cell.cell_type == "code":
                ast.parse(cell.source)
        all_source = "\n".join(cell.source for cell in notebook.cells)
        assert "run_stage(" in all_source
        assert "expected_artifacts" in all_source


def test_notebook_sources_do_not_embed_dense_or_absolute_temp_path():
    for name in EXPECTED:
        raw = (NCS_ROOT / "notebooks" / name).read_text(encoding="utf-8")
        assert "dense_rerank(" not in raw
        assert "/tmp/p4-agent2-observed" not in raw
