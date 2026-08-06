from __future__ import annotations

import re
from typing import Any

from p4.common.keys import make_requirement_id, normalize
from p4.normalize.semantic_recovery import SEMANTIC_RECOVERY_VERSION


_BULLET = re.compile(r"(?:^|\n)\s*(?:[-*•·]|\d+[.)])?\s*(.+?)(?=\n|$)")
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*년")
_MONTHS = re.compile(r"(\d+)\s*(?:개월|개월이상)")
_PRIOR_EXPERIENCE = re.compile(r"(?:동일|관련|실무|상용|인턴|프로젝트)\s*(?:직무\s*)?(?:경험|경력)")
_PORTFOLIO = re.compile(r"포트폴리오")
_PROJECT = re.compile(r"(?:프로젝트|과제)\s*(?:수행|경험|경력|참여)?")
_CERTIFICATE = re.compile(r"(?:자격증|자격\s*소지|기사(?:\s|$)|기능사|산업기사|공인\s*자격)")
_DEGREE_PATTERNS = (
    ("doctorate", re.compile(r"(?:박사|doctoral|ph\.?d)", re.IGNORECASE)),
    ("master", re.compile(r"(?:석사|master)", re.IGNORECASE)),
    ("associate", re.compile(r"(?:전문학사|전문대졸|2년제|3년제)", re.IGNORECASE)),
    ("bachelor", re.compile(r"(?:학사|(?<!전문)대졸|4년제|bachelor)", re.IGNORECASE)),
    ("highSchool", re.compile(r"(?:고졸|고등학교\s*졸업)", re.IGNORECASE)),
)


def _obligation(section: dict[str, Any]) -> str:
    section_type = str(section.get("sectionType") or "").casefold()
    if section_type == "required" and bool(section.get("boundaryResolvedFlag")):
        return "required"
    if section_type == "preferred" and bool(section.get("boundaryResolvedFlag")):
        return "preferred"
    return "unknown"


def _degree_level(text: str) -> str | None:
    for level, pattern in _DEGREE_PATTERNS:
        if pattern.search(text):
            return level
    return None


def _fact_types(text: str) -> list[str]:
    facts: list[str] = []
    if experience_months(text) is not None:
        facts.append("careerMonths")
    if _PRIOR_EXPERIENCE.search(text):
        facts.append("priorExperience")
    if _PORTFOLIO.search(text):
        facts.append("portfolio")
    if _PROJECT.search(text):
        facts.append("project")
    if _CERTIFICATE.search(text):
        facts.append("certificate")
    if _degree_level(text):
        facts.append("degree")
    return facts or ["other"]


def experience_months(text: str) -> int | None:
    values: list[int] = []
    values.extend(round(float(value) * 12) for value in _YEARS.findall(text))
    values.extend(int(value) for value in _MONTHS.findall(text))
    return min(values) if values else None


def extract_requirements(section: dict[str, Any]) -> list[dict[str, Any]]:
    section_id = section["sectionId"]
    obligation = _obligation(section)
    mandatory = obligation == "required"
    rows: list[dict[str, Any]] = []
    for ordinal, match in enumerate(_BULLET.finditer(str(section.get("sectionText") or ""))):
        text = match.group(1).strip()
        if not text:
            continue
        normalized = normalize(text)
        min_months = experience_months(normalized)
        degree_level = _degree_level(normalized)
        for fact_type in _fact_types(normalized):
            rows.append(
                {
                    "requirementId": make_requirement_id(section_id, f"{obligation}:{fact_type}", normalized),
                    "sectionId": section_id,
                    "requirementType": fact_type,
                    "obligation": obligation,
                    "requirementText": text,
                    "evidenceText": text,
                    "numericValue": min_months if fact_type == "careerMonths" else None,
                    "unit": "months" if fact_type == "careerMonths" else None,
                    "normalizedTextValue": normalized,
                    "rawCertificateName": text if fact_type == "certificate" else None,
                    "nationalCertificateClass": None,
                    "requiredDegreeLevel": degree_level if fact_type == "degree" else None,
                    "extractorVersion": SEMANTIC_RECOVERY_VERSION,
                    "extractionConfidence": 1.0 if obligation != "unknown" and fact_type != "other" else 0.5,
                    "humanReviewRequiredFlag": obligation == "unknown" or fact_type == "other",
                    # Backward-compatible consumer fields. The canonical meaning is
                    # carried by requirementType + obligation above.
                    "mandatoryFlag": mandatory,
                    "minExperienceMonths": min_months if fact_type == "careerMonths" else None,
                    "minCareerMonths": min_months if fact_type == "careerMonths" else None,
                    "priorExperienceFlag": bool(mandatory and fact_type == "priorExperience"),
                    "portfolioFlag": fact_type == "portfolio",
                    "projectFlag": fact_type == "project",
                    "certificateFlag": fact_type == "certificate",
                    "degreeFlag": fact_type == "degree",
                }
            )
    return rows
