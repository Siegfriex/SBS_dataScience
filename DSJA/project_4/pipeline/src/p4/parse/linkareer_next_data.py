from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.casefold() == "script" and attributes.get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self.capture:
            self.capture = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)


def extract_next_data(html: str) -> dict[str, Any]:
    parser = _NextDataParser()
    parser.feed(html)
    if not parser.parts:
        raise ValueError("SSR HTML does not contain __NEXT_DATA__")
    payload = json.loads("".join(parser.parts))
    if not isinstance(payload, dict):
        raise TypeError("__NEXT_DATA__ must contain a JSON object")
    return payload


def extract_page_props(next_data: dict[str, Any]) -> dict[str, Any]:
    props = next_data.get("props", {}).get("pageProps", next_data.get("pageProps"))
    if not isinstance(props, dict):
        raise ValueError("__NEXT_DATA__ missing pageProps")
    return props

