import ast
from pathlib import Path

import nbformat
import yaml


PIPELINE_ROOT = Path(__file__).resolve().parents[2]


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
        assert notebook.cells[0].metadata.tags == ["parameters"]
        assert notebook.cells[0].source.startswith('RUN_MODE = "observed-dev"')
        assert sum(len(cell.get("outputs", [])) for cell in notebook.cells if cell.cell_type == "code") == 0
        for cell in notebook.cells:
            assert cell.id not in seen_ids
            seen_ids.add(cell.id)
            if cell.cell_type == "code":
                ast.parse(cell.source)
        assert "run_observed_stage" in notebook.cells[3].source
        assert "stage_manifest.json" in notebook.cells[-1].source
