from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.common.hashing import canonical_json_sha256  # noqa: E402
from p4.common.keys import make_section_id  # noqa: E402
from p4.contracts.loader import contract_bundle_status, find_crawl_releases  # noqa: E402
from p4.dedup.reposts import assign_repost_groups  # noqa: E402
from p4.label.career import LabelEvidence, label_track  # noqa: E402
from p4.marts.posting import build_posting_analysis_mart, validate_posting_analysis_mart  # noqa: E402
from p4.marts.time_series import build_time_series_mart  # noqa: E402
from p4.ncs.mapping import rank_candidates  # noqa: E402
from p4.normalize.postings import normalize_postings  # noqa: E402
from p4.normalize.tracks import split_tracks  # noqa: E402
from p4.parse.requirements import extract_requirements  # noqa: E402
from p4.quality.manifest import artifact_record  # noqa: E402
from p4.warehouse.bootstrap import bootstrap_development_warehouse  # noqa: E402
from p4.warehouse.connection import connect  # noqa: E402
from p4.warehouse.integrity import primary_key_duplicates  # noqa: E402
from p4.warehouse.loaders import replace_from_frame  # noqa: E402


def run() -> dict[str, object]:
    fixture_path = PIPELINE_ROOT / "tests/fixtures/generated_structural_fixture.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw = pd.DataFrame(payload["rawPostings"])
    raw["fetchedAt"] = pd.to_datetime(raw["fetchedAt"], utc=True)
    postings = assign_repost_groups(normalize_postings(raw))

    track_rows: list[dict[str, object]] = []
    section_rows: list[dict[str, object]] = []
    requirement_rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []
    match_rows: list[dict[str, object]] = []

    for source_id, track_specs in payload["tracks"].items():
        posting = postings.loc[postings["sourcePostingId"] == source_id].iloc[0].to_dict()
        tracks = split_tracks(posting, track_specs)
        for track, spec in zip(tracks, track_specs):
            track_rows.append(track)
            label_rows.append(label_track(track["trackId"], LabelEvidence(**spec["labelEvidence"])))
            duty_section_id = None
            for ordinal, section_spec in enumerate(spec.get("sections", [])):
                section_id = make_section_id(track["trackId"], ordinal)
                section = {
                    "sectionId": section_id,
                    "trackId": track["trackId"],
                    "sectionType": section_spec["sectionType"],
                    "sectionOrdinal": ordinal,
                    "sectionText": section_spec["text"],
                    "boundaryResolvedFlag": spec["labelEvidence"]["boundary_resolved"],
                }
                section_rows.append(section)
                requirement_rows.extend(extract_requirements(section))
                if section_spec["sectionType"] == "duty":
                    duty_section_id = section_id
            if spec.get("ncsUnitCode") and duty_section_id:
                ranked = rank_candidates(
                    track["trackId"],
                    duty_section_id,
                    [
                        {
                            "ncsUnitCode": spec["ncsUnitCode"],
                            "evidenceText": next(
                                item["text"] for item in spec["sections"] if item["sectionType"] == "duty"
                            ),
                            "mappingBasis": spec["mappingBasis"],
                            "matchScore": spec["matchScore"],
                        }
                    ],
                    "fixture-map-v1",
                )
                for match in ranked:
                    match["trackId"] = track["trackId"]
                    match_rows.append(match)

    tracks = pd.DataFrame(track_rows)
    sections = pd.DataFrame(section_rows)
    requirements = pd.DataFrame(requirement_rows)
    labels = pd.DataFrame(label_rows)
    matches = pd.DataFrame(match_rows)
    units = pd.DataFrame(payload["ncsUnits"])
    lineage = {
        "contractVersion": "2.1.2",
        "crawlReleaseId": "NONE",
        "dataVersion": payload["fixtureVersion"],
        "parseVersion": "fixture-parse-v2",
        "labelVersion": "fixture-label-v2",
        "ncsMapVersion": "fixture-ncs-v2",
        "dedupVersion": "fixture-dedup-v2",
    }
    posting_mart = build_posting_analysis_mart(
        postings, tracks, labels, matches, units, lineage=lineage
    )
    time_series = build_time_series_mart(posting_mart)

    marts_dir = PIPELINE_ROOT / "data/marts"
    marts_dir.mkdir(parents=True, exist_ok=True)
    posting_path = marts_dir / "postingAnalysisMart.parquet"
    time_path = marts_dir / "timeSeriesMart.parquet"
    posting_mart.to_parquet(posting_path, index=False)
    time_series.to_parquet(time_path, index=False)

    database = PIPELINE_ROOT / "data/warehouse/p4.development.duckdb"
    bootstrap_development_warehouse(database)
    raw_columns = [
        "rawPostingId", "sourcePostingId", "sourceUrl", "fetchedAt", "rawSha256",
        "titleRaw", "companyRaw", "postedAtRaw", "bodyRaw", "postingKind",
    ]
    with connect(database) as connection:
        replace_from_frame(connection, "raw.linkareer_posting", raw[raw_columns])
        replace_from_frame(connection, "core.posting_normalized", postings)
        replace_from_frame(connection, "core.posting_track", tracks.drop(columns=["trackText"]))
        replace_from_frame(connection, "core.posting_section", sections)
        # The development fixture warehouse keeps the legacy v2.1.2 physical
        # projection. Semantic v4.0 fields remain in the in-memory/output frame
        # and are materialized by the addendum pipeline, not silently added to
        # the legacy table.
        legacy_requirement_columns = [
            "requirementId",
            "sectionId",
            "requirementType",
            "requirementText",
            "mandatoryFlag",
            "minExperienceMonths",
            "priorExperienceFlag",
            "portfolioFlag",
        ]
        replace_from_frame(
            connection,
            "core.requirement_fact",
            requirements[legacy_requirement_columns],
        )
        replace_from_frame(connection, "core.career_label", labels)
        replace_from_frame(connection, "ncs.ncs_unit", units)
        replace_from_frame(connection, "ncs.posting_ncs_match", matches.drop(columns=["trackId"]))
        replace_from_frame(connection, "mart.posting_analysis", posting_mart)
        replace_from_frame(connection, "mart.time_series", time_series)
        warehouse_checks = {
            "postingMartPkDuplicates": primary_key_duplicates(connection, "mart.posting_analysis", ["trackId"]),
            "timeSeriesPkDuplicates": primary_key_duplicates(connection, "mart.time_series", ["metricId"]),
        }

    artifact_manifest = [
        artifact_record(posting_path, "development-fixture-v1", len(posting_mart)),
        artifact_record(time_path, "development-fixture-v1", len(time_series)),
        artifact_record(database, "development-fixture-v1", 0),
    ]
    for artifact in artifact_manifest:
        artifact["path"] = str(Path(artifact["path"]).relative_to(PIPELINE_ROOT))
    summary = {
        "status": "FIXTURE_PIPELINE_READY",
        "dataProvenance": payload["fixtureType"],
        "dataVersion": payload["fixtureVersion"],
        "empiricalAnalysisAllowed": False,
        "contract": contract_bundle_status(PIPELINE_ROOT.parent / "shared/contracts/P4_CONTRACT_v2.1.2"),
        "crawlReleaseCount": len(find_crawl_releases(PIPELINE_ROOT.parent)),
        "rows": {
            "raw": len(raw),
            "normalized": len(postings),
            "tracks": len(tracks),
            "sections": len(sections),
            "requirements": len(requirements),
            "labels": len(labels),
            "ncsUnits": len(units),
            "ncsMatches": len(matches),
            "postingAnalysisMart": len(posting_mart),
            "timeSeriesMart": len(time_series),
            "excludedPostings": int((~postings["postingEligibleFlag"]).sum()),
        },
        "postingMartQuality": validate_posting_analysis_mart(posting_mart),
        "warehouseChecks": warehouse_checks,
        "artifactManifest": artifact_manifest,
        "fixtureSha256": canonical_json_sha256(payload),
    }
    runs_dir = PIPELINE_ROOT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "fixture_pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
