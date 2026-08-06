import pandas as pd

from p4.normalize.postings import normalize_posting, normalize_postings
from p4.normalize.tracks import split_tracks
from p4.parse.sections import parse_sections


def _raw(**overrides):
    row = {
        "rawPostingId": "RAW_1",
        "sourceName": "linkareer",
        "sourcePostingId": "123",
        "sourceUrl": "https://example.test/123",
        "rawSha256": "a" * 64,
        "titleRaw": "데이터 분석 인턴",
        "companyRaw": "(주) 예시",
        "postedAtRaw": "2026-08-06T12:00:00+09:00",
        "bodyRaw": "담당업무\n데이터 분석과 리포팅 수행\n자격요건\n관련 프로젝트 경험 필수",
        "postingKind": "recruit",
    }
    row.update(overrides)
    return row


def test_posting_normalization_and_eligibility_are_separate_from_dedup():
    normalized = normalize_posting(_raw())
    assert normalized["postingEligibleFlag"] is True
    assert normalized["canonicalRecordFlag"] is True
    assert normalized["periodMonth"].isoformat() == "2026-08-01"
    assert normalized["companyName"] == "(주) 예시"
    assert len(normalize_postings(pd.DataFrame([_raw()]))) == 1


def test_invalid_kind_or_short_body_is_ineligible():
    assert normalize_posting(_raw(postingKind="activity"))["postingEligibleFlag"] is False
    assert normalize_posting(_raw(bodyRaw="짧음"))["postingEligibleFlag"] is False


def test_sections_preserve_required_preferred_boundary():
    sections = parse_sections("담당업무\n분석\n자격요건\n경력 필수\n우대사항\nSQL 우대")
    assert [section.section_type for section in sections] == ["duty", "required", "preferred"]
    assert all(section.boundary_resolved for section in sections)


def test_unstructured_section_marks_boundary_unresolved():
    section = parse_sections("구조 없는 공고 본문")[0]
    assert section.section_type == "other"
    assert section.boundary_resolved is False


def test_mixed_posting_is_not_force_allocated():
    posting = normalize_posting(_raw(titleRaw="신입 및 인턴 채용"))
    track = split_tracks(posting)[0]
    assert track["trackType"] == "mixedUnresolved"
    assert track["mixedResolvedFlag"] is False


def test_explicit_tracks_can_be_split():
    posting = normalize_posting(_raw())
    tracks = split_tracks(
        posting,
        [
            {"trackType": "entry", "text": "데이터 신입", "jobCodeLevel": "ncsSub", "jobCode": "200101"},
            {"trackType": "intern", "text": "데이터 인턴", "jobCodeLevel": "ncsSub", "jobCode": "200101"},
        ],
    )
    assert [track["trackType"] for track in tracks] == ["entry", "intern"]
    assert len({track["trackId"] for track in tracks}) == 2
