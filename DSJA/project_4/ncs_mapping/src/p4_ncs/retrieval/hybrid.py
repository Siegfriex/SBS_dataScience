"""Dependency-free sparse/BM25 candidate union for the v4 offline baseline."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣+#/.]+")
OUT_OF_SCOPE_CODE = "OUT_OF_SCOPE"


def _words(text: str) -> list[str]:
    return [token for token in _NON_WORD.sub(" ", str(text).lower()).split() if token]


def char_ngrams(text: str, minimum: int = 3, maximum: int = 5) -> Counter[str]:
    compact = "".join(_words(text))
    return Counter(
        compact[start:start + size]
        for size in range(minimum, maximum + 1)
        for start in range(max(0, len(compact) - size + 1))
    )


def word_ngrams(text: str, minimum: int = 1, maximum: int = 2) -> Counter[str]:
    words = _words(text)
    return Counter(
        " ".join(words[start:start + size])
        for size in range(minimum, maximum + 1)
        for start in range(max(0, len(words) - size + 1))
    )


@dataclass(frozen=True)
class RetrievalDocument:
    code: str
    name: str
    definition: str | None = None
    subcategory_code: str | None = None
    performance_criteria: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.name, self.definition or "") if part).strip()


@dataclass
class CandidateScore:
    code: str
    name: str
    definition: str | None
    subcategory_code: str | None
    performance_criteria: tuple[str, ...]
    channel_scores: dict[str, float] = field(default_factory=dict)
    combined_score: float = 0.0
    match_bases: set[str] = field(default_factory=set)


class TfidfIndex:
    def __init__(self, documents: list[RetrievalDocument], feature_fn):
        self.documents = documents
        self.feature_fn = feature_fn
        self.features = [feature_fn(document.text) for document in documents]
        df: Counter[str] = Counter()
        for features in self.features:
            df.update(features.keys())
        count = max(1, len(documents))
        self.idf = {term: math.log((count + 1) / (frequency + 1)) + 1 for term, frequency in df.items()}
        self.norms = [self._norm(features) for features in self.features]

    def _norm(self, features: Counter[str]) -> float:
        return math.sqrt(sum((frequency * self.idf.get(term, 0.0)) ** 2 for term, frequency in features.items()))

    def search(self, query: str, top_k: int) -> list[tuple[RetrievalDocument, float]]:
        query_features = self.feature_fn(query)
        query_norm = self._norm(query_features)
        if query_norm == 0:
            return []
        scored: list[tuple[RetrievalDocument, float]] = []
        for document, features, norm in zip(self.documents, self.features, self.norms):
            denominator = query_norm * norm
            if denominator == 0:
                continue
            dot = sum(
                frequency * self.idf.get(term, 0.0)
                * features.get(term, 0) * self.idf.get(term, 0.0)
                for term, frequency in query_features.items()
            )
            score = dot / denominator
            if score > 0:
                scored.append((document, float(score)))
        return sorted(scored, key=lambda item: (-item[1], item[0].code))[:top_k]


class BM25Index:
    def __init__(self, documents: list[RetrievalDocument], k1: float = 1.5, b: float = 0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.tokens = [_words(document.text) for document in documents]
        self.lengths = [len(tokens) for tokens in self.tokens]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        df: Counter[str] = Counter()
        for tokens in self.tokens:
            df.update(set(tokens))
        count = max(1, len(documents))
        self.idf = {term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5)) for term, frequency in df.items()}

    def search(self, query: str, top_k: int) -> list[tuple[RetrievalDocument, float]]:
        query_terms = set(_words(query))
        scored: list[tuple[RetrievalDocument, float]] = []
        for document, tokens, length in zip(self.documents, self.tokens, self.lengths):
            frequencies = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / max(1.0, self.average_length))
                score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator
            if score > 0:
                scored.append((document, float(score)))
        return sorted(scored, key=lambda item: (-item[1], item[0].code))[:top_k]


def _normalized(scores: list[tuple[RetrievalDocument, float]]) -> dict[str, float]:
    if not scores:
        return {}
    maximum = max(score for _, score in scores)
    return {document.code: score / maximum if maximum else 0.0 for document, score in scores}


class HybridRetriever:
    def __init__(self, documents: Iterable[RetrievalDocument]):
        rows = sorted(documents, key=lambda document: document.code)
        if not rows or len({row.code for row in rows}) != len(rows):
            raise ValueError("retrieval corpus must contain unique non-empty codes")
        self.documents = rows
        self.by_code = {row.code: row for row in rows}
        self.char_index = TfidfIndex(rows, char_ngrams)
        self.word_index = TfidfIndex(rows, word_ngrams)
        self.bm25_index = BM25Index(rows)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
        aliases: Mapping[str, str] | None = None,
        hierarchy_backoff: Iterable[str] = (),
    ) -> list[CandidateScore]:
        if not str(query).strip():
            raise ValueError("query must be non-empty")
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be within 1..10")
        channel_results = {
            "charTfidf": self.char_index.search(query, top_k),
            "wordTfidf": self.word_index.search(query, top_k),
            "bm25": self.bm25_index.search(query, top_k),
        }
        merged: dict[str, CandidateScore] = {}

        def ensure(code: str) -> CandidateScore | None:
            document = self.by_code.get(code)
            if document is None:
                return None
            return merged.setdefault(code, CandidateScore(
                code=code, name=document.name, definition=document.definition,
                subcategory_code=document.subcategory_code,
                performance_criteria=document.performance_criteria,
            ))

        for channel, results in channel_results.items():
            normalized = _normalized(results)
            for document, _ in results:
                candidate = ensure(document.code)
                assert candidate is not None
                candidate.channel_scores[channel] = normalized[document.code]
                candidate.match_bases.add(channel)
        lowered = query.lower()
        for alias, code in sorted((aliases or {}).items()):
            if alias.lower() in lowered:
                candidate = ensure(code)
                if candidate is not None:
                    candidate.channel_scores["aliasExact"] = 1.0
                    candidate.match_bases.add("aliasExact")
        for code in hierarchy_backoff:
            candidate = ensure(str(code))
            if candidate is not None:
                candidate.channel_scores["hierarchyBackoff"] = 0.25
                candidate.match_bases.add("hierarchyBackoff")
        for candidate in merged.values():
            candidate.combined_score = round(sum(candidate.channel_scores.values()), 10)
        ranked = sorted(merged.values(), key=lambda row: (-row.combined_score, row.code))[:max(0, top_k - 1)]
        ranked.append(CandidateScore(
            code=OUT_OF_SCOPE_CODE, name="Out of NCS candidate scope", definition=None,
            subcategory_code=None, performance_criteria=(), channel_scores={"sentinel": 0.0},
            combined_score=0.0, match_bases={"sentinel"},
        ))
        return ranked[:top_k]
