from __future__ import annotations

from typing import Any

import pandas as pd

from p4.ncs.bands import ncs_band


RQ2B_MART_VERSION = "p4-rq2b-mart-v4.0.0"
CANONICAL_BANDS = ("level1to2", "level3to4", "level5to6", "level7to8")
BAND_DISPLAY_ALIAS = {
    "level1to2": "B1",
    "level3to4": "B2",
    "level5to6": "B3",
    "level7to8": "B4",
}
MAPPING_STATUSES = {"ACCEPTED_SINGLE", "ACCEPTED_MULTI", "ABSTAIN", "UNMAPPED", "OUT_OF_SCOPE"}
ACCEPTED_STATUSES = {"ACCEPTED_SINGLE", "ACCEPTED_MULTI"}
SOURCE_ROLES = {"DUTY", "KNOWLEDGE", "SKILL", "REQUIRED", "PREFERRED", "OTHER"}
GROUP_COLUMNS = ["periodMonth", "jobCohort", "sourceRole"]


def _safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _weighted_median(frame: pd.DataFrame) -> float | None:
    values = frame.loc[frame["ncsLevel"].notna() & frame["mappingWeight"].gt(0), ["ncsLevel", "mappingWeight"]].copy()
    if values.empty:
        return None
    values["ncsLevel"] = pd.to_numeric(values["ncsLevel"])
    values = values.sort_values("ncsLevel")
    cutoff = float(values["mappingWeight"].sum()) / 2.0
    cumulative = values["mappingWeight"].cumsum()
    return float(values.loc[cumulative.ge(cutoff), "ncsLevel"].iloc[0])


def prepare_rq2b_mapping_input(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "periodMonth",
        "jobCohort",
        "sourceRole",
        "trackId",
        "chunkId",
        "ncsEligibleFlag",
        "mappingStatus",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"RQ2-B input missing columns: {missing}")
    result = frame.copy()
    result["sourceRole"] = result["sourceRole"].astype(str).str.upper()
    result["mappingStatus"] = result["mappingStatus"].astype(str).str.upper()
    invalid_roles = sorted(set(result["sourceRole"]) - SOURCE_ROLES)
    invalid_statuses = sorted(set(result["mappingStatus"]) - MAPPING_STATUSES)
    if invalid_roles:
        raise ValueError(f"invalid sourceRole values: {invalid_roles}")
    if invalid_statuses:
        raise ValueError(f"invalid mappingStatus values: {invalid_statuses}")
    result["ncsEligibleFlag"] = result["ncsEligibleFlag"].fillna(False).astype(bool)
    for column in ("ncsUnitCode", "ncsBand", "ncsLevel"):
        if column not in result:
            result[column] = pd.NA
    result["ncsLevel"] = pd.to_numeric(result["ncsLevel"], errors="coerce")
    missing_band = result["ncsBand"].isna() & result["ncsLevel"].notna()
    result.loc[missing_band, "ncsBand"] = result.loc[missing_band, "ncsLevel"].map(
        lambda level: ncs_band(int(level))
    )
    accepted = result["mappingStatus"].isin(ACCEPTED_STATUSES)
    invalid_accepted = accepted & (result["ncsUnitCode"].isna() | result["ncsBand"].isna() | result["ncsLevel"].isna())
    if invalid_accepted.any():
        raise ValueError("accepted mappings require ncsUnitCode, ncsLevel, and canonical ncsBand")
    invalid_bands = sorted(set(result.loc[accepted, "ncsBand"].dropna()) - set(CANONICAL_BANDS))
    if invalid_bands:
        raise ValueError(f"invalid canonical ncsBand values: {invalid_bands}")

    # One record per chunk/unit. Multi-label rows receive deterministic 1/k.
    result = result.sort_values([*GROUP_COLUMNS, "trackId", "chunkId", "ncsUnitCode"], na_position="last")
    result = result.drop_duplicates([*GROUP_COLUMNS, "trackId", "chunkId", "ncsUnitCode", "mappingStatus"])
    accepted_counts = (
        result.loc[accepted]
        .groupby([*GROUP_COLUMNS, "trackId", "chunkId"], dropna=False)["ncsUnitCode"]
        .transform("nunique")
    )
    result["mappingWeight"] = 0.0
    result.loc[result["mappingStatus"].eq("ACCEPTED_SINGLE"), "mappingWeight"] = 1.0
    multi_index = result["mappingStatus"].eq("ACCEPTED_MULTI")
    result.loc[multi_index, "mappingWeight"] = 1.0 / accepted_counts.loc[multi_index].astype(float)
    result["rq2bMartVersion"] = RQ2B_MART_VERSION
    return result.reset_index(drop=True)


def _chunk_statuses(group: pd.DataFrame) -> pd.DataFrame:
    priority = {
        "ACCEPTED_SINGLE": 0,
        "ACCEPTED_MULTI": 1,
        "ABSTAIN": 2,
        "UNMAPPED": 3,
        "OUT_OF_SCOPE": 4,
    }
    chunks = group.loc[group["ncsEligibleFlag"]].copy()
    chunks["_priority"] = chunks["mappingStatus"].map(priority)
    return chunks.sort_values("_priority").drop_duplicates("chunkId")


def _primary_dedup(group: pd.DataFrame) -> pd.DataFrame:
    accepted = group.loc[group["ncsEligibleFlag"] & group["mappingStatus"].isin(ACCEPTED_STATUSES)].copy()
    return accepted.sort_values(["trackId", "ncsUnitCode", "chunkId"]).drop_duplicates(
        ["trackId", "ncsUnitCode"]
    )


def build_mapping_coverage_mart(prepared: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in prepared.groupby(GROUP_COLUMNS, dropna=False, sort=True):
        dimensions = dict(zip(GROUP_COLUMNS, keys))
        chunks = _chunk_statuses(group)
        dedup = _primary_dedup(group)
        eligible = len(chunks)
        accepted_chunks = int(chunks["mappingStatus"].isin(ACCEPTED_STATUSES).sum())
        accepted_weight = float(dedup["mappingWeight"].sum())
        advanced_weight = float(
            dedup.loc[dedup["ncsBand"].isin({"level5to6", "level7to8"}), "mappingWeight"].sum()
        )
        status_counts = chunks["mappingStatus"].value_counts()
        rows.append(
            {
                **dimensions,
                "ncsEligibleChunkCount": eligible,
                "acceptedSingleCount": int(status_counts.get("ACCEPTED_SINGLE", 0)),
                "acceptedMultiCount": int(status_counts.get("ACCEPTED_MULTI", 0)),
                "abstainCount": int(status_counts.get("ABSTAIN", 0)),
                "unmappedCount": int(status_counts.get("UNMAPPED", 0)),
                "outOfScopeCount": int(status_counts.get("OUT_OF_SCOPE", 0)),
                "acceptedMappedChunkCount": accepted_chunks,
                "acceptedMappedWeight": accepted_weight,
                "mappingCoverage": _safe_rate(accepted_chunks, eligible),
                "advancedDutyShareAccepted": _safe_rate(advanced_weight, accepted_weight),
                "advancedDutyShareEligibleLowerBound": _safe_rate(advanced_weight, eligible),
                "ncsLevelWeightedMedian": _weighted_median(dedup),
                "rq2bMartVersion": RQ2B_MART_VERSION,
            }
        )
    return pd.DataFrame(rows).sort_values(GROUP_COLUMNS).reset_index(drop=True)


def build_band_distribution_mart(prepared: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in prepared.groupby(GROUP_COLUMNS, dropna=False, sort=True):
        dimensions = dict(zip(GROUP_COLUMNS, keys))
        chunks = _chunk_statuses(group)
        dedup = _primary_dedup(group)
        accepted_denominator = float(dedup["mappingWeight"].sum())
        eligible_denominator = len(chunks)
        for band in CANONICAL_BANDS:
            weight = float(dedup.loc[dedup["ncsBand"].eq(band), "mappingWeight"].sum())
            rows.append(
                {
                    **dimensions,
                    "distributionCategory": "ACCEPTED_BAND",
                    "ncsBand": band,
                    "ncsBandDisplayAlias": BAND_DISPLAY_ALIAS[band],
                    "acceptedWeight": weight,
                    "eligibleStatusCount": None,
                    "acceptedMappedDenominator": accepted_denominator,
                    "allEligibleDenominator": eligible_denominator,
                    "bandShareAccepted": _safe_rate(weight, accepted_denominator),
                    "bandShareEligibleLowerBound": _safe_rate(weight, eligible_denominator),
                    "rq2bMartVersion": RQ2B_MART_VERSION,
                }
            )
        for status in ("ABSTAIN", "UNMAPPED", "OUT_OF_SCOPE"):
            rows.append(
                {
                    **dimensions,
                    "distributionCategory": "EXCLUDED_STATUS",
                    "ncsBand": status,
                    "ncsBandDisplayAlias": status,
                    "acceptedWeight": 0.0,
                    "eligibleStatusCount": int(chunks["mappingStatus"].eq(status).sum()),
                    "acceptedMappedDenominator": accepted_denominator,
                    "allEligibleDenominator": eligible_denominator,
                    "bandShareAccepted": None,
                    "bandShareEligibleLowerBound": None,
                    "rq2bMartVersion": RQ2B_MART_VERSION,
                }
            )
    return pd.DataFrame(rows).sort_values([*GROUP_COLUMNS, "distributionCategory", "ncsBand"]).reset_index(drop=True)


def build_unit_mention_intensity_mart(prepared: pd.DataFrame) -> pd.DataFrame:
    accepted = prepared.loc[
        prepared["ncsEligibleFlag"] & prepared["mappingStatus"].isin(ACCEPTED_STATUSES)
    ].copy()
    if accepted.empty:
        return pd.DataFrame(
            columns=[*GROUP_COLUMNS, "trackId", "ncsUnitCode", "unitMentionIntensity", "rq2bMartVersion"]
        )
    result = (
        accepted.groupby([*GROUP_COLUMNS, "trackId", "ncsUnitCode"], dropna=False)["chunkId"]
        .nunique()
        .rename("unitMentionIntensity")
        .reset_index()
    )
    result["rq2bMartVersion"] = RQ2B_MART_VERSION
    return result.sort_values([*GROUP_COLUMNS, "trackId", "ncsUnitCode"]).reset_index(drop=True)


def build_rq2b_marts(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    prepared = prepare_rq2b_mapping_input(frame)
    return {
        "prepared": prepared,
        "mapping_coverage": build_mapping_coverage_mart(prepared),
        "band_distribution": build_band_distribution_mart(prepared),
        "unit_mention_intensity": build_unit_mention_intensity_mart(prepared),
    }
