from __future__ import annotations

import re
import hashlib
import unicodedata
from typing import Any

from p4.common.hashing import canonical_json_sha256


_SPACE = re.compile(r"\s+")
_COMPANY_TOKENS = re.compile(
    r"(?:\(주\)|㈜|주식회사|유한회사|유한책임회사|재단법인|사단법인)", re.IGNORECASE
)
_PUNCT = re.compile(r"[^0-9a-z가-힣]+", re.IGNORECASE)


def normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return _SPACE.sub(" ", text)


def normalize_company(value: Any) -> str:
    text = _COMPANY_TOKENS.sub("", normalize(value))
    return _PUNCT.sub("", text)


normalizeCompany = normalize_company


def _key(prefix: str, *parts: Any) -> str:
    normalized = [normalize(part) for part in parts]
    return f"{prefix}_{canonical_json_sha256(normalized)[:24]}"


def _canonical_contract_key(prefix: str, *parts: Any) -> str:
    if any(part is None or str(part) == "" for part in parts):
        raise ValueError(f"{prefix} canonical key inputs must be non-empty")
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


def make_posting_id(source_name: str, source_posting_id: str, source_url: str | None = None) -> str:
    del source_url
    return _canonical_contract_key("PST", source_name, source_posting_id)


def make_raw_posting_id(source_name: str, source_posting_id: str, raw_sha256: str) -> str:
    return _canonical_contract_key("RAW", source_name, source_posting_id, raw_sha256)


def make_track_id(posting_id: str, track_index: int | str) -> str:
    return _canonical_contract_key("TRK", posting_id, track_index)


def make_section_id(track_id: str, section_order: int | str) -> str:
    return _canonical_contract_key("SEC", track_id, section_order)


def make_requirement_id(section_id: str, requirement_type: str, normalized_evidence: str) -> str:
    return _canonical_contract_key("REQ", section_id, requirement_type, normalized_evidence)


def make_asset_id(posting_id: str, asset_url: str, asset_sha256: str | None = None) -> str:
    return _key("AST", posting_id, asset_url, asset_sha256 or "")


def make_ocr_id(asset_id: str, engine: str, model_version: str) -> str:
    return _key("OCR", asset_id, engine, model_version)


def make_match_id(track_id: str, ncs_unit_code: str, mapping_basis: str, evidence_hash: str) -> str:
    return _canonical_contract_key("NMT", track_id, ncs_unit_code, mapping_basis, evidence_hash)


def make_duplicate_group_id(company_key: str, normalized_title: str, first_posted_at: Any) -> str:
    return _key("DUP", company_key, normalized_title, first_posted_at)


def make_company_key(company_name: str) -> str:
    return _key("COM", normalize_company(company_name))


def make_metric_id(period_month: Any, cohort_type: str, job_code_level: str, job_code: str, dedup_applied: bool) -> str:
    return _key("MET", period_month, cohort_type, job_code_level, job_code, int(dedup_applied))


makePostingId = make_posting_id
makeRawPostingId = make_raw_posting_id
makeTrackId = make_track_id
makeSectionId = make_section_id
makeRequirementId = make_requirement_id
makeAssetId = make_asset_id
makeOcrId = make_ocr_id
makeMatchId = make_match_id
makeDuplicateGroupId = make_duplicate_group_id
makeCompanyKey = make_company_key
makeMetricId = make_metric_id
