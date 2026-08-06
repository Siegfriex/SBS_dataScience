from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from p4.contracts.loader import assess_crawl_release  # noqa: E402
from p4.normalize.linkareer import adapt_linkareer_source  # noqa: E402
from p4.parse.linkareer_apollo_cache import parse_masked_ssr_fixture  # noqa: E402
from p4.parse.linkareer_apq import parse_apq_entries  # noqa: E402


def _masked(value) -> bool:
    if isinstance(value, dict):
        return all(_masked(item) for item in value.values())
    if isinstance(value, list):
        return all(_masked(item) for item in value)
    return value == "[MASKED]" or value is None


def run(release_root: Path, fixture_release_root: Path | None = None) -> dict[str, object]:
    release_root = release_root.resolve()
    acceptance = assess_crawl_release(release_root / "HANDOFF.json")
    fixture_release_root = (fixture_release_root or release_root).resolve()
    apq_paths = sorted((fixture_release_root / "fixtures/apq").glob("*.json"))
    ssr_paths = sorted((fixture_release_root / "fixtures/ssr").glob("*.json"))
    if len(apq_paths) != 1 or len(ssr_paths) != 3:
        raise ValueError(f"expected one APQ and three SSR fixtures, found {len(apq_paths)} and {len(ssr_paths)}")

    apq_payload = json.loads(apq_paths[0].read_text(encoding="utf-8"))
    apq_rows = parse_apq_entries(apq_payload)
    if not apq_rows:
        raise ValueError("APQ fixture produced no entries")
    apq_checks = {
        "fixtureCount": 1,
        "entryCount": len(apq_rows),
        "activityTypeIdPresent": all(row.get("activityTypeId") is not None for row in apq_rows),
        "jobTypesRawJsonPresent": all(bool(row.get("jobTypesRawJson")) for row in apq_rows),
        "managerPiiMasked": all(_masked(row.get("managerMasked")) for row in apq_rows),
    }

    ssr_results = []
    for path in ssr_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        activity = payload.get("activityData") or {}
        detail = parse_masked_ssr_fixture(payload)
        index = parse_apq_entries({"entries": [activity]})[0]
        adapted = adapt_linkareer_source(index, detail)
        ssr_results.append(
            {
                "sourcePostingId": adapted["sourcePostingId"],
                "activityTypeId": adapted["activityTypeId"],
                "jobTypesRawJsonPresent": bool(adapted["jobTypesRawJson"]),
                "dutiesRawJsonPresent": bool(adapted["dutiesRawJson"]),
                "dutiesCount": len(json.loads(adapted["dutiesRawJson"])),
                "activityTextExtracted": bool(adapted["activityTextHtml"]),
                "activityTextAvailableFlag": adapted["activityTextAvailableFlag"],
                "externalApplyFlag": adapted["externalApplyFlag"],
                "externalDetailOnlyFlag": adapted["externalDetailOnlyFlag"],
                "externalAtsDomain": adapted["externalAtsDomain"],
                "jobTypeConflictFlag": adapted["jobTypeConflictFlag"],
                "reviewFlag": adapted["reviewFlag"],
                "managerPiiMasked": _masked(detail["managerMasked"]),
                "embeddedImageCount": len(adapted["embeddedImageUrls"]),
                "ocrRoutingRequiredFlag": adapted["ocrRoutingRequiredFlag"],
                "ocrQueueCount": len(adapted["ocrQueue"]),
                "postingEligibleFlag": adapted["postingEligibleFlag"],
                "rq1EligibleFlag": adapted["rq1EligibleFlag"],
                "rq2EligibleFlag": adapted["rq2EligibleFlag"],
                "ncsEligibleFlag": adapted["ncsEligibleFlag"],
                "rq2ExclusionReason": adapted["rq2ExclusionReason"],
            }
        )

    sample_path = release_root / "stratified_detail_sample_n126.json"
    samples = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.is_file() else []
    sample_rates = {
        field: (sum(bool(row.get(field)) for row in samples) / len(samples) if samples else None)
        for field in (
            "hasActivityText",
            "externalApplyFlag",
            "externalDetailOnlyFlag",
            "rq1EligibleFlag",
            "rq2EligibleFlag",
            "ncsEligibleFlag",
            "jobTypeConflictFlag",
            "activityTextEmbeddedImageFlag",
            "hasPosterFile",
        )
    }
    coverage_counts: dict[str, int] = {}
    target_coverage_counts: dict[str, int] = {}
    complete_distinct_postings = 0
    coverage_path = release_root / "monthly_coverage.csv"
    if coverage_path.is_file():
        with coverage_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                status = str(row.get("coverageStatus") or "missing")
                coverage_counts[status] = coverage_counts.get(status, 0) + 1
                period = str(row.get("periodMonth") or "")[:7]
                if "2020-01" <= period <= "2026-07":
                    target_coverage_counts[status] = target_coverage_counts.get(status, 0) + 1
                    if status == "complete":
                        complete_distinct_postings += int(float(row.get("returnedDistinctCount") or 0))
    ncs_records = None
    ncs_manifest = release_root / "ncs_manifest.jsonl"
    if ncs_manifest.is_file():
        for line in ncs_manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item.get("datasetId") == "15083321":
                    ncs_records = item.get("recordCount")

    result = {
        "agentId": "P4-A2-PIPELINE",
        "agentName": "P4 Contract-Driven Pipeline & Analysis Engineer",
        "contractVersion": "2.1.2",
        "crawlReleaseId": acceptance["releaseId"],
        "adapterFixtureReleaseId": fixture_release_root.name,
        "dataProvenance": "PARTIAL_CONFORMANCE_ONLY",
        "empiricalAnalysisAllowed": False,
        "sourceAdapterConformanceStatus": acceptance["sourceAdapterConformanceStatus"],
        "empiricalCorpusStatus": acceptance["empiricalCorpusStatus"],
        "empiricalRejectionReasons": acceptance["empiricalRejectionReasons"],
        "detailRawPerRecordLineageVerified": acceptance["detailRawPerRecordLineageVerified"],
        "releaseChecksumCount": acceptance["checksumCount"],
        "releaseChecksumPassed": acceptance["checksumPassed"],
        "apq": apq_checks,
        "ssrFixtureCount": len(ssr_results),
        "ssr": ssr_results,
        "stratifiedSample": {"rows": len(samples), "rates": sample_rates},
        "monthlyCoverageStatusCounts": coverage_counts,
        "targetCoverageStatusCounts": target_coverage_counts,
        "completeMonthDistinctPostingCount": complete_distinct_postings,
        "detailSampleSuccessCount": len(samples),
        "detailSampleFailureCount": 0,
        "ncsUnitRecordCount": ncs_records,
        "qualityChecks": {
            "allManagersMasked": apq_checks["managerPiiMasked"] and all(row["managerPiiMasked"] for row in ssr_results),
            "allActivityTextExtracted": all(row["activityTextExtracted"] for row in ssr_results),
            "embeddedImageObserved": any(row["embeddedImageCount"] > 0 for row in ssr_results),
            "ocrRouteObserved": any(row["ocrRoutingRequiredFlag"] for row in ssr_results),
            "nonRecruitExcluded": all(
                not row["postingEligibleFlag"] for row in ssr_results if str(row["activityTypeId"]) != "5"
            ),
        },
    }
    output = PIPELINE_ROOT / "reports/agent2/PARTIAL_CRAWL_CONFORMANCE.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--fixture-release-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.release_root, args.fixture_release_root), ensure_ascii=False, indent=2))
