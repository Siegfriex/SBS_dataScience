"""Observed-development batch mapping with a lexical-only NCS baseline."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from p4_ncs.mapping.mapping_basis import is_bare_tool_mention
from p4_ncs.retrieval.lexical_index import LexicalIndex

MAPPING_MODE = "LEXICAL_BASELINE"
CODESET_STATUS = "REVIEW_REQUIRED"
NCS_MAP_VERSION = "ncs-lexical-observed-v0.1"


def _confidence(mapping_basis: str, score: float | None) -> str:
    if mapping_basis == "dictionaryRule":
        return "HIGH_DEVELOPMENT"
    if score is None:
        return "UNMAPPED"
    if score >= 0.25:
        return "HIGH_DEVELOPMENT"
    if score >= 0.12:
        return "MEDIUM_DEVELOPMENT"
    return "LOW_DEVELOPMENT"


def _base_output(row: object, data_version: str) -> dict[str, object]:
    return {
        "trackId": row.trackId,
        "sectionId": row.sectionId,
        "inputSha256": row.inputSha256,
        "parseVersion": row.parseVersion,
        "ncsMapVersion": NCS_MAP_VERSION,
        "dataVersion": data_version,
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "dataProvenance": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalAnalysisAllowed": False,
        "promotionAllowed": False,
        "mappingMode": MAPPING_MODE,
        "codeSetStatus": CODESET_STATUS,
        "goldValidatedFlag": False,
        "denseScore": None,
    }


def _alias_subcodes(evidence_text: str, alias_df: pd.DataFrame) -> list[str]:
    text = evidence_text.lower()
    hits = alias_df.loc[
        alias_df["alias"].astype("string").str.lower().map(lambda alias: alias in text),
        "ncsSubCode",
    ].astype(str)
    return sorted(set(hits))


def map_observed_duties(
    duties: pd.DataFrame,
    lexical_index: LexicalIndex,
    alias_df: pd.DataFrame,
    codeset_df: pd.DataFrame,
    data_version: str,
    top_k: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Materialize top-5 candidates and one development match per duty.

    Alias hits anchor retrieval to the same NCS subcategory.  Otherwise the
    search space is the 69 included REVIEW_REQUIRED subcategories.  Each
    lexical hit names the matching unit and is asserted to share the returned
    subcategory prefix.
    """
    included = codeset_df.loc[codeset_df["included"].astype(bool)].copy()
    valid_subcodes = set(included["ncsSubCode"].astype(str))
    names = dict(zip(codeset_df["ncsSubCode"].astype(str), codeset_df["ncsSubName"].astype(str)))
    candidate_rows: list[dict[str, object]] = []
    match_rows: list[dict[str, object]] = []

    for row in duties.sort_values(["trackId", "sectionId"], kind="stable").itertuples(index=False):
        base = _base_output(row, data_version)
        evidence = str(row.evidenceText).strip()
        unmapped_reason: str | None = None
        if not bool(row.ncsEligibleFlag):
            hits = []
            unmapped_reason = "NCS_INELIGIBLE_INPUT"
        elif not evidence:
            hits = []
            unmapped_reason = "EMPTY_EVIDENCE"
        elif is_bare_tool_mention(evidence):
            hits = []
            unmapped_reason = "BARE_TOOL_MENTION"
        else:
            aliases = _alias_subcodes(evidence, alias_df)
            allowed = aliases or valid_subcodes
            hits = lexical_index.search(evidence, top_k=top_k, allowed_subcodes=allowed)
            if not hits and aliases:
                # A dictionary rule is valid evidence even when no unit label
                # overlaps; it stays within the alias-declared subcategory.
                for subcode in aliases[:top_k]:
                    candidate_rows.append({
                        **base,
                        "candidateRank": len(candidate_rows) + 1,
                        "ncsSubCode": subcode,
                        "ncsSubName": names[subcode],
                        "matchedNcsUnitCode": None,
                        "matchedNcsUnitName": None,
                        "mappingBasis": "dictionaryRule",
                        "lexicalScore": None,
                        "developmentConfidenceCategory": "HIGH_DEVELOPMENT",
                        "sameSubcategoryRestrictedFlag": True,
                        "unmappedReason": None,
                    })
                section_candidates = candidate_rows[-len(aliases[:top_k]):]
                for rank, candidate in enumerate(section_candidates, start=1):
                    candidate["candidateRank"] = rank
                best = section_candidates[0]
                match_rows.append({**best, "selectedCandidateRank": 1})
                continue
            if not hits:
                unmapped_reason = "NO_LEXICAL_MATCH"

        section_candidates: list[dict[str, object]] = []
        aliases = _alias_subcodes(evidence, alias_df) if hits else []
        for rank, hit in enumerate(hits, start=1):
            hit_dict = asdict(hit)
            if not str(hit.matchedNcsUnitCode).startswith(hit.ncsSubCode):
                raise AssertionError("candidate unit escaped its NCS subcategory")
            basis = "dictionaryRule" if hit.ncsSubCode in aliases else "semanticMatch"
            candidate = {
                **base,
                "candidateRank": rank,
                **hit_dict,
                "mappingBasis": basis,
                "developmentConfidenceCategory": _confidence(basis, hit.lexicalScore),
                "sameSubcategoryRestrictedFlag": bool(aliases),
                "unmappedReason": None,
            }
            section_candidates.append(candidate)
            candidate_rows.append(candidate)

        if section_candidates:
            match_rows.append({**section_candidates[0], "selectedCandidateRank": 1})
        else:
            match_rows.append({
                **base,
                "candidateRank": None,
                "selectedCandidateRank": None,
                "ncsSubCode": None,
                "ncsSubName": None,
                "matchedNcsUnitCode": None,
                "matchedNcsUnitName": None,
                "mappingBasis": "unmapped",
                "lexicalScore": None,
                "developmentConfidenceCategory": "UNMAPPED",
                "sameSubcategoryRestrictedFlag": False,
                "unmappedReason": unmapped_reason,
            })

    candidates = pd.DataFrame(candidate_rows)
    matches = pd.DataFrame(match_rows)
    if len(matches) != len(duties):
        raise AssertionError("unmapped preservation failed")
    if not candidates.empty and int(candidates.groupby("sectionId").size().max()) > top_k:
        raise AssertionError("candidate top-k cap failed")
    return candidates, matches
