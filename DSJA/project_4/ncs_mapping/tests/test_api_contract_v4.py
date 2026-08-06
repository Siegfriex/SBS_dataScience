import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from p4_ncs.api.client import MinimalProbeClient
from p4_ncs.api.parsers import parse_fixture_document
from p4_ncs.api.redaction import REDACTED, assert_no_secret_value, redacted_request_manifest
from p4_ncs.api.registry import load_api_registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "ncs_mapping" / "data" / "raw" / "api_fixtures"
SCHEMA_ROOT = PROJECT_ROOT / "shared" / "contracts" / "semantic_ncs_reference" / "v4.0" / "schemas"


def _fixture(provider: str, name: str):
    return json.loads((FIXTURE_ROOT / provider / f"{name}.json").read_text(encoding="utf-8"))


def test_registry_is_read_only_authority_with_six_unique_endpoints():
    registry = load_api_registry()
    assert len(registry.endpoints) == 6
    assert len({row.api_contract_id for row in registry.endpoints}) == 6
    assert all(row.url.startswith("https://") for row in registry.endpoints)
    assert {row.provider for row in registry.endpoints} == {"NCS_OPENAPI", "WORK24"}


def test_registry_records_validate_against_agent3_schema():
    schema = json.loads((SCHEMA_ROOT / "api_endpoint_contract.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for endpoint in load_api_registry().endpoints:
        validator.validate(endpoint.as_contract_record(valid_from="2026-08-06T00:00:00Z", parser_version="offline-v4.0"))


def test_request_manifest_redacts_and_hashes_without_secret():
    secret = "do-not-log-this-key"
    manifest = redacted_request_manifest(
        api_contract_id="TEST", method="GET", url="https://example.test/api",
        parameters={"serviceKey": secret, "word": "데이터", "nested": {"authToken": secret}},
    )
    assert manifest["parameters"]["serviceKey"] == REDACTED
    assert manifest["parameters"]["nested"]["authToken"] == REDACTED
    assert len(manifest["requestSha256"]) == 64
    assert_no_secret_value(manifest, [secret])


@pytest.mark.parametrize("provider,name,expected", [
    ("ncs", "success", "SUCCESS"),
    ("ncs", "empty", "EMPTY_VALID"),
    ("ncs", "auth_error", "AUTH_ERROR"),
    ("ncs", "param_error", "PARAM_ERROR"),
    ("work24", "success", "SUCCESS"),
    ("work24", "empty", "EMPTY_VALID"),
    ("work24", "auth_error", "AUTH_ERROR"),
    ("work24", "param_error", "PARAM_ERROR"),
])
def test_synthetic_contract_fixture_classes(provider, name, expected):
    document = _fixture(provider, name)
    assert document["sourceClass"] == "SYNTHETIC_CONTRACT_FIXTURE"
    parsed = parse_fixture_document(document)
    assert parsed.response_class == expected
    assert len(parsed.observed_schema_sha256) == 64


def test_success_fixtures_expose_expected_records_and_paging():
    ncs = parse_fixture_document(_fixture("ncs", "success"))
    work24 = parse_fixture_document(_fixture("work24", "success"))
    assert ncs.total_count == work24.total_count == 1
    assert ncs.page_no == work24.page_no == 1
    assert ncs.records[0]["ncsCompeUnitCd"] == "2001070101_20v1"
    assert work24.records[0]["ablt_unit"] == "2001070101_20v1"


def test_default_probe_never_calls_network_and_is_not_evaluated(monkeypatch):
    monkeypatch.delenv("NCS_API_SERVICE_KEY", raising=False)
    endpoint = load_api_registry().by_id("NCS-ncsCdInfo-v4.0")
    outcome = MinimalProbeClient().probe(
        endpoint, probe_case="SUCCESS_MINIMAL", parameters={"pageNo": 1, "numOfRows": 1}
    )
    assert outcome.parsed is None
    assert outcome.manifest["status"] == "NOT_EVALUATED"
    assert outcome.manifest["responseClass"] == "AUTH_ERROR"
    schema = json.loads((SCHEMA_ROOT / "api_probe_run.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(outcome.manifest)


def test_network_opt_in_without_explicit_transport_fails_closed():
    endpoint = load_api_registry().by_id("NCS-ncsCdInfo-v4.0")
    with pytest.raises(RuntimeError, match="explicit audited transport"):
        MinimalProbeClient(network_enabled=True).probe(
            endpoint, probe_case="SUCCESS_MINIMAL", parameters={}, credential="runtime-only"
        )
