"""Dependency-free TF-IDF character/token index for the M1 lexical baseline."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣+#/.]+")


def _features(text: str) -> Counter[str]:
    normalized = _NON_WORD.sub(" ", str(text).lower()).strip()
    compact = normalized.replace(" ", "")
    tokens = [f"tok:{token}" for token in normalized.split() if len(token) > 1]
    bigrams = [f"bi:{compact[i:i + 2]}" for i in range(max(0, len(compact) - 1))]
    trigrams = [f"tri:{compact[i:i + 3]}" for i in range(max(0, len(compact) - 2))]
    return Counter(tokens + bigrams + trigrams)


@dataclass(frozen=True)
class LexicalHit:
    ncsSubCode: str
    ncsSubName: str
    matchedNcsUnitCode: str
    matchedNcsUnitName: str
    lexicalScore: float


class LexicalIndex:
    """A stable in-memory index over NCS units in reviewed subcategories."""

    def __init__(self, documents: pd.DataFrame):
        required = {"ncsSubCode", "ncsSubName", "ncsUnitCode", "ncsUnitName"}
        missing = required.difference(documents.columns)
        if missing:
            raise ValueError(f"lexical documents missing columns: {', '.join(sorted(missing))}")
        docs = documents.loc[:, sorted(required)].copy()
        docs = docs.sort_values(["ncsSubCode", "ncsUnitCode"], kind="stable").reset_index(drop=True)
        self.documents = docs
        self._features = [_features(f"{row.ncsSubName} {row.ncsUnitName}") for row in docs.itertuples()]
        document_frequency: Counter[str] = Counter()
        for features in self._features:
            document_frequency.update(features.keys())
        count = max(1, len(docs))
        self._idf = {term: math.log((count + 1) / (freq + 1)) + 1 for term, freq in document_frequency.items()}
        self._norms = [self._norm(features) for features in self._features]

    def _norm(self, features: Counter[str]) -> float:
        return math.sqrt(sum((frequency * self._idf.get(term, 0.0)) ** 2 for term, frequency in features.items()))

    @classmethod
    def build(cls, ncs_units: pd.DataFrame, codeset: pd.DataFrame) -> "LexicalIndex":
        included = codeset.loc[codeset["included"].astype(bool), ["ncsSubCode", "ncsSubName"]].copy()
        units = ncs_units.copy()
        units["ncsSubCode"] = (
            units["majorCode"].astype("string")
            + units["middleCode"].astype("string")
            + units["minorCode"].astype("string")
            + units["subCode"].astype("string")
        )
        documents = units.merge(included, on="ncsSubCode", how="inner", validate="many_to_one")
        return cls(documents[["ncsSubCode", "ncsSubName", "ncsUnitCode", "ncsUnitName"]])

    def search(
        self,
        query: str,
        top_k: int = 5,
        allowed_subcodes: Iterable[str] | None = None,
        minimum_score: float = 0.035,
    ) -> list[LexicalHit]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_features = _features(query)
        query_norm = self._norm(query_features)
        if query_norm == 0:
            return []
        allowed = set(allowed_subcodes) if allowed_subcodes is not None else None
        best_by_subcode: dict[str, LexicalHit] = {}
        for position, row in enumerate(self.documents.itertuples(index=False)):
            if allowed is not None and row.ncsSubCode not in allowed:
                continue
            dot = sum(
                frequency * self._idf.get(term, 0.0)
                * self._features[position].get(term, 0)
                * self._idf.get(term, 0.0)
                for term, frequency in query_features.items()
            )
            denominator = query_norm * self._norms[position]
            score = dot / denominator if denominator else 0.0
            if score < minimum_score:
                continue
            hit = LexicalHit(
                ncsSubCode=row.ncsSubCode,
                ncsSubName=row.ncsSubName,
                matchedNcsUnitCode=row.ncsUnitCode,
                matchedNcsUnitName=row.ncsUnitName,
                lexicalScore=round(float(score), 8),
            )
            previous = best_by_subcode.get(row.ncsSubCode)
            if previous is None or (hit.lexicalScore, hit.matchedNcsUnitCode) > (
                previous.lexicalScore,
                previous.matchedNcsUnitCode,
            ):
                best_by_subcode[row.ncsSubCode] = hit
        return sorted(
            best_by_subcode.values(),
            key=lambda hit: (-hit.lexicalScore, hit.ncsSubCode, hit.matchedNcsUnitCode),
        )[:top_k]


def restrict_units_to_subcategories(ncs_units: pd.DataFrame, allowed_subcodes: Iterable[str]) -> pd.DataFrame:
    """Return only units whose encoded 8-digit prefix is explicitly allowed."""
    allowed = set(allowed_subcodes)
    encoded = ncs_units["ncsUnitCode"].astype("string").str.slice(0, 8)
    restricted = ncs_units.loc[encoded.isin(allowed)].copy()
    if not restricted.empty and not restricted["ncsUnitCode"].str.slice(0, 8).isin(allowed).all():
        raise AssertionError("same-subcategory restriction failed")
    return restricted
