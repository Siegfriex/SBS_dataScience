from __future__ import annotations

import re
from dataclasses import dataclass


SECTION_ALIASES = {
    "duty": ("담당업무", "주요업무", "직무내용", "수행업무"),
    "required": ("자격요건", "필수요건", "지원자격", "필수사항"),
    "preferred": ("우대사항", "우대요건", "우대조건"),
}


@dataclass(frozen=True)
class ParsedSection:
    section_type: str
    section_ordinal: int
    text: str
    boundary_resolved: bool


def _heading_type(line: str) -> str | None:
    normalized = re.sub(r"[\s:：\-]+", "", line)
    for section_type, aliases in SECTION_ALIASES.items():
        if any(normalized == re.sub(r"\s+", "", alias) for alias in aliases):
            return section_type
    return None


def parse_sections(body_text: str) -> list[ParsedSection]:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    sections: list[ParsedSection] = []
    current_type = "other"
    current: list[str] = []

    def flush() -> None:
        if current:
            sections.append(
                ParsedSection(
                    section_type=current_type,
                    section_ordinal=len(sections),
                    text="\n".join(current),
                    boundary_resolved=current_type in {"duty", "required", "preferred"},
                )
            )

    for line in lines:
        heading = _heading_type(line)
        if heading:
            flush()
            current_type = heading
            current = []
        else:
            current.append(line)
    flush()
    if not sections and body_text.strip():
        sections.append(ParsedSection("other", 0, body_text.strip(), False))
    return sections

