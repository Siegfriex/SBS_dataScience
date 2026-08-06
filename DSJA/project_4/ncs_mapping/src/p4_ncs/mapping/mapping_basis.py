"""mappingBasis classification and the tool-name-alone exclusion rule.

Per spec §7.4: a bare tool/language mention ("Python 가능", "SQL 사용",
"Java 경험") must never by itself justify assigning an NCS level -- it only
becomes evidence when paired with a duty/task description (e.g. "Python으로
데이터 파이프라인 구축"). This module enforces that as a guard, not just a
convention.
"""
from __future__ import annotations

from enum import Enum

_BARE_TOOL_TERMS = {
    "python", "sql", "java", "javascript", "c++", "c#", "r", "excel",
    "파이썬", "자바", "자바스크립트",
}


class MappingBasis(str, Enum):
    NCS_UNIT_DIRECT = "ncsUnitDirect"
    NCS_PERFORMANCE_CRITERIA = "ncsPerformanceCriteria"
    NCS_LEARNING_MODULE = "ncsLearningModule"
    DICTIONARY_RULE = "dictionaryRule"
    SEMANTIC_MATCH = "semanticMatch"
    UNMAPPED = "unmapped"


def is_bare_tool_mention(evidence_text: str) -> bool:
    """True if the evidence text is just a tool/language name (± 가능/사용/경험 particles),
    with no duty/task verb attached -- the case this module must refuse to map.
    """
    stripped = evidence_text.strip().lower()
    for suffix in ("가능", "사용", "경험", "능숙", " skill", " ability"):
        stripped = stripped.replace(suffix.lower(), "").strip()
    return stripped in _BARE_TOOL_TERMS


def classify_mapping_basis(evidence_text: str, has_dictionary_hit: bool, has_semantic_hit: bool) -> MappingBasis:
    if is_bare_tool_mention(evidence_text):
        return MappingBasis.UNMAPPED
    if has_dictionary_hit:
        return MappingBasis.DICTIONARY_RULE
    if has_semantic_hit:
        return MappingBasis.SEMANTIC_MATCH
    return MappingBasis.UNMAPPED
