"""Fail-closed Labeler/Critic/Adjudicator contracts; no model execution."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from p4_ncs.api.redaction import canonical_json_sha256

_SHA = re.compile(r"^[0-9a-f]{64}$")
AGENT_ROLES = {"LABELER", "CRITIC", "ADJUDICATOR"}
DECISIONS = {"SELECT_CANDIDATE", "MULTI_LABEL", "NONE_OF_CANDIDATES", "OUT_OF_SCOPE", "ABSTAIN"}
AUTHORITIES = {"LLM_REFERENCE", "HUMAN_GOLD", "HYBRID_GOLD"}

_TRANSITIONS = {
    "UNLABELED": {"SILVER_PROPOSED"},
    "SILVER_PROPOSED": {"LLM_CODED", "HUMAN_CODED", "ABSTAINED", "OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE"},
    "LLM_CODED": {"CRITIC_EVALUATED", "INVALIDATED"},
    "HUMAN_CODED": {"CRITIC_EVALUATED", "ADJUDICATED", "INVALIDATED"},
    "CRITIC_EVALUATED": {"ADJUDICATION_REQUIRED", "LLM_REFERENCE_FROZEN", "HUMAN_GOLD_FROZEN", "INVALIDATED"},
    "ADJUDICATION_REQUIRED": {"ADJUDICATED", "ABSTAINED", "INVALIDATED"},
    "ADJUDICATED": {"LLM_REFERENCE_FROZEN", "HUMAN_GOLD_FROZEN", "HYBRID_GOLD_FROZEN", "ABSTAINED", "INVALIDATED"},
    "LLM_REFERENCE_FROZEN": {"SUPERSEDED"},
    "HUMAN_GOLD_FROZEN": {"SUPERSEDED"},
    "HYBRID_GOLD_FROZEN": {"SUPERSEDED"},
    "ABSTAINED": {"SUPERSEDED"},
    "OUT_OF_SCOPE": {"SUPERSEDED"},
    "INSUFFICIENT_EVIDENCE": {"SUPERSEDED"},
    "INVALIDATED": {"SUPERSEDED"},
    "SUPERSEDED": set(),
}


@dataclass(frozen=True)
class ReferenceAgentOutput:
    agent_role: str
    decision: str
    selected_codes: tuple[str, ...]
    evidence_spans: tuple[dict[str, Any], ...]
    rationale: str
    source_sha256: str
    candidate_packet_sha256: str
    candidate_corpus_sha256: str
    model_artifact_sha256: str
    prompt_sha256: str
    output_schema_sha256: str
    parameter_sha256: str


def _valid_sha(value: str) -> bool:
    return bool(_SHA.fullmatch(str(value)))


def validate_agent_output(
    output: ReferenceAgentOutput,
    *,
    candidate_codes: Sequence[str],
    source_blocks: Mapping[str, str],
) -> None:
    if output.agent_role not in AGENT_ROLES:
        raise ValueError("invalid reference agent role")
    if output.decision not in DECISIONS:
        raise ValueError("invalid reference decision")
    if len(output.selected_codes) != len(set(output.selected_codes)):
        raise ValueError("duplicate selected canonical code")
    unsupported = set(output.selected_codes).difference(candidate_codes)
    if unsupported:
        raise ValueError(f"unsupported canonical code: {sorted(unsupported)}")
    if "OUT_OF_SCOPE" in output.selected_codes:
        raise ValueError("OUT_OF_SCOPE sentinel cannot be selected as a canonical code")
    if output.decision == "SELECT_CANDIDATE" and len(output.selected_codes) != 1:
        raise ValueError("SELECT_CANDIDATE requires exactly one selected code")
    if output.decision == "MULTI_LABEL" and len(output.selected_codes) < 2:
        raise ValueError("MULTI_LABEL requires at least two selected codes")
    if output.decision in {"NONE_OF_CANDIDATES", "OUT_OF_SCOPE", "ABSTAIN"} and output.selected_codes:
        raise ValueError(f"{output.decision} cannot include selected codes")
    if output.selected_codes and not output.evidence_spans:
        raise ValueError("selected mapping requires evidence spans")
    for span in output.evidence_spans:
        if set(span) != {"sourceBlockId", "startChar", "endChar"}:
            raise ValueError("invalid evidence span fields")
        block_id = str(span["sourceBlockId"])
        if block_id not in source_blocks:
            raise ValueError("evidence span references unknown source block")
        start, end = int(span["startChar"]), int(span["endChar"])
        if start < 0 or end <= start or end > len(source_blocks[block_id]):
            raise ValueError("evidence span is outside source text")
    provenance = [
        output.source_sha256, output.candidate_packet_sha256, output.candidate_corpus_sha256,
        output.model_artifact_sha256, output.prompt_sha256, output.output_schema_sha256,
        output.parameter_sha256,
    ]
    if not all(_valid_sha(value) for value in provenance):
        raise ValueError("reference output provenance SHA is invalid")


def transition_reference_state(current: str, target: str) -> str:
    if current not in _TRANSITIONS or target not in _TRANSITIONS:
        raise ValueError("unknown reference state")
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"invalid reference transition: {current}->{target}")
    return target


def needs_adjudication(
    labeler: ReferenceAgentOutput,
    critic: ReferenceAgentOutput,
    *,
    p_top1: float | None = None,
    margin: float | None = None,
    review_threshold: float = 0.7,
    margin_threshold: float = 0.15,
) -> bool:
    if labeler.decision != critic.decision or labeler.selected_codes != critic.selected_codes:
        return True
    if p_top1 is not None and p_top1 < review_threshold:
        return True
    if margin is not None and margin < margin_threshold:
        return True
    return False


def build_reference_label(
    *,
    annotation_task_id: str,
    authority: str,
    tier: str,
    status: str,
    output: ReferenceAgentOutput,
    labeler_run_id: str | None = None,
    critic_run_id: str | None = None,
    adjudicator_run_id: str | None = None,
    human_coding_bundle_id: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    if authority not in AUTHORITIES:
        raise ValueError("invalid reference authority")
    frozen_by_authority = {
        "LLM_REFERENCE": "LLM_REFERENCE_FROZEN",
        "HUMAN_GOLD": "HUMAN_GOLD_FROZEN",
        "HYBRID_GOLD": "HYBRID_GOLD_FROZEN",
    }
    if status.endswith("_FROZEN") and status != frozen_by_authority[authority]:
        raise ValueError("reference authority does not match frozen status")
    if authority == "HUMAN_GOLD" and not human_coding_bundle_id:
        raise ValueError("HUMAN_GOLD requires humanCodingBundleId")
    label_json = {"decision": output.decision, "selectedCodes": list(output.selected_codes), "rationale": output.rationale}
    digest = canonical_json_sha256({"task": annotation_task_id, "authority": authority, "label": label_json})
    return {
        "referenceLabelId": f"RFL_{digest[:20]}",
        "annotationTaskId": annotation_task_id,
        "referenceAuthority": authority,
        "referenceLabelJson": label_json,
        "referenceTier": tier,
        "referenceConfidence": confidence,
        "referenceStatus": status,
        "labelerRunId": labeler_run_id,
        "criticRunId": critic_run_id,
        "adjudicatorRunId": adjudicator_run_id,
        "humanCodingBundleId": human_coding_bundle_id,
        "evidenceSpansJson": list(output.evidence_spans),
        "sourceSha256": output.source_sha256,
        "candidatePacketSha256": output.candidate_packet_sha256,
        "candidateCorpusSha256": output.candidate_corpus_sha256,
        "promptBundleSha256": output.prompt_sha256,
        "frozenAt": None,
        "supersededBy": None,
    }


class ReferenceRuntime:
    """Offline contract runtime. Model invocation is deliberately absent."""

    def evaluate(self, _task: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": "NOT_EVALUATED",
            "reason": "MODEL_RUNTIME_NOT_CONFIGURED",
            "modelCallCount": 0,
            "promotionAllowed": False,
        }
