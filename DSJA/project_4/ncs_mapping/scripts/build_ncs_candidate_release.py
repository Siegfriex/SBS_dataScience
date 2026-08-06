#!/usr/bin/env python3
"""Build only a compact NCS v4 candidate manifest; never duplicate the corpus."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

NCS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NCS_ROOT / "src"))

from p4_ncs.corpus.release import build_candidate_release_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="ncs-candidate-2026-02-20-v4.0")
    args = parser.parse_args()
    source = NCS_ROOT / "data" / "processed" / "ncsUnit.parquet"
    manifest = build_candidate_release_manifest(
        pd.read_parquet(source), ncs_corpus_version=args.version, normalized_path=source
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
