from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from p4.common.hashing import canonical_json_sha256, sha256_bytes
from p4.common.keys import (
    makeAssetId,
    makeCompanyKey,
    makeDuplicateGroupId,
    makeMatchId,
    makeMetricId,
    makeOcrId,
    makePostingId,
    makeRawPostingId,
    makeRequirementId,
    makeSectionId,
    makeTrackId,
    normalize,
    normalizeCompany,
)
from p4.common.time import ensure_seoul_datetime, period_month, quarter_number


def test_normalize_and_company_normalization():
    assert normalize("  ＡI\t개발  ") == "ai 개발"
    assert normalizeCompany("(주) 예시-기업") == "예시기업"
    assert normalizeCompany("예시기업 주식회사") == "예시기업"


@pytest.mark.parametrize(
    "function,args",
    [
        (makePostingId, ("linkareer", "123", "https://example.test/123")),
        (makeRawPostingId, ("PST_x", "a" * 64, "2026-08-06T12:00:00+09:00")),
        (makeTrackId, ("PST_x", 0, "개발")),
        (makeSectionId, ("TRK_x", "required", 0)),
        (makeRequirementId, ("SEC_x", 0, "경력 2년")),
        (makeAssetId, ("PST_x", "https://example.test/a.png", "b" * 64)),
        (makeOcrId, ("AST_x", "tesseract", "5")),
        (makeMatchId, ("SEC_x", "200101", "v1")),
        (makeDuplicateGroupId, ("COM_x", "개발자", "2026-01-01")),
        (makeCompanyKey, ("(주)예시",)),
        (makeMetricId, ("2026-01-01", "coreAiIt", "ncsSub", "2001", True)),
    ],
)
def test_all_keys_are_idempotent(function, args):
    assert function(*args) == function(*args)


def test_hashing_is_stable():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert canonical_json_sha256({"b": 2, "a": 1}) == canonical_json_sha256({"a": 1, "b": 2})


def test_timezone_and_period_rules():
    aware = datetime(2026, 8, 6, 12, tzinfo=ZoneInfo("UTC"))
    assert ensure_seoul_datetime(aware).hour == 21
    assert period_month(aware).isoformat() == "2026-08-01"
    assert quarter_number(aware) == 3
    with pytest.raises(ValueError):
        ensure_seoul_datetime(datetime(2026, 8, 6, 12))

