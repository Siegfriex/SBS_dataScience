from pathlib import Path

from p4.contracts.duty_input import validate_duty_input_handoff


def test_agent4_duty_input_handoff_schema_and_fixture():
    path = Path(__file__).resolve().parents[3] / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT.json"
    payload = validate_duty_input_handoff(path)
    assert payload["status"] == "SCHEMA_AND_FIXTURE_ONLY"
    assert payload["empiricalUseAllowed"] is False
    assert payload["grain"] == "one row per core.postingSection where sectionType=duty"
    assert payload["fixtureRows"][0]["dataProvenance"] == "SYNTHETIC"
