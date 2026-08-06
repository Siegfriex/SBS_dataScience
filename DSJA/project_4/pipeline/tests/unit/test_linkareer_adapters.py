import json

from p4.normalize.eligibility import eligibility_flags, resolve_job_types
from p4.normalize.linkareer import adapt_linkareer_source
from p4.parse.linkareer_activity_text import build_ocr_queue_candidates, parse_activity_text_html
from p4.parse.linkareer_apollo_cache import extract_activity, find_apollo_cache, parse_masked_ssr_fixture
from p4.parse.linkareer_apq import parse_apq_entries
from p4.parse.linkareer_next_data import extract_next_data, extract_page_props


def masked_apq_fixture():
    return {
        "data": {
            "CalendarScreen_ActivityCalendarEntries": [
                {
                    "id": "MASKED_1",
                    "group": "recruit",
                    "title": "마스킹 채용 공고",
                    "activityTypeID": 5,
                    "activityStartAt": "2026-01-01",
                    "activityEndAt": "2026-01-31",
                    "organizationName": "마스킹 기업",
                    "jobTypes": [{"id": "JT1", "name": "인턴"}],
                    "recruitStartAt": "2026-01-01",
                    "recruitCloseAt": "2026-01-31",
                    "createdAt": "2026-01-01T00:00:00+09:00",
                    "manager": {"name": "개인정보", "email": "masked@example.invalid"},
                }
            ]
        }
    }


def test_apq_entry_parsing_preserves_job_types_masks_manager_and_is_idempotent():
    payload = masked_apq_fixture()
    first = parse_apq_entries(payload)
    second = parse_apq_entries(payload)
    assert first == second
    assert json.loads(first[0]["jobTypesRawJson"]) == [{"id": "JT1", "name": "인턴"}]
    assert first[0]["activityTypeId"] == 5
    assert first[0]["managerMasked"] == {"email": "[MASKED]", "name": "[MASKED]"}
    assert "개인정보" not in json.dumps(first, ensure_ascii=False)


def test_apq_calendar_date_connections_are_flattened_and_deduplicated():
    activity = masked_apq_fixture()["data"]["CalendarScreen_ActivityCalendarEntries"][0]
    payload = {
        "responseBody": {
            "data": {
                "activityCalendarEntries": {
                    "nodes": [
                        {"date": 1, "start": {"nodes": [activity]}, "end": {"nodes": [activity]}},
                    ]
                }
            }
        }
    }
    rows = parse_apq_entries(payload)
    assert len(rows) == 1
    assert rows[0]["id"] == "MASKED_1"


def test_next_data_apollo_duties_activity_text_and_external_url():
    cache = {
        "ROOT_QUERY": {},
        "Activity:MASKED_1": {
            "id": "MASKED_1",
            "duties": [{"__ref": "Duty:1"}],
            "activityText": {"__ref": "ActivityText:1"},
            "externalApplyUrl": "https://ats.example.invalid/apply/1",
        },
        "Duty:1": {"id": "1", "jobType": {"name": "인턴"}, "title": "분석"},
        "ActivityText:1": {"text": "<div><strong>담당업무</strong><p>데이터 분석</p></div>"},
    }
    html = '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(
        {"props": {"pageProps": {"apolloState": cache}}}
    ) + "</script></html>"
    page_props = extract_page_props(extract_next_data(html))
    extracted_cache = find_apollo_cache(page_props)
    detail = extract_activity(extracted_cache, "MASKED_1")
    assert detail["dutiesJobTypesRaw"] == [{"name": "인턴"}]
    assert "담당업무" in detail["activityTextHtml"]
    assert detail["externalAtsDomain"] == "ats.example.invalid"
    assert detail["externalDetailOnlyFlag"] is False


def test_external_ats_only_eligibility():
    cache = {
        "ROOT_QUERY": {},
        "Activity:MASKED_2": {"id": "MASKED_2", "duties": [], "externalApplyUrl": "https://ats.example.invalid/2"},
    }
    detail = extract_activity(cache, "MASKED_2")
    assert detail["externalDetailOnlyFlag"] is True
    flags = eligibility_flags(
        posting_kind="recruit",
        posted_at_available=True,
        source_integrity_available=True,
        job_types_resolved=True,
        activity_text_available=False,
        required_or_preferred_text_available=False,
        boundary_resolved=False,
        track_resolved=True,
        text_minimum_met=False,
        duty_text_available=False,
        mappable_task_sentence_available=False,
        external_apply=True,
        external_detail_only=True,
    )
    assert flags["rq1EligibleFlag"] is True
    assert flags["rq2EligibleFlag"] is False
    assert flags["ncsEligibleFlag"] is False
    assert flags["rq2ExclusionReason"] == "externalAtsBodyUnavailable"


def test_job_type_priority_and_conflict_review():
    resolved = resolve_job_types(
        job_types=[{"name": "인턴"}],
        duty_job_types=[],
        detail_tags=[],
        title="경력직 채용",
        body="경력 3년",
    )
    assert resolved["resolvedJobTypes"] == ["intern"]
    assert resolved["jobTypeSource"] == "structured"
    assert resolved["jobTypeConflictFlag"] is True
    assert resolved["reviewFlag"] is True


def test_activity_text_lineage_and_unresolved_boundary():
    rows = parse_activity_text_html(
        '<div style="font-weight:700">담당업무</div><div>데이터 품질 점검</div><div>모호한 설명</div>'
    )
    assert rows[0]["headingCandidate"] is True
    assert rows[1]["sectionAssignment"] == "duty"
    assert rows[1]["evidenceSpan"]["endChar"] > rows[1]["evidenceSpan"]["startChar"]
    unresolved = parse_activity_text_html("<div>구조 없는 단일 문단</div>")
    assert unresolved[0]["boundaryResolvedFlag"] is False


def test_source_adapter_emits_split_eligibility_and_raw_lineage():
    index = parse_apq_entries(masked_apq_fixture())[0]
    detail = {
        "dutiesRawJson": '[{"jobType":{"name":"인턴"}}]',
        "dutiesJobTypesRaw": [{"name": "인턴"}],
        "activityTextHtml": "<strong>담당업무</strong><p>데이터 품질을 점검한다</p><strong>자격요건</strong><p>지원 가능</p>",
        "activityTextAvailableFlag": True,
        "externalApplyUrl": "https://ats.example.invalid/apply/1",
        "externalAtsDomain": "ats.example.invalid",
        "externalDetailOnlyFlag": False,
    }
    adapted = adapt_linkareer_source(index, detail)
    assert adapted["rq1EligibleFlag"] is True
    assert adapted["rq2EligibleFlag"] is True
    assert adapted["ncsEligibleFlag"] is True
    assert adapted["jobTypesRawJson"].startswith("[")
    assert adapted["dutiesRawJson"].startswith("[")
    assert adapted["activityTextBlocks"][1]["sectionAssignment"] == "duty"
    assert adapted["externalApplyFlag"] is True
    assert adapted["externalDetailOnlyFlag"] is False


def test_external_apply_does_not_exclude_when_activity_text_is_usable():
    flags = eligibility_flags(
        posting_kind="recruit",
        posted_at_available=True,
        source_integrity_available=True,
        job_types_resolved=True,
        activity_text_available=True,
        required_or_preferred_text_available=True,
        boundary_resolved=True,
        track_resolved=True,
        text_minimum_met=True,
        duty_text_available=True,
        mappable_task_sentence_available=True,
        external_apply=True,
        external_detail_only=False,
    )
    assert flags["rq2EligibleFlag"] is True
    assert flags["ncsEligibleFlag"] is True
    assert json.loads(flags["rq2ExclusionReasonsJson"]) == []


def test_embedded_image_routes_to_ocr_only_when_text_is_insufficient():
    short_html = '<p>채용공고</p><p><img src="https://cdn.example.invalid/posting.jpg"></p>'
    queue = build_ocr_queue_candidates(short_html)
    assert queue[0]["assetUrl"] == "https://cdn.example.invalid/posting.jpg"
    assert queue[0]["routingReason"] == "activityTextEmbeddedImageWithInsufficientText"
    long_html = f'<p>{"담당업무 데이터 분석 " * 40}</p><img src="https://cdn.example.invalid/banner.jpg">'
    assert build_ocr_queue_candidates(long_html) == []


def test_masked_ssr_fixture_masks_manager_and_preserves_external_apply():
    payload = {
        "activityData": {
            "id": "MASKED_3",
            "manager": {"id": "PII_1", "email": "pii@example.invalid"},
            "managerName": "PII name",
            "applyDetail": "https://ats.example.invalid/apply",
            "duties": {"nodes": [{"jobType": "INTERN"}]},
        },
        "apolloState_ActivityText_sample": {
            "ActivityText:1": {"text": '<p>채용공고</p><img src="https://cdn.example.invalid/posting.jpg">'}
        },
    }
    detail = parse_masked_ssr_fixture(payload)
    assert detail["managerMasked"] == {"email": "[MASKED]", "id": "[MASKED]"}
    assert "PII" not in json.dumps(detail, ensure_ascii=False)
    assert detail["externalApplyFlag"] is True
    assert detail["externalDetailOnlyFlag"] is False
    assert detail["ocrRoutingRequiredFlag"] is True


def test_non_recruit_activity_is_excluded_from_posting_denominator():
    index = parse_apq_entries(masked_apq_fixture())[0]
    index["activityTypeId"] = 1
    index["activityTypeID"] = 1
    index["group"] = "NORMAL"
    detail = {
        "activityTextHtml": "<strong>담당업무</strong><p>대외활동을 수행한다</p><strong>자격요건</strong><p>누구나</p>",
        "activityTextAvailableFlag": True,
    }
    adapted = adapt_linkareer_source(index, detail)
    assert adapted["postingEligibleFlag"] is False
    assert adapted["rq2ExclusionReason"] == "nonRecruitPosting"
