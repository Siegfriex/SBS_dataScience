"""Explicit dense-retrieval availability boundary."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DenseRetrievalResult:
    status: str
    reason: str
    model_id: str | None
    model_revision: str | None
    candidates: tuple[tuple[str, float], ...]


class DenseRetrievalAdapter:
    def __init__(self, *, model_id: str | None = None, model_revision: str | None = None):
        self.model_id = model_id
        self.model_revision = model_revision

    def retrieve(self, _query: str, *, top_k: int = 10) -> DenseRetrievalResult:
        if not self.model_id or not self.model_revision:
            return DenseRetrievalResult(
                status="NOT_EVALUATED",
                reason="DENSE_MODEL_OR_REVISION_UNAVAILABLE",
                model_id=self.model_id,
                model_revision=self.model_revision,
                candidates=(),
            )
        raise NotImplementedError("dense model execution requires a pinned audited adapter")
