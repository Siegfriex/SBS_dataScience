"""Bounded candidate packet construction with explicit truncation metadata."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from p4_ncs.api.redaction import canonical_json_sha256
from p4_ncs.retrieval.hybrid import CandidateScore

TRUNCATION_POLICY_VERSION = "candidate-packet-bounds-v4.0"


@dataclass(frozen=True)
class CandidatePacket:
    contract_record: dict
    detail: dict


def _bounded_text(text: str, *, max_chars: int, max_tokens: int) -> tuple[str, dict]:
    original = str(text).strip()
    if not original:
        raise ValueError("candidate packet target text must be non-empty")
    tokens = original.split()
    token_bounded = " ".join(tokens[:max_tokens])
    bounded = token_bounded[:max_chars].strip()
    if not bounded:
        raise ValueError("candidate packet target text became empty")
    return bounded, {
        "truncatedFlag": bounded != original,
        "originalCharCount": len(original),
        "retainedCharCount": len(bounded),
        "removedCharCount": len(original) - len(bounded),
        "originalTokenCount": len(tokens),
        "retainedTokenCount": len(bounded.split()),
        "removedTokenCount": max(0, len(tokens) - len(bounded.split())),
    }


def build_candidate_packet(
    *,
    annotation_task_id: str,
    target_text: str,
    source_role: str,
    candidates: Iterable[CandidateScore],
    adjacent_context: Iterable[str] = (),
    retrieval_top_k: int = 10,
    llm_visible_k: int = 5,
) -> CandidatePacket:
    if source_role not in {"DUTY", "REQUIRED", "PREFERRED", "OTHER"}:
        raise ValueError("invalid candidate packet sourceRole")
    if not 1 <= retrieval_top_k <= 10 or not 1 <= llm_visible_k <= 5:
        raise ValueError("candidate packet top-k limits violated")
    target, target_meta = _bounded_text(target_text, max_chars=1200, max_tokens=600)
    context_rows = list(adjacent_context)[:2]
    context_joined = "\n".join(map(str, context_rows))
    context, context_meta = ("", {
        "truncatedFlag": False, "originalCharCount": 0, "retainedCharCount": 0,
        "removedCharCount": 0, "originalTokenCount": 0, "retainedTokenCount": 0,
        "removedTokenCount": 0,
    }) if not context_joined.strip() else _bounded_text(context_joined, max_chars=800, max_tokens=600)
    candidate_rows = list(candidates)[:retrieval_top_k]
    codes = [row.code for row in candidate_rows]
    if not candidate_rows or len(codes) != len(set(codes)):
        raise ValueError("candidate packet requires unique candidates")
    details = []
    for row in candidate_rows:
        definition = (row.definition or "")[:350]
        details.append({
            "code": row.code,
            "name": row.name,
            "definition": definition or None,
            "performanceCriteria": list(row.performance_criteria[:2]),
            "subcategoryCode": row.subcategory_code,
            "channelScores": dict(sorted(row.channel_scores.items())),
            "combinedScore": row.combined_score,
            "matchBases": sorted(row.match_bases),
        })
    target_sha = canonical_json_sha256(target)
    body = {
        "annotationTaskId": annotation_task_id,
        "sourceRole": source_role,
        "targetText": target,
        "adjacentContext": context,
        "targetTruncation": target_meta,
        "contextTruncation": context_meta,
        "retrievalTopK": retrieval_top_k,
        "llmVisibleK": min(llm_visible_k, len(details)),
        "candidates": details,
        "truncationPolicyVersion": TRUNCATION_POLICY_VERSION,
    }
    packet_sha = canonical_json_sha256(body)
    contract = {
        "candidatePacketId": f"CPK_{packet_sha[:20]}",
        "annotationTaskId": annotation_task_id,
        "targetTextSha256": target_sha,
        "targetCharCount": len(target),
        "targetTokenCount": len(target.split()),
        "sourceRole": source_role,
        "contextBlockCount": len(context_rows),
        "retrievalTopK": retrieval_top_k,
        "llmVisibleK": min(llm_visible_k, len(details)),
        "truncationPolicyVersion": TRUNCATION_POLICY_VERSION,
        "candidateCodesJson": codes,
        "decision": None,
        "packetSha256": packet_sha,
    }
    return CandidatePacket(contract_record=contract, detail=body)
