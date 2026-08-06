from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


_BLOCK_TAGS = {"div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "strong"}
_HEADINGS = {
    "담당업무": "duty",
    "주요업무": "duty",
    "직무내용": "duty",
    "자격요건": "required",
    "필수요건": "required",
    "지원자격": "required",
    "우대사항": "preferred",
    "우대요건": "preferred",
}


class _BlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, dict[str, str | None], list[str]]] = []
        self.blocks: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in _BLOCK_TAGS:
            self.stack.append((tag.casefold(), dict(attrs), []))

    def handle_data(self, data: str) -> None:
        for _, _, parts in self.stack:
            parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag.casefold():
            return
        block_tag, attrs, parts = self.stack.pop()
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        if text and not any(existing["text"] == text for existing in self.blocks):
            self.blocks.append({"tag": block_tag, "attrs": attrs, "text": text})


def parse_activity_text_html(html: str) -> list[dict[str, Any]]:
    parser = _BlockParser()
    parser.feed(html)
    current_section = "other"
    rows: list[dict[str, Any]] = []
    char_offset = 0
    for ordinal, block in enumerate(parser.blocks):
        compact = re.sub(r"[\s:：\-]+", "", block["text"])
        heading = _HEADINGS.get(compact)
        style = str(block["attrs"].get("style") or "").casefold()
        visual_heading = block["tag"].startswith("h") or block["tag"] == "strong" or "font-weight" in style
        heading_candidate = heading is not None or visual_heading
        if heading:
            current_section = heading
        start = char_offset
        end = start + len(block["text"])
        rows.append(
            {
                "blockOrdinal": ordinal,
                "tag": block["tag"],
                "text": block["text"],
                "headingCandidate": heading_candidate,
                "sectionAssignment": heading or current_section,
                "boundaryResolvedFlag": heading is not None or current_section != "other",
                "evidenceSpan": {"startChar": start, "endChar": end},
            }
        )
        char_offset = end + 1
    return rows

