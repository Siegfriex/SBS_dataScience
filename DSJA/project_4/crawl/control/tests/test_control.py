from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


CONTROL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL_DIR))

import validate_control as control  # noqa: E402
import notebook_bundle as bundle  # noqa: E402


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
        self.assertEqual(set(stage["stageId"] for stage in registry["stages"]), set(control.EXPECTED_STAGE_IDS))
        self.assertEqual(registry["requiredTerminationArtifacts"], control.EXPECTED_TERMINATION_ARTIFACTS)

    def test_registry_topology_places_a4_producers_before_a2_consumers(self) -> None:
        with (CONTROL_DIR / "NOTEBOOK_STAGE_REGISTRY.yaml").open(encoding="utf-8") as handle:
            registry = yaml.safe_load(handle)
        order = control.deterministic_topological_order(registry["stages"])
        position = {stage_id: index for index, stage_id in enumerate(order)}
        self.assertLess(position["A4-00-NCS-SOURCE"], position["A2-08-NCS-LOAD"])
        self.assertLess(position["A4-01-CODESET"], position["A2-08-NCS-LOAD"])
        self.assertLess(position["A4-03-MAP-OBSERVED"], position["A2-09-NCS-MAP"])
        self.assertLess(position["A4-04-EXPORT"], position["A2-09-NCS-MAP"])

    def test_topology_rejects_cycle(self) -> None:
        stages = [
            {"stageId": "A1-X", "upstreamStages": ["A1-Y"]},
            {"stageId": "A1-Y", "upstreamStages": ["A1-X"]},
        ]
        with self.assertRaisesRegex(ValueError, "cycle"):
            control.deterministic_topological_order(stages)

    def test_topology_rejects_unknown_upstream(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            control.deterministic_topological_order([
                {"stageId": "A1-X", "upstreamStages": ["A1-MISSING"]},
            ])

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

    def _current_run_fixture(self, *, mutations: dict | None = None, duplicate: bool = False) -> tuple[Path, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        run = root / "run"
        artifact = root / "run" / "artifacts" / "A1-X"
        artifact.mkdir(parents=True)
        native = artifact / "stage_manifest.json"
        native.write_text("{}", encoding="utf-8")
        executed = root / "run" / "executed" / "x.ipynb"
        executed.parent.mkdir(parents=True)
        executed.write_text("{}", encoding="utf-8")
        (run / "NOTEBOOK_EXECUTION_RESULTS.csv").parent.mkdir(parents=True, exist_ok=True)
        bundle.write_csv(run / "NOTEBOOK_EXECUTION_RESULTS.csv", [{
            "agentId": "P4-A1-SOURCE", "stageId": "A1-X", "notebook": "crawl/notebooks/x.ipynb",
            "status": "PASS", "sourceSha256": "a" * 64, "stageOutputRoot": "run/artifacts/A1-X",
            "parameterSha256": "b" * 64,
        }])
        payload = {
            "manifestVersion": "current-run-manifest-v1", "currentRunId": bundle.MASTER_RUN_ID,
            "stageId": "A1-X", "agentId": "P4-A1-SOURCE", "status": "PASS",
            "sourceNotebookPath": "crawl/notebooks/x.ipynb", "sourceNotebookSha256": "a" * 64,
            "sourceGitRef": "HEAD", "sourceGitBlobSha": "c" * 40,
            "parameterSha256": "b" * 64, "artifactRoot": "run/artifacts/A1-X",
            "executedNotebookPath": "run/executed/x.ipynb", "executedNotebookSha256": bundle.sha256_file(executed),
            "nativeStageManifestPath": "run/artifacts/A1-X/stage_manifest.json",
            "nativeStageManifestSha256": bundle.sha256_file(native), "createdAt": "2026-08-06T00:00:00Z", "errors": [],
        }
        payload.update(mutations or {})
        (artifact / bundle.CURRENT_RUN_MANIFEST).write_text(json.dumps(payload), encoding="utf-8")
        if duplicate:
            other = run / "duplicate"
            other.mkdir()
            (other / bundle.CURRENT_RUN_MANIFEST).write_text(json.dumps(payload), encoding="utf-8")
        return root, temporary

    def _collect_fixture(self, root: Path) -> list[dict]:
        plan = (("P4-A1-SOURCE", "A1-X", "crawl/notebooks/x.ipynb"),)
        source = [{
            "stageId": "A1-X", "sha256": "a" * 64, "gitRef": "HEAD",
            "gitBlobSha": "c" * 40, "gitTracked": True, "gitBlobMatch": True,
        }]
        with patch.object(bundle, "registry_notebook_plan", return_value=plan), patch.object(bundle, "audit_source_bundle", return_value=source):
            return bundle.collect_stage_manifests(root / "run", root)

    def test_current_run_manifest_accepts_exact_binding(self) -> None:
        root, temporary = self._current_run_fixture()
        self.addCleanup(temporary.cleanup)
        self.assertEqual(self._collect_fixture(root)[0]["status"], "SUCCEEDED")

    def test_current_run_manifest_rejects_duplicate(self) -> None:
        root, temporary = self._current_run_fixture(duplicate=True)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(ValueError, "cardinality"):
            self._collect_fixture(root)

    def test_current_run_manifest_rejects_missing_planned_stage(self) -> None:
        root, temporary = self._current_run_fixture()
        self.addCleanup(temporary.cleanup)
        (root / "run" / "artifacts" / "A1-X" / bundle.CURRENT_RUN_MANIFEST).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self._collect_fixture(root)

    def test_current_run_manifest_rejects_stale_run_id(self) -> None:
        root, temporary = self._current_run_fixture(mutations={"currentRunId": "STALE"})
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(ValueError, "currentRunId"):
            self._collect_fixture(root)

    def test_current_run_manifest_rejects_source_parameter_and_artifact_mismatch(self) -> None:
        root, temporary = self._current_run_fixture(mutations={
            "sourceNotebookSha256": "d" * 64,
            "parameterSha256": "e" * 64,
            "artifactRoot": "elsewhere",
        })
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(ValueError, "artifactRoot.*parameterSha256.*sourceNotebookSha256"):
            self._collect_fixture(root)

    def test_git_provenance_rejects_untracked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.ipynb"
            source.write_text("{}", encoding="utf-8")
            import subprocess
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            provenance = bundle.git_blob_provenance(source, root)
            self.assertFalse(provenance["gitTracked"])
            self.assertFalse(provenance["gitBlobMatch"])

    def test_git_provenance_rejects_modified_tracked_source(self) -> None:
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.ipynb"
            source.write_text("{}", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "p4-control@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "P4 Control Test"], cwd=root, check=True)
            subprocess.run(["git", "add", "source.ipynb"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            self.assertTrue(bundle.git_blob_provenance(source, root)["gitBlobMatch"])
            source.write_text('{"changed": true}', encoding="utf-8")
            provenance = bundle.git_blob_provenance(source, root)
            self.assertTrue(provenance["gitTracked"])
            self.assertFalse(provenance["gitBlobMatch"])

    def test_runtime_lock_declares_nbclient_and_not_required_papermill(self) -> None:
        import importlib.metadata as metadata
        lock = self.load_schema("NOTEBOOK_RUNTIME_LOCK.json")
        self.assertEqual(lock["executionEngine"], "nbclient")
        self.assertEqual(lock["papermill"]["status"], "NOT_REQUIRED")
        self.assertIn("beautifulsoup4", lock["packages"])
        for package, specifier in lock["packages"].items():
            self.assertEqual(specifier, "==" + metadata.version(package))


if __name__ == "__main__":
    unittest.main()
