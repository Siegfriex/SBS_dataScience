from __future__ import annotations

import re
from typing import Any

from p4.common.keys import make_requirement_id, normalize


_BULLET = re.compile(r"(?:^|\n)\s*(?:[-*•·]|\d+[.)])?\s*(.+?)(?=\n|$)")
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*년")
_MONTHS = re.compile(r"(\d+)\s*(?:개월|개월이상)")
_PRIOR_EXPERIENCE = re.compile(r"(?:동일|관련|실무|상용|인턴|프로젝트)\s*(?:직무\s*)?(?:경험|경력)")
_PORTFOLIO = re.compile(r"포트폴리오")


def experience_months(text: str) -> int | None:
    values: list[int] = []
    values.extend(round(float(value) * 12) for value in _YEARS.findall(text))
    values.extend(int(value) for value in _MONTHS.findall(text))
    return min(values) if values else None


def extract_requirements(section: dict[str, Any]) -> list[dict[str, Any]]:
    section_id = section["sectionId"]
    section_type = section.get("sectionType", "other")
    mandatory = section_type == "required" and bool(section.get("boundaryResolvedFlag"))
    rows: list[dict[str, Any]] = []
    for ordinal, match in enumerate(_BULLET.finditer(str(section.get("sectionText") or ""))):
        text = match.group(1).strip()
        if not text:
            continue
        normalized = normalize(text)
        rows.append(
            {
                "requirementId": make_requirement_id(section_id, ordinal, normalized),
                "sectionId": section_id,
                "requirementType": section_type,
                "requirementText": text,
                "mandatoryFlag": mandatory,
                "minExperienceMonths": experience_months(normalized),
                "priorExperienceFlag": bool(mandatory and _PRIOR_EXPERIENCE.search(normalized)),
                "portfolioFlag": bool(_PORTFOLIO.search(normalized)),
            }
        )
    return rows

