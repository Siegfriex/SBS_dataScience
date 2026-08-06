import ast
from pathlib import Path

import nbformat
import yaml

from p4.notebooks.observed_stages import _git_identity


PIPELINE_ROOT = Path(__file__).resolve().parents[2]


def test_stage_artifact_git_identity_labels_detached_head(monkeypatch, tmp_path):
    def fake_check_output(command, **kwargs):
        return "\n" if command[1:3] == ["branch", "--show-current"] else "a" * 40 + "\n"

    monkeypatch.setattr("p4.notebooks.observed_stages.subprocess.check_output", fake_check_output)
    assert _git_identity(tmp_path) == ("DETACHED_HEAD", "a" * 40)


def test_stage_registry_notebooks_are_deterministic_clean_thin_sources():
    spec = yaml.safe_load((PIPELINE_ROOT / "notebook_specs/observed_dev.yaml").read_text(encoding="utf-8"))
    stages = spec["stages"]
    assert [item["id"] for item in stages][:8] == [
        "00ContractAndInputAudit",
        "01LoadCrawlRelease",
        "02ParseAndNormalize",
        "03OcrAndSectionRecovery",
        "04SplitTracks",
        "05ExtractRequirements",
        "06Deduplicate90Days",
        "07LabelCareerAccess",
    ]
    assert [item["id"] for item in stages][-2:] == ["10ExportPreprocessedCsv", "11PreprocessedDataQa"]
    assert all(item["stageId"].startswith("A2-") for item in stages)
    seen_ids: set[str] = set()
    for stage in stages:
        path = PIPELINE_ROOT / "notebooks" / f"{stage['id']}.ipynb"
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        assert notebook.cells[0].cell_type == "markdown"
        assert all(label in notebook.cells[0].source for label in ("목적", "담당 Agent", "Stage ID", "입력", "처리", "출력", "선행 Gate", "후속 활용"))
        assert notebook.cells[1].metadata.tags == ["parameters"]
        assert notebook.cells[1].source.startswith('RUN_MODE = "observed-dev"')
        assignments = [
            node for node in ast.parse(notebook.cells[1].source).body if isinstance(node, (ast.Assign, ast.AnnAssign))
        ]
        assert len(assignments) >= 13
        assert "RANDOM_SEED = 20260806" in notebook.cells[1].source
        assert "FAIL_ON_GATE = True" in notebook.cells[1].source
        assert len(notebook.cells) == 11
        assert sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code") == 0
        for cell in notebook.cells:
            assert cell.id not in seen_ids
            seen_ids.add(cell.id)
            if cell.cell_type == "code":
                ast.parse(cell.source)
        assert "audit_observed_stage_inputs" in notebook.cells[4].source
        assert "_stage(" in notebook.cells[6].source
        assert "stage_manifest.json" in notebook.cells[-1].source
        assert notebook.cells[0].source.startswith(f"# P4 Notebook-First · {stage['stageId']}")
