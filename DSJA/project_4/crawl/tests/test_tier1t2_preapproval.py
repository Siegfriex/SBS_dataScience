from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


CRAWL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = CRAWL_ROOT / "scripts/build_tier1t2_preapproval.py"
REPORT_ROOT = CRAWL_ROOT / "reports/tier1t2_preapproval"


def test_generator_has_no_network_or_dotenv_access() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"requests", "httpx", "aiohttp", "urllib3", "playwright", "selenium", "dotenv"})
    assert ".env" not in source


def test_detail_sample_is_not_materialized_before_discovery() -> None:
    contract = json.loads((REPORT_ROOT / "P4_TIER2_DETAIL_SAMPLE_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["contractStatus"] == "NOT_EVALUATED_AWAITING_TIER1_DISCOVERY"
    assert contract["postingIds"] == []
    assert contract["sampleSize"] == 10
    assert contract["replacement"] is False
    assert contract["terminalFailureReplacementAllowed"] is False
    assert contract["samplingSeedExpression"] == "SHA256(tier1CanaryRunId+tier1DiscoveryManifestSha256+approvedScopeHash)"


def test_asset_request_proposal_is_evidence_bounded() -> None:
    estimate = json.loads((REPORT_ROOT / "P4_TIER3_ASSET_REQUEST_ESTIMATE.json").read_text(encoding="utf-8"))
    assert estimate["evidencePostingRows"] == 137
    assert estimate["evidenceAssetCandidateRows"] == 59
    assert estimate["observedAssetCandidatesPerPostingMaximum"] == 3
    assert estimate["proposedMaxAssetRequests"] == 30
    assert estimate["externalAtsCandidateRows"] == 0
    assert estimate["assetsFetchedEvidenceRows"] == 0
    assert estimate["assetByteEstimateStatus"].startswith("NOT_EVALUATED")


def test_eight_artifacts_and_checksums() -> None:
    files = sorted(path.name for path in REPORT_ROOT.iterdir() if path.is_file())
    assert len(files) == 8
    lines = (REPORT_ROOT / "EVIDENCE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7
    for line in lines:
        expected, name = line.split(None, 1)
        assert hashlib.sha256((REPORT_ROOT / name.strip()).read_bytes()).hexdigest() == expected


def test_no_actual_approval_values_or_calls() -> None:
    scope = json.loads((REPORT_ROOT / "P4_TIER1T2_SCOPE_PROPOSAL.json").read_text(encoding="utf-8"))
    assert scope["proposalStatus"] == "PROPOSED_NOT_APPROVED"
    assert scope["networkCalls"] == 0
    assert scope["detailCalls"] == 0
    assert scope["assetCalls"] == 0
    assert scope["externalAtsTransportCalls"] == 0
    assert scope["browserAutomationCalls"] == 0
    assert scope["credentialedApiCalls"] == 0
