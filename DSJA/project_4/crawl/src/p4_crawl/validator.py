"""Fail-closed adapter for the read-only Agent 2 release validator."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUATED = "NOT_EVALUATED"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate_validator_artifact(
    artifact: Mapping[str, Any] | None,
    *,
    expected_run_id: str,
    expected_input_sha256: str,
    expected_source_notebook_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate the complete validator evidence envelope before promotion.

    Invocation itself is never evidence of success. Missing evidence stays
    ``NOT_EVALUATED``; malformed, stale, or failed evidence is ``FAIL``.
    """

    if artifact is None:
        return {
            "gateStatus": NOT_EVALUATED,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_ARTIFACT_MISSING",
        }

    required = {
        "processExitCode",
        "status",
        "runId",
        "inputSha256",
        "validation",
    }
    missing = sorted(required.difference(artifact))
    if missing:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_ARTIFACT_FIELDS_MISSING",
            "missingFields": missing,
        }
    if artifact["processExitCode"] != 0:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_PROCESS_EXIT_NONZERO",
        }
    if artifact["runId"] != expected_run_id:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_RUN_ID_MISMATCH",
        }
    if artifact["inputSha256"] != expected_input_sha256:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_INPUT_SHA256_MISMATCH",
        }
    if expected_source_notebook_sha256 is not None:
        if artifact.get("sourceNotebookSha256") != expected_source_notebook_sha256:
            return {
                "gateStatus": FAIL,
                "crawlReleaseReady": False,
                "reason": "VALIDATOR_SOURCE_NOTEBOOK_SHA256_MISMATCH",
            }
    if artifact["status"] != PASS:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_STATUS_NOT_PASS",
        }
    validation = artifact["validation"]
    if not isinstance(validation, Mapping):
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "VALIDATOR_PAYLOAD_INVALID",
        }
    full_status = validation.get("fullCorpusAcceptance")
    if isinstance(full_status, Mapping):
        full_status = full_status.get("status")
    if full_status != PASS:
        return {
            "gateStatus": FAIL,
            "crawlReleaseReady": False,
            "reason": "FULL_CORPUS_ACCEPTANCE_NOT_PASS",
        }
    return {
        "gateStatus": PASS,
        "crawlReleaseReady": True,
        "reason": "VALIDATOR_EVIDENCE_PASS",
    }
