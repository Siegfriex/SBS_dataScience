from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_canary_handoff.py"
SPEC = importlib.util.spec_from_file_location("publish_canary_handoff", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_empty_envelope_is_nonempty_and_bound() -> None:
    value = MODULE.empty_envelope("CANARY_TEST", "REQUEST_ATTEMPT")
    assert value == {
        "recordType": "EMPTY_ARTIFACT",
        "artifactType": "REQUEST_ATTEMPT",
        "runId": "CANARY_TEST",
        "schemaVersion": "p4-canary-handoff-v1",
        "emptyReason": "NETWORK_NOT_AUTHORIZED",
        "rowCount": 0,
    }


def test_redacted_tree_rejects_absolute_path(tmp_path: Path) -> None:
    for name in MODULE.HANDOFF_NAMES:
        (tmp_path / name).write_text("safe\n", encoding="utf-8")
    (tmp_path / "canary_plan.json").write_text('{"path":"/home/example/raw"}\n', encoding="utf-8")
    try:
        MODULE.validate_redacted_tree(tmp_path)
    except ValueError as exc:
        assert "absolute=1" in str(exc)
    else:
        raise AssertionError("absolute path must fail closed")


def test_redacted_tree_accepts_complete_safe_tree(tmp_path: Path) -> None:
    for name in MODULE.HANDOFF_NAMES:
        (tmp_path / name).write_text("safe\n", encoding="utf-8")
    observed = MODULE.validate_redacted_tree(tmp_path)
    assert observed == {"files": 16, "absolutePathHits": 0, "secretHits": 0, "zeroByteFiles": 0}
