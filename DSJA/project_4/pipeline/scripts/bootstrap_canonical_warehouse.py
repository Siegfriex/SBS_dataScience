from __future__ import annotations

import json
import sys
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.common.hashing import sha256_file  # noqa: E402
from p4.contracts.validators import audit_contract_bundle  # noqa: E402
from p4.warehouse.bootstrap import bootstrap_canonical_warehouse  # noqa: E402


def run() -> dict[str, object]:
    bundle = PROJECT_ROOT / "shared/contracts/P4_CONTRACT_v2.1.2"
    database = PIPELINE_ROOT / "data/warehouse/p4.duckdb"
    contract = audit_contract_bundle(bundle)
    warehouse = bootstrap_canonical_warehouse(database, bundle / "warehouse_duckdb.sql")
    result = {
        "agentId": "P4-A2-PIPELINE",
        "agentName": "P4 Contract-Driven Pipeline & Analysis Engineer",
        "status": "CONTRACT_LINKED",
        "contractVersion": contract["contractVersion"],
        "contractSha256": contract["contractSha256"],
        "ddlSha256": contract["ddlSha256"],
        "databasePath": "data/warehouse/p4.duckdb",
        "databaseSha256": sha256_file(database),
        "warehouse": warehouse,
    }
    runs = PIPELINE_ROOT / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "canonical_warehouse_bootstrap.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
