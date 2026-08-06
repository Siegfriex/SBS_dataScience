"""Structural gold-evaluation contract for Agent 4.

M1 has no adjudicated gold rows. The module therefore produces an explicit
``NOT_EVALUATED`` result instead of manufacturing a zero precision or coverage
value. A future production evaluator can extend this interface once controlled
gold data is approved.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

GOLD_COLUMNS = [
    "goldSampleId", "trackId", "sectionId", "evidenceText",
    "candidateNcsUnitCodes", "goldNcsUnitCode", "goldNcsLevel",
    "mappableFlag", "annotator1", "annotator2", "adjudicatedLabel",
    "reviewNote",
]


@dataclass(frozen=True)
class GoldEvaluationResult:
    goldRows: int
    adjudicatedRows: int
    precision: None
    finalCoverage: None
    lowConfidenceRate: None
    gateStatus: str
    reason: str
    goldValidatedFlag: bool
    empiricalAnalysisAllowed: bool
    promotionAllowed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_gold_structure(path: str | Path | None = None) -> pd.DataFrame:
    """Load a gold CSV or return the canonical zero-row structure."""
    if path is None or not Path(path).exists():
        return pd.DataFrame(columns=GOLD_COLUMNS)
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = set(GOLD_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"gold input missing columns: {', '.join(sorted(missing))}")
    return frame[GOLD_COLUMNS].copy()


def evaluate_gold_mapping(gold: pd.DataFrame) -> GoldEvaluationResult:
    """Return a non-evaluated M1 result; never infer metrics from empty gold."""
    missing = set(GOLD_COLUMNS).difference(gold.columns)
    if missing:
        raise ValueError(f"gold input missing columns: {', '.join(sorted(missing))}")
    adjudicated = int(gold["adjudicatedLabel"].notna().sum()) if len(gold) else 0
    if len(gold) != 0:
        raise ValueError("M1 observed-development cannot evaluate non-empty gold input")
    return GoldEvaluationResult(
        goldRows=0,
        adjudicatedRows=adjudicated,
        precision=None,
        finalCoverage=None,
        lowConfidenceRate=None,
        gateStatus="NOT_EVALUATED",
        reason="EMPTY_GOLD_INPUT",
        goldValidatedFlag=False,
        empiricalAnalysisAllowed=False,
        promotionAllowed=False,
    )
