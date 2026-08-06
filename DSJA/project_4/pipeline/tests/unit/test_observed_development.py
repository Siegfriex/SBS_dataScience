import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from p4.common.manifest_cursor import advance_cursor, plan_manifest_work, should_process_raw
from p4.common.hashing import canonical_json_sha256
from p4.contracts.duty_input import validate_observed_duty_input_handoff
from p4.contracts.release_validation import validate_release_gates
from p4.normalize.observed_batch import PARSE_VERSION, build_observed_batch
from p4.parse.linkareer_apollo_cache import extract_activity
from p4.warehouse.connection import connect
from p4.warehouse.observed import OBSERVED_PROVENANCE, bootstrap_observed_warehouse, replace_observed_table


def _real_ssr_shape(activity_id: str = "57115") -> str:
    cache = {
        "ROOT_QUERY": {},
        f"Activity:{activity_id}": {
            "id": activity_id,
            "title": "관측 인턴 채용",
            "organizationName": "관측 기업",
            "activityTypeID": 5,
            "group": "NORMAL",
            "createdAt": 1614737593000,
            "jobTypes": ["INTERN"],
            "duties": {"nodes": []},
            "applyDetail": "https://ats.example.invalid/apply",
            "managerName": "REMOVE ME",
            "managerEmail": "remove@example.invalid",
        },
        "ActivityText:standalone": {
            "text": '<div><strong>담당업무</strong><p>데이터 품질 점검</p><img src="https://img.example.invalid/poster.png"></div>'
            '<strong>자격요건</strong><p>SQL 경험</p>'
        },
    }
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": cache}}}
    return '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script></html>"


def test_old_ssr_standalone_activity_text_is_recovered_without_manager_pii():
    cache = json.loads(_real_ssr_shape().split('type="application/json">', 1)[1].split("</script>", 1)[0])[
        "props"
    ]["pageProps"]["__APOLLO_STATE__"]
    detail = extract_activity(cache, "57115")
    assert "담당업무" in detail["activityTextHtml"]
    assert detail["ocrRoutingRequiredFlag"] is True
    serialized = json.dumps(detail, ensure_ascii=False)
    assert "REMOVE ME" not in serialized
    assert "remove@example.invalid" not in serialized


def test_manifest_cursor_skips_same_sha_until_parse_version_changes():
    row = advance_cursor(7, "a" * 64, "CRAWL_20260806_03", PARSE_VERSION).as_dict()
    assert should_process_raw("a" * 64, PARSE_VERSION, [row]) is False
    assert should_process_raw("a" * 64, PARSE_VERSION + ".2", [row]) is True
    assert should_process_raw("b" * 64, PARSE_VERSION, [row]) is True
    plan = plan_manifest_work(
        [{"contentSha256": "a" * 64}, {"contentSha256": "b" * 64}], [row], PARSE_VERSION
    )
    assert [item["action"] for item in plan] == ["SKIP_IDENTICAL_RAW_AND_PARSE_VERSION", "PROCESS"]


def test_observed_warehouse_is_nonempirical_and_has_no_canonical_schemas(tmp_path):
    database = tmp_path / "p4.observed-dev.duckdb"
    metadata = bootstrap_observed_warehouse(database, PARSE_VERSION)
    assert metadata["dataProvenance"] == "OBSERVED_DEVELOPMENT_ONLY"
    assert metadata["empiricalAnalysisAllowed"] is False
    replace_observed_table(database, "raw_posting", pd.DataFrame([{"sourcePostingId": "1"}]))
    with connect(database, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM observed.raw_posting").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw','core','mart','ncs','qa')"
        ).fetchone()[0] == 0
    with pytest.raises(ValueError, match="p4.observed-dev.duckdb"):
        bootstrap_observed_warehouse(tmp_path / "p4.duckdb", PARSE_VERSION)


def test_real_ssr_shape_flows_to_sections_requirements_and_ocr_queue(tmp_path):
    release = tmp_path / "release"
    crawl = tmp_path / "crawl"
    raw_relative = Path("data/raw/linkareer/detail/2021/03/observed.html.gz")
    raw_path = crawl / raw_relative
    raw_path.parent.mkdir(parents=True)
    content = _real_ssr_shape().encode()
    with gzip.open(raw_path, "wb") as stream:
        stream.write(content)
    digest = hashlib.sha256(content).hexdigest()
    release.mkdir()
    (release / "fetch_manifest.jsonl").write_text(
        json.dumps(
            {
                "entityType": "detail",
                "requestUrl": "https://linkareer.com/activity/57115",
                "contentSha256": digest,
                "rawPath": str(raw_relative),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "sourcePostingId": "57115",
                "sourceName": "linkareer",
                "hasDetailRawHtml": True,
                "hasDerivedFields": False,
                "jobTypes": "INTERN",
                "activityTextAvailable": True,
                "externalApplyFlag": True,
                "externalDetailOnlyFlag": False,
                "rq1EligibleFlag": True,
                "rq2EligibleFlag": True,
                "ncsEligibleFlag": True,
            }
        ]
    ).to_parquet(release / "posting_manifest.parquet", index=False)
    (release / "stratified_detail_sample_n126.json").write_text("[]\n", encoding="utf-8")
    result = build_observed_batch(release, crawl)
    assert result["metrics"]["inputPostings"] == 1
    assert result["metrics"]["parseFailure"] == 0
    assert result["metrics"]["activityTextRecovered"] == 1
    assert result["metrics"]["embeddedImageRouted"] == 1
    assert set(result["frames"]["posting_section"]["sectionType"]) >= {"duty", "required"}
    assert len(result["frames"]["requirement_fact"]) >= 1
    assert set(result["frames"]["ocr_queue"]["queueStatus"]) == {"ASSET_NOT_FETCHED"}


def test_observed_duty_handoff_rejects_empirical_claims_and_accepts_required_rows(tmp_path):
    path = tmp_path / "handoff.json"
    payload = {
        "agentId": "P4-A2-PIPELINE",
        "recipientAgentId": "P4-A4-NCS",
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_03",
        "status": "OBSERVED_DEVELOPMENT_ONLY",
        "empiricalUseAllowed": False,
        "rows": [
            {
                "trackId": "TRK_x",
                "sectionId": "SEC_x",
                "evidenceText": "업무 근거",
                "jobTitle": "채용",
                "jobCode": None,
                "ncsEligibleFlag": True,
                "parseVersion": PARSE_VERSION,
                "inputSha256": "a" * 64,
            }
        ],
    }
    payload["rowCount"] = len(payload["rows"])
    payload["rowsSha256"] = canonical_json_sha256(payload["rows"])
    payload["promotionAllowed"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert validate_observed_duty_input_handoff(path)["rows"][0]["sectionId"] == "SEC_x"
    payload["empiricalUseAllowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be used as empirical"):
        validate_observed_duty_input_handoff(path)


def test_crawl03_style_validation_separates_source_pass_from_full_corpus_fail(tmp_path):
    root = tmp_path / "CRAWL_20260806_03"
    root.mkdir()
    (root / "fetch_manifest.jsonl").write_text(
        json.dumps(
            {
                "entityType": "detail",
                "requestUrl": "https://linkareer.com/activity/1",
                "rawPath": "data/raw/1.html.gz",
                "contentSha256": "a" * 64,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "sourcePostingId": "1",
                "hasDetailRawHtml": True,
                "rq1EligibleFlag": True,
                "rq2EligibleFlag": True,
                "ncsEligibleFlag": True,
            },
            {
                "sourcePostingId": "2",
                "hasDetailRawHtml": False,
                "rq1EligibleFlag": True,
                "rq2EligibleFlag": False,
                "ncsEligibleFlag": False,
            },
        ]
    ).to_parquet(root / "posting_manifest.parquet", index=False)
    pd.DataFrame(
        [
            {"periodMonth": "2026-01", "coverageStatus": "complete", "coverageReason": "complete"},
            {"periodMonth": "2026-02", "coverageStatus": "unverified", "coverageReason": "paginationUnverified"},
        ]
    ).to_parquet(root / "monthly_coverage.parquet", index=False)
    (root / "query.yaml").write_text("query: observed\n", encoding="utf-8")
    (root / "schema.json").write_text("{}\n", encoding="utf-8")
    handoff = {
        "release_id": "CRAWL_20260806_03",
        "contract_version": "2.1.2",
        "manifest_paths": ["fetch_manifest.jsonl", "posting_manifest.parquet"],
        "coverage_path": "monthly_coverage.parquet",
        "checksum_path": "CHECKSUMS.sha256",
        "query_registry_path": "query.yaml",
        "schema_snapshot_path": "schema.json",
        "source_start": "2026-01-01",
        "source_end": "2026-02-28",
        "status": "CRAWL_RELEASE_CANDIDATE",
        "pagination_verified": False,
        "transparent_client_verified": True,
        "robots_status": "allowed",
        "head_commit": "",
        "known_gaps": ["2 distinct posting IDs discovered"],
    }
    (root / "HANDOFF.json").write_text(json.dumps(handoff), encoding="utf-8")
    checksum_files = [
        "fetch_manifest.jsonl",
        "posting_manifest.parquet",
        "monthly_coverage.parquet",
        "query.yaml",
        "schema.json",
    ]
    (root / "CHECKSUMS.sha256").write_text(
        "".join(f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n" for name in checksum_files),
        encoding="utf-8",
    )
    result = validate_release_gates(root / "HANDOFF.json")
    assert result["sourceAdapterConformance"] == "PASS"
    assert result["fullCorpusAcceptance"] == "FAIL"
    assert result["coverage"] == {"targetMonths": 2, "completeMonths": 1, "unverifiedMonths": 1}
    assert {gap["failedGate"] for gap in result["failedGates"]} >= {
        "releaseCommitLineage",
        "monthlyPaginationCompleteness",
        "releaseStatus",
        "fullDetailRawLineage",
    }
