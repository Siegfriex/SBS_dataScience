from __future__ import annotations

from p4_crawl.validator import evaluate_validator_artifact


EXPECTED_RUN = "RUN-001"
EXPECTED_SHA = "a" * 64
EXPECTED_NOTEBOOK_SHA = "c" * 64


def artifact(**overrides):
    value = {
        "processExitCode": 0,
        "status": "PASS",
        "runId": EXPECTED_RUN,
        "inputSha256": EXPECTED_SHA,
        "sourceNotebookSha256": EXPECTED_NOTEBOOK_SHA,
        "validation": {"fullCorpusAcceptance": "PASS"},
    }
    value.update(overrides)
    return value


def test_validator_complete_matching_pass_evidence_promotes() -> None:
    result = evaluate_validator_artifact(
        artifact(), expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result == {
        "gateStatus": "PASS",
        "crawlReleaseReady": True,
        "reason": "VALIDATOR_EVIDENCE_PASS",
    }


def test_validator_nonzero_exit_fails_closed() -> None:
    result = evaluate_validator_artifact(
        artifact(processExitCode=17), expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result["gateStatus"] == "FAIL"
    assert result["crawlReleaseReady"] is False


def test_validator_non_pass_status_fails_closed() -> None:
    result = evaluate_validator_artifact(
        artifact(status="FAIL"), expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result["gateStatus"] == "FAIL"
    assert result["crawlReleaseReady"] is False


def test_validator_missing_artifact_is_not_evaluated() -> None:
    result = evaluate_validator_artifact(
        None, expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result["gateStatus"] == "NOT_EVALUATED"
    assert result["crawlReleaseReady"] is False


def test_validator_stale_run_id_fails_closed() -> None:
    result = evaluate_validator_artifact(
        artifact(runId="STALE"), expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result["reason"] == "VALIDATOR_RUN_ID_MISMATCH"
    assert result["crawlReleaseReady"] is False


def test_validator_input_sha_mismatch_fails_closed() -> None:
    result = evaluate_validator_artifact(
        artifact(inputSha256="b" * 64), expected_run_id=EXPECTED_RUN, expected_input_sha256=EXPECTED_SHA,
    )
    assert result["reason"] == "VALIDATOR_INPUT_SHA256_MISMATCH"
    assert result["crawlReleaseReady"] is False


def test_validator_full_corpus_must_also_pass() -> None:
    result = evaluate_validator_artifact(
        artifact(validation={"fullCorpusAcceptance": "FAIL"}),
        expected_run_id=EXPECTED_RUN,
        expected_input_sha256=EXPECTED_SHA,
    )
    assert result["reason"] == "FULL_CORPUS_ACCEPTANCE_NOT_PASS"
    assert result["crawlReleaseReady"] is False


def test_validator_notebook_source_sha_mismatch_fails_closed() -> None:
    result = evaluate_validator_artifact(
        artifact(sourceNotebookSha256="d" * 64),
        expected_run_id=EXPECTED_RUN,
        expected_input_sha256=EXPECTED_SHA,
        expected_source_notebook_sha256=EXPECTED_NOTEBOOK_SHA,
    )
    assert result["reason"] == "VALIDATOR_SOURCE_NOTEBOOK_SHA256_MISMATCH"
    assert result["crawlReleaseReady"] is False
