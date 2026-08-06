"""Candidate NCS subCode retrieval for a piece of duty/evidence text.

Pipeline per spec: alias/dictionary match first, then lexical retrieval over
the included codeset, then (future) dense rerank, capped at top k=5. Dense
rerank has no implementation yet -- it needs an embeddings model and real
duty evidence text to validate against, neither of which exists before
Agent 2 input arrives, so `dense_rerank` is a pass-through stub, not a fake
model.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TOP_K = 5


@dataclass(frozen=True)
class Candidate:
    ncsSubCode: str
    ncsSubName: str
    score: float
    mappingBasis: str


def _tokenize(text: str) -> set[str]:
    # NCS sub-names and job-posting Korean text aren't reliably whitespace-
    # tokenizable (compounds, no spaces between morphemes), so this also
    # scores raw substring containment, not just token overlap.
    return set(text.replace("/", " ").split())


def alias_lookup(evidence_text: str, alias_df: pd.DataFrame) -> list[Candidate]:
    hits = []
    for _, row in alias_df.iterrows():
        if row["alias"] in evidence_text:
            hits.append(Candidate(row["ncsSubCode"], row["alias"], score=1.0, mappingBasis="dictionaryRule"))
    return hits


def lexical_retrieve(evidence_text: str, codeset_df: pd.DataFrame, top_k: int = TOP_K) -> list[Candidate]:
    included = codeset_df[codeset_df["included"]]
    scored = []
    for _, row in included.iterrows():
        name = row["ncsSubName"]
        if name in evidence_text or evidence_text in name:
            overlap = min(len(name), len(evidence_text)) / max(len(name), len(evidence_text))
            scored.append(Candidate(row["ncsSubCode"], name, score=overlap, mappingBasis="semanticMatch"))
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def dense_rerank(candidates: list[Candidate]) -> list[Candidate]:
    """Stub: no embeddings model wired up yet. Returns input order unchanged.

    Do not call this a real rerank in reports -- it is an identity pass-
    through until a dense retrieval component is built against real duty
    evidence text.
    """
    return candidates


def retrieve_candidates(evidence_text: str, alias_df: pd.DataFrame, codeset_df: pd.DataFrame, top_k: int = TOP_K) -> list[Candidate]:
    alias_hits = alias_lookup(evidence_text, alias_df)
    if alias_hits:
        return alias_hits[:top_k]
    lexical_hits = lexical_retrieve(evidence_text, codeset_df, top_k=top_k)
    return dense_rerank(lexical_hits)
