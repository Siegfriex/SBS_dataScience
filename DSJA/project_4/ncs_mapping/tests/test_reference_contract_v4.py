import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from p4_ncs.reference.contracts import (
    ReferenceAgentOutput, ReferenceRuntime, build_reference_label,
    needs_adjudication, transition_reference_state, validate_agent_output,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((PROJECT_ROOT / "shared/contracts/semantic_ncs_reference/v4.0/schemas/reference_label.schema.json").read_text())
SHA = "a" * 64


@pytest.fixture
def output():
    return ReferenceAgentOutput(
        agent_role="LABELER", decision="SELECT_CANDIDATE", selected_codes=("U1",),
        evidence_spans=({"sourceBlockId": "B1", "startChar": 0, "endChar": 5},),
        rationale="업무 근거와 후보 정의가 대응함", source_sha256=SHA,
        candidate_packet_sha256="b" * 64, candidate_corpus_sha256="c" * 64,
        model_artifact_sha256="d" * 64, prompt_sha256="e" * 64,
        output_schema_sha256="f" * 64, parameter_sha256="1" * 64,
    )


def test_valid_labeler_output_and_llm_reference_schema(output):
    validate_agent_output(output, candidate_codes=["U1", "U2", "OUT_OF_SCOPE"], source_blocks={"B1": "업무근거 텍스트"})
    record = build_reference_label(
        annotation_task_id="TASK_1", authority="LLM_REFERENCE", tier="A",
        status="LLM_REFERENCE_FROZEN", output=output,
        labeler_run_id="LABELER_1", critic_run_id="CRITIC_1", confidence=0.9,
    )
    Draft202012Validator(SCHEMA).validate(record)
    assert record["referenceAuthority"] == "LLM_REFERENCE"


def test_unsupported_code_fails_closed(output):
    with pytest.raises(ValueError, match="unsupported canonical code"):
        validate_agent_output(output, candidate_codes=["U2"], source_blocks={"B1": "업무근거 텍스트"})


def test_selected_code_requires_evidence(output):
    with pytest.raises(ValueError, match="requires evidence"):
        validate_agent_output(replace(output, evidence_spans=()), candidate_codes=["U1"], source_blocks={"B1": "업무근거"})


def test_evidence_span_must_be_inside_source(output):
    bad = replace(output, evidence_spans=({"sourceBlockId": "B1", "startChar": 0, "endChar": 999},))
    with pytest.raises(ValueError, match="outside source"):
        validate_agent_output(bad, candidate_codes=["U1"], source_blocks={"B1": "짧음"})


def test_provenance_sha_failure_is_fatal(output):
    with pytest.raises(ValueError, match="provenance SHA"):
        validate_agent_output(replace(output, prompt_sha256="bad"), candidate_codes=["U1"], source_blocks={"B1": "업무근거 텍스트"})


def test_out_of_scope_is_decision_not_selected_code(output):
    invalid = replace(output, decision="OUT_OF_SCOPE", selected_codes=("OUT_OF_SCOPE",), evidence_spans=())
    with pytest.raises(ValueError, match="cannot be selected"):
        validate_agent_output(invalid, candidate_codes=["OUT_OF_SCOPE"], source_blocks={"B1": "업무근거"})


def test_reference_state_machine_accepts_only_declared_transitions():
    assert transition_reference_state("UNLABELED", "SILVER_PROPOSED") == "SILVER_PROPOSED"
    assert transition_reference_state("LLM_CODED", "CRITIC_EVALUATED") == "CRITIC_EVALUATED"
    with pytest.raises(ValueError, match="invalid reference transition"):
        transition_reference_state("UNLABELED", "LLM_REFERENCE_FROZEN")


def test_adjudicator_is_conditional_on_disagreement_or_risk(output):
    critic_same = replace(output, agent_role="CRITIC")
    critic_other = replace(output, agent_role="CRITIC", decision="ABSTAIN", selected_codes=(), evidence_spans=())
    assert needs_adjudication(output, critic_same, p_top1=0.9, margin=0.4) is False
    assert needs_adjudication(output, critic_other, p_top1=0.9, margin=0.4) is True
    assert needs_adjudication(output, critic_same, p_top1=0.6, margin=0.4) is True
    assert needs_adjudication(output, critic_same, p_top1=0.9, margin=0.05) is True


def test_human_and_llm_authority_cannot_be_conflated(output):
    with pytest.raises(ValueError, match="does not match"):
        build_reference_label(
            annotation_task_id="T", authority="LLM_REFERENCE", tier="A",
            status="HUMAN_GOLD_FROZEN", output=output,
        )
    with pytest.raises(ValueError, match="humanCodingBundleId"):
        build_reference_label(
            annotation_task_id="T", authority="HUMAN_GOLD", tier="HUMAN",
            status="HUMAN_GOLD_FROZEN", output=output,
        )


def test_reference_runtime_never_calls_model_without_configuration():
    result = ReferenceRuntime().evaluate({"task": "synthetic"})
    assert result == {
        "status": "NOT_EVALUATED", "reason": "MODEL_RUNTIME_NOT_CONFIGURED",
        "modelCallCount": 0, "promotionAllowed": False,
    }
