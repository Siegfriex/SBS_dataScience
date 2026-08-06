"""Schema-tolerant parsers for synthetic and future observed API fixtures."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from p4_ncs.api.redaction import canonical_json_sha256


@dataclass(frozen=True)
class ParsedApiResponse:
    provider: str
    response_class: str
    records: tuple[dict[str, Any], ...]
    page_no: int | None
    total_count: int | None
    error_code: str | None
    error_message: str | None
    observed_schema_sha256: str


def _flatten_xml(element: ET.Element) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in list(element):
        tag = child.tag.split("}")[-1]
        result[tag] = (child.text or "").strip() if not list(child) else _flatten_xml(child)
    return result


def _schema_signature(records: list[dict[str, Any]]) -> str:
    signature = sorted({key for row in records for key in row})
    return canonical_json_sha256(signature)


def _classify(code: str | None, message: str | None, record_count: int) -> str:
    text = f"{code or ''} {message or ''}".lower()
    if any(token in text for token in ("auth", "service key", "servicekey", "unauthorized", "인증")):
        return "AUTH_ERROR"
    if any(token in text for token in ("parameter", "param", "invalid", "필수", "값을 확인")):
        return "PARAM_ERROR"
    if any(token in text for token in ("server", "internal", "timeout")):
        return "SERVER_ERROR"
    if record_count == 0 or any(token in text for token in ("empty", "no data", "nodata")):
        return "EMPTY_VALID"
    return "SUCCESS"


def parse_ncs_xml(body: str) -> ParsedApiResponse:
    root = ET.fromstring(body)
    values = {node.tag.split("}")[-1]: (node.text or "").strip() for node in root.iter() if not list(node)}
    item_nodes = [node for node in root.iter() if node.tag.split("}")[-1].lower() == "item"]
    records = [_flatten_xml(node) for node in item_nodes]
    code = values.get("resultCode") or values.get("returnReasonCode")
    message = values.get("resultMsg") or values.get("returnAuthMsg") or values.get("errMsg")
    page = values.get("pageNo")
    total = values.get("totalCount")
    return ParsedApiResponse(
        provider="NCS_OPENAPI",
        response_class=_classify(code, message, len(records)),
        records=tuple(records),
        page_no=int(page) if page and page.isdigit() else None,
        total_count=int(total) if total and total.isdigit() else None,
        error_code=code,
        error_message=message,
        observed_schema_sha256=_schema_signature(records),
    )


def parse_work24(body: str, content_type: str) -> ParsedApiResponse:
    if "json" in content_type.lower() or body.lstrip().startswith(("{", "[")):
        payload = json.loads(body)
        code = str(payload.get("resultCode") or payload.get("code") or "") or None
        message = str(payload.get("resultMsg") or payload.get("message") or "") or None
        raw_records = payload.get("items", payload.get("data", []))
        if isinstance(raw_records, dict):
            raw_records = raw_records.get("item", [raw_records])
        records = list(raw_records) if isinstance(raw_records, list) else []
        page = payload.get("pageNo")
        total = payload.get("totalCount")
        return ParsedApiResponse(
            provider="WORK24",
            response_class=_classify(code, message, len(records)),
            records=tuple(records),
            page_no=int(page) if page is not None else None,
            total_count=int(total) if total is not None else None,
            error_code=code,
            error_message=message,
            observed_schema_sha256=_schema_signature(records),
        )
    parsed = parse_ncs_xml(body)
    return ParsedApiResponse(
        provider="WORK24",
        response_class=parsed.response_class,
        records=parsed.records,
        page_no=parsed.page_no,
        total_count=parsed.total_count,
        error_code=parsed.error_code,
        error_message=parsed.error_message,
        observed_schema_sha256=parsed.observed_schema_sha256,
    )


def parse_fixture_document(document: dict[str, Any]) -> ParsedApiResponse:
    if document.get("sourceClass") != "SYNTHETIC_CONTRACT_FIXTURE":
        raise ValueError("fixture sourceClass must be SYNTHETIC_CONTRACT_FIXTURE")
    provider = document.get("provider")
    if provider == "NCS_OPENAPI":
        return parse_ncs_xml(str(document["body"]))
    if provider == "WORK24":
        return parse_work24(str(document["body"]), str(document["contentType"]))
    raise ValueError(f"unsupported fixture provider: {provider}")
