from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
CONTRACT_VERSION = "2.1.2"
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.contracts.loader import assess_crawl_release, validate_crawl_release  # noqa: E402
from p4.contracts.validators import audit_contract_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a full P4 crawl release before empirical loading.")
    parser.add_argument("--handoff", required=True, type=Path)
    args = parser.parse_args()

    contract = audit_contract_bundle(PROJECT_ROOT / "shared/contracts/P4_CONTRACT_v2.1.2")
    release = validate_crawl_release(args.handoff, expected_contract_version=CONTRACT_VERSION)
    assessment = assess_crawl_release(args.handoff, expected_contract_version=CONTRACT_VERSION)
    result = {
        "contractVersion": contract["contractVersion"],
        "contractChecksumsPassed": contract["checksums"]["passed"],
        "releaseId": release["release"].release_id,
        "releaseChecksumsVerified": release["checksumCount"],
        "rawLineageVerified": release["rawLineageVerified"],
        **assessment,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if assessment["empiricalCorpusStatus"] != "EMPIRICAL_CORPUS_ACCEPTED":
        raise SystemExit("full crawl release rejected; empirical pipeline remains blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
