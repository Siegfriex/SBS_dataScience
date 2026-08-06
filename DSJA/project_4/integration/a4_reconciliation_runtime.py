"""Read-only A4 stage runners used by the unified reconciliation wrapper."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pandas as pd


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_a4_stage(project: Path, stage_id: str) -> dict[str, Any]:
    """Execute exactly one deterministic A4 check without mutating corpus bytes."""
    sys.path[:0] = [str(project / "ncs_mapping/src"), str(project / "pipeline/src")]
    ncs = project / "ncs_mapping"
    units_path = ncs / "data/processed/ncsUnit.parquet"
    codes_path = ncs / "data/processed/coreAiItCodeSet.parquet"
    alias_path = ncs / "configs/ncs_alias_dictionary.yaml"
    duty_path = project / "shared/handoffs/AGENT2_TO_AGENT4_DUTY_INPUT_OBSERVED_DEV.json"
    compat_path = project / "shared/handoffs/AGENT4_TO_AGENT2_NCS_MAPPING_OBSERVED_DEV.json"
    mart_path = ncs / "reports/reconciliation_a4/A4_MAPPING_TO_MART_CONTRACT.json"
    gold_path = ncs / "data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv"

    if stage_id == "A4-00-NCS-SOURCE":
        units = pd.read_parquet(units_path)
        passed = (
            len(units) == 13_442
            and not units.ncsUnitCode.duplicated().any()
            and units.ncsLevel.between(1, 8).all()
        )
        if not passed:
            raise ValueError("A4 NCS source integrity failed")
        return {"input": sha_file(units_path), "rows": len(units), "status": "SUCCEEDED"}

    if stage_id == "A4-01-CODESET":
        from p4_ncs.codeset.core_ai_it import build_core_ai_it_codeset

        units = pd.read_parquet(units_path)
        codes = pd.read_parquet(codes_path)
        rebuilt = build_core_ai_it_codeset(units).sort_values("ncsSubCode").reset_index(drop=True)
        pd.testing.assert_frame_equal(
            rebuilt,
            codes.sort_values("ncsSubCode").reset_index(drop=True),
            check_dtype=False,
        )
        return {
            "input": sha_file(codes_path), "rows": len(codes),
            "included": int(codes.included.sum()), "status": "SUCCEEDED",
        }

    if stage_id == "A4-02-RETRIEVAL":
        from p4_ncs.dictionary.alias_dictionary import load_alias_dictionary, validate_alias_dictionary
        from p4_ncs.retrieval.lexical_index import LexicalIndex

        units = pd.read_parquet(units_path)
        codes = pd.read_parquet(codes_path)
        aliases = load_alias_dictionary(alias_path)
        index = LexicalIndex.build(units, codes)
        bad_aliases = validate_alias_dictionary(aliases, set(codes.ncsSubCode.astype(str)))
        if bad_aliases:
            raise ValueError(f"invalid A4 aliases: {bad_aliases}")
        return {
            "input": sha_file(alias_path), "rows": len(index.documents),
            "aliasRows": len(aliases), "status": "SUCCEEDED",
        }

    if stage_id == "A4-03-MAP-OBSERVED":
        from p4.contracts.ncs_handoff import validate_agent4_ncs_handoff

        compat = validate_agent4_ncs_handoff(compat_path, project)
        return {
            "input": sha_file(duty_path), "rows": compat["matchRows"],
            "candidateRows": compat["candidateRows"], "status": "SUCCEEDED",
        }

    if stage_id == "A4-04-EXPORT":
        from p4.contracts.ncs_mart_handoff import load_ncs_mart_handoff

        mart, payload = load_ncs_mart_handoff(mart_path)
        if len(mart) != 28 or payload["humanGoldRows"] != 0:
            raise ValueError("A4 structural mart boundary failed")
        return {
            "input": sha_file(compat_path), "rows": len(mart),
            "structuralRows": int(mart.mappingStatus.eq("REVIEW_REQUIRED").sum()),
            "status": "SUCCEEDED",
        }

    if stage_id == "A4-05-EVALUATE":
        from p4_ncs.evaluation.gold_evaluation import evaluate_gold_mapping, load_gold_structure

        gold = evaluate_gold_mapping(load_gold_structure(gold_path))
        if gold.goldRows != 0 or gold.gateStatus != "NOT_EVALUATED":
            raise ValueError("empty Gold must remain NOT_EVALUATED")
        return {
            "input": sha_file(gold_path), "rows": gold.goldRows,
            "goldAuthority": "NONE", "status": "NOT_EVALUATED",
        }

    raise KeyError(f"unknown A4 stage: {stage_id}")
