import pytest

from p4.quality.provenance import DataProvenance, ProvenanceContext, require_production_provenance


def test_only_canonical_crawl_release_allows_empirical_analysis():
    real = ProvenanceContext(DataProvenance.EMPIRICAL, "2.1.2", "CRAWL_20260806_01", "20260806.1")
    assert real.empirical_analysis_allowed is True
    real.require_empirical()


@pytest.mark.parametrize(
    "context",
    [
        ProvenanceContext(DataProvenance.GENERATED_STRUCTURAL_FIXTURE, None, None, "fixture-v1"),
        ProvenanceContext(DataProvenance.CRAWL_RELEASE, None, "CRAWL_1", "v1"),
        ProvenanceContext(DataProvenance.CRAWL_RELEASE, "2.1.2", "RECON_1", "v1"),
        ProvenanceContext(DataProvenance.CRAWL_RELEASE, "2.1.2", "CRAWL_1", "v1"),
        ProvenanceContext(DataProvenance.EMPIRICAL, "2.1.1", "CRAWL_1", "v1"),
    ],
)
def test_noncanonical_provenance_is_blocked(context):
    assert context.empirical_analysis_allowed is False
    with pytest.raises(ValueError, match="requires contractVersion"):
        context.require_empirical()


def test_production_provenance_requires_exact_four_field_envelope():
    valid = {
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_FULL",
        "dataVersion": "20260806.1",
        "dataProvenance": "EMPIRICAL",
    }
    assert require_production_provenance(valid) == valid
    for field in valid:
        broken = {**valid, field: None}
        with pytest.raises(ValueError, match="missing provenance fields"):
            require_production_provenance(broken)
    with pytest.raises(ValueError, match="dataVersion"):
        require_production_provenance({**valid, "dataVersion": "   "})


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("contractVersion", "2.1.1", "contractVersion=2.1.2"),
        ("crawlReleaseId", "RECON_1", "immutable CRAWL_"),
        ("dataProvenance", "SYNTHETIC", "dataProvenance=EMPIRICAL"),
    ],
)
def test_production_provenance_rejects_noncanonical_values(field, value, message):
    payload = {
        "contractVersion": "2.1.2",
        "crawlReleaseId": "CRAWL_20260806_FULL",
        "dataVersion": "20260806.1",
        "dataProvenance": "EMPIRICAL",
        field: value,
    }
    with pytest.raises(ValueError, match=message):
        require_production_provenance(payload)
