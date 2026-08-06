from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "integration/build_m1_5_reconciliation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("reconciliation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconciliation_constants_are_fail_closed() -> None:
    module = load_module()
    assert module.BASE == "5508fce02ba5396b5d5a55870f1f879c1f32e8e0"
    assert module.BRANCH == "integration/p4-m1_5-reconcile-for-m2-v1"
    assert module.VALIDATOR_SHA.startswith("NOT_AVAILABLE")


def test_registry_has_exact_reconciliation_stage_boundary() -> None:
    module = load_module()
    import yaml

    registry = yaml.safe_load((PROJECT / "crawl/control/NOTEBOOK_STAGE_REGISTRY.yaml").read_text())
    stages = registry["stages"]
    assert len(stages[:23]) == 23
    assert stages[22]["stageId"] == "A2-11-EXPORT-QA"
    assert stages[-1]["stageId"] == "A3-MASTER"
