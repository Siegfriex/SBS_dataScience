from __future__ import annotations

import ast
import json
from pathlib import Path


CRAWL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = CRAWL_ROOT / "scripts/build_tier1_preapproval.py"
REPORT_ROOT = CRAWL_ROOT / "reports/tier1_preapproval"


def test_preapproval_builder_has_no_network_transport_import() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"requests", "httpx", "aiohttp", "urllib", "playwright", "selenium"})


def test_scope_proposal_is_not_an_approval_and_network_is_zero() -> None:
    proposal = json.loads((REPORT_ROOT / "P4_TIER1_SCOPE_PROPOSAL.json").read_text(encoding="utf-8"))
    assert proposal["proposalStatus"] == "PROPOSED_NOT_APPROVED"
    assert proposal["logicalRequestType"] == "INDEX"
    assert proposal["networkCalls"] == 0
    assert proposal["detailRequestCount"] == 0
    assert proposal["assetRequestCount"] == 0
    assert proposal["externalAtsTransportAllowed"] is False
    assert proposal["browserAutomationAllowed"] is False
    assert proposal["tier0CanonicalHandoffManifestSha256"] == "6162d3aea6ff3646d4d9cb7ff09d09acf91bbde81a815896096bca82b6f63c42"
    assert not any(key.startswith("approved") for key in proposal)


def test_exact_eleven_preapproval_artifacts_and_checksums() -> None:
    files = sorted(path.name for path in REPORT_ROOT.iterdir() if path.is_file())
    assert len(files) == 11
    assert "EVIDENCE_MANIFEST.sha256" in files
    lines = (REPORT_ROOT / "EVIDENCE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    for line in lines:
        expected, name = line.split(None, 1)
        import hashlib
        assert hashlib.sha256((REPORT_ROOT / name.strip()).read_bytes()).hexdigest() == expected


def test_source_authority_bindings_are_exact() -> None:
    expected_tier0 = "6162d3aea6ff3646d4d9cb7ff09d09acf91bbde81a815896096bca82b6f63c42"
    expected_source = "13205c11e7de3dfc7b005b0fde16197281eb857f"
    for name in (
        "P4_TIER1_SCOPE_PROPOSAL.json",
        "P4_TIER1_REQUEST_ESTIMATE.json",
        "P4_TIER1_STORAGE_ESTIMATE.json",
    ):
        payload = json.loads((REPORT_ROOT / name).read_text(encoding="utf-8"))
        assert payload["tier0ChecksumManifestSha256"] == expected_tier0
        assert payload["tier0CanonicalHandoffManifestSha256"] == expected_tier0
        assert payload["a1SourceCommit"] == expected_source
    schema = json.loads((REPORT_ROOT / "P4_TIER1_EMPTY_HANDOFF_SCHEMA.json").read_text(encoding="utf-8"))
    assert schema["x-p4-binding"]["tier0ChecksumManifestSha256"] == expected_tier0
    assert schema["x-p4-binding"]["tier0CanonicalHandoffManifestSha256"] == expected_tier0
    assert schema["x-p4-binding"]["a1SourceCommit"] == expected_source
    assert schema["properties"]["approvalId"]["const"] == "NONE"
    assert "status" in schema["required"]
