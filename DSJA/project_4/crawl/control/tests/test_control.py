from __future__ import annotations

import copy
import csv
import json
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


CONTROL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL_DIR))

import validate_control as control  # noqa: E402


class ControlLayerTests(unittest.TestCase):
    def load_schema(self, name: str) -> dict:
        with (CONTROL_DIR / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def validator(self, name: str) -> Draft202012Validator:
        return Draft202012Validator(self.load_schema(name), format_checker=FormatChecker())

    def test_complete_control_validation(self) -> None:
        self.assertEqual(control.validate_control(CONTROL_DIR), [])

    def test_registry_has_exact_28_stages_and_four_artifacts(self) -> None:
        with (CONTROL_DIR / "NOTEBOOK_STAGE_REGISTRY.yaml").open(encoding="utf-8") as handle:
            registry = yaml.safe_load(handle)
        self.assertEqual([stage["stageId"] for stage in registry["stages"]], control.EXPECTED_STAGE_IDS)
        self.assertEqual(registry["requiredTerminationArtifacts"], control.EXPECTED_TERMINATION_ARTIFACTS)

    def test_gate_matrix_has_exact_18_gates(self) -> None:
        with (CONTROL_DIR / "NOTEBOOK_GATE_MATRIX.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["gateId"] for row in rows], control.EXPECTED_GATE_IDS)

    def test_observed_execution_constants_are_accepted(self) -> None:
        self.validator("NOTEBOOK_EXECUTION_CONTRACT.schema.json").validate(
            control.observed_execution_example()
        )

    def test_observed_execution_cannot_enable_analysis(self) -> None:
        instance = copy.deepcopy(control.observed_execution_example())
        instance["empiricalAnalysisAllowed"] = True
        with self.assertRaises(ValidationError):
            self.validator("NOTEBOOK_EXECUTION_CONTRACT.schema.json").validate(instance)

    def test_observed_execution_cannot_enable_promotion(self) -> None:
        instance = copy.deepcopy(control.observed_execution_example())
        instance["promotionAllowed"] = True
        with self.assertRaises(ValidationError):
            self.validator("NOTEBOOK_EXECUTION_CONTRACT.schema.json").validate(instance)

    def test_observed_manifest_rejects_wrong_release(self) -> None:
        instance = copy.deepcopy(control.observed_manifest_example())
        instance["crawlReleaseId"] = "CRAWL_OTHER"
        with self.assertRaises(ValidationError):
            self.validator("STAGE_MANIFEST.schema.json").validate(instance)

    def test_manifest_rejects_changed_termination_artifacts(self) -> None:
        instance = copy.deepcopy(control.observed_manifest_example())
        instance["terminationArtifacts"].pop()
        with self.assertRaises(ValidationError):
            self.validator("STAGE_MANIFEST.schema.json").validate(instance)

    def test_execution_rejects_absolute_output_path(self) -> None:
        instance = copy.deepcopy(control.observed_execution_example())
        instance["outputRoot"] = "/tmp/observed-dev/output"
        with self.assertRaises(ValidationError):
            self.validator("NOTEBOOK_EXECUTION_CONTRACT.schema.json").validate(instance)

    def test_metrics_schema_accepts_complete_metric_semantics(self) -> None:
        self.validator("STAGE_METRICS.schema.json").validate(control.observed_metrics_example())

    def test_zero_denominator_cannot_pass(self) -> None:
        instance = copy.deepcopy(control.observed_metrics_example())
        instance["metrics"][0]["denominator"] = 0
        instance["metrics"][0]["status"] = "PASS"
        with self.assertRaises(ValidationError):
            self.validator("STAGE_METRICS.schema.json").validate(instance)


if __name__ == "__main__":
    unittest.main()
