from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from p4.common.keys import make_match_id, normalize


MAPPING_PRIORITY = {
    "ncsUnitDirect": 0,
    "ncsPerformanceCriteria": 1,
    "ncsLearningModule": 2,
    "dictionaryRule": 3,
    "semanticMatch": 4,
    "unmapped": 5,
}


@dataclass(frozen=True)
class NcsMatch:
    matchId: str
    sectionId: str
    ncsUnitCode: str
    evidenceText: str
    mappingBasis: str
    matchScore: float
    matchRank: int
    mappingVersion: str
    selectedFlag: bool


def validate_match(match: NcsMatch) -> None:
    if match.mappingBasis not in MAPPING_PRIORITY:
        raise ValueError(f"unknown mapping basis: {match.mappingBasis}")
    if not match.evidenceText.strip():
        raise ValueError("evidenceText is required")
    if not match.ncsUnitCode.strip():
        raise ValueError("ncsUnitCode is required")
    if not 0 <= match.matchScore <= 1:
        raise ValueError("matchScore must be in [0, 1]")
    if match.matchRank < 1:
        raise ValueError("matchRank must be positive")


def rank_candidates(
    section_id: str,
    candidates: Iterable[dict[str, object]],
    mapping_version: str,
) -> list[dict[str, object]]:
    prepared = []
    for candidate in candidates:
        basis = str(candidate.get("mappingBasis") or "")
        if basis not in MAPPING_PRIORITY or basis == "unmapped":
            raise ValueError(f"invalid candidate mappingBasis: {basis}")
        evidence = str(candidate.get("evidenceText") or "").strip()
        code = str(candidate.get("ncsUnitCode") or "").strip()
        score = float(candidate.get("matchScore", 0.0))
        if not evidence or not code:
            raise ValueError("candidate requires evidenceText and ncsUnitCode")
        if candidate.get("toolNameOnly"):
            raise ValueError("tool-name-only NCS level assignment is prohibited")
        prepared.append((MAPPING_PRIORITY[basis], -score, code, evidence, basis, score))
    prepared.sort()
    results: list[dict[str, object]] = []
    for index, (_, _, code, evidence, basis, score) in enumerate(prepared, start=1):
        match = NcsMatch(
            matchId=make_match_id(section_id, code, mapping_version),
            sectionId=section_id,
            ncsUnitCode=code,
            evidenceText=evidence,
            mappingBasis=basis,
            matchScore=score,
            matchRank=index,
            mappingVersion=mapping_version,
            selectedFlag=index == 1,
        )
        validate_match(match)
        results.append(asdict(match))
    return results


def dictionary_candidates(
    section_id: str,
    section_text: str,
    rules: Iterable[dict[str, object]],
    mapping_version: str,
) -> list[dict[str, object]]:
    text = normalize(section_text)
    candidates: list[dict[str, object]] = []
    for rule in rules:
        phrases = [normalize(value) for value in rule.get("phrases", [])]
        matched = [phrase for phrase in phrases if phrase and phrase in text]
        if matched:
            candidates.append(
                {
                    "ncsUnitCode": rule["ncsUnitCode"],
                    "evidenceText": " | ".join(matched),
                    "mappingBasis": "dictionaryRule",
                    "matchScore": float(rule.get("matchScore", 0.7)),
                }
            )
    return rank_candidates(section_id, candidates, mapping_version) if candidates else []

