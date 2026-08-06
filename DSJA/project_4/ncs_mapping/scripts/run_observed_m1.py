"""CLI for the Agent 4 observed-development lexical baseline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p4_ncs.workflow.observed import STAGES, run_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["all", *STAGES], default="all")
    parser.add_argument("--duty-input", type=Path)
    parser.add_argument("--gold-input", type=Path)
    parser.add_argument("--schema-dir", type=Path)
    args = parser.parse_args()
    stages = list(STAGES) if args.stage == "all" else [args.stage]
    manifests = [
        run_stage(
            stage,
            root=ROOT,
            duty_input_path=args.duty_input,
            gold_input_path=args.gold_input,
            schema_dir=args.schema_dir,
        )
        for stage in stages
    ]
    print(json.dumps([
        {"stageId": item["stageId"], "status": item["status"], "rowCounts": item["rowCounts"]}
        for item in manifests
    ], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
