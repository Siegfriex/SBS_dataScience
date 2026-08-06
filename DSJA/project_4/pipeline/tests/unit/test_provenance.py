import pytest

from p4.quality.provenance import DataProvenance, ProvenanceContext


def test_only_canonical_crawl_release_allows_empirical_analysis():
    real = ProvenanceContext(DataProvenance.CRAWL_RELEASE, "2.1.2", "CRAWL_20260806_01", "20260806.1")
    assert real.empirical_analysis_allowed is True
    real.require_empirical()


@pytest.mark.parametrize(
    "context",
    [
        ProvenanceContext(DataProvenance.GENERATED_STRUCTURAL_FIXTURE, None, None, "fixture-v1"),
        ProvenanceContext(DataProvenance.CRAWL_RELEASE, None, "CRAWL_1", "v1"),
        ProvenanceContext(DataProvenance.CRAWL_RELEASE, "2.1.2", "RECON_1", "v1"),
    ],
)
def test_noncanonical_provenance_is_blocked(context):
    assert context.empirical_analysis_allowed is False
    with pytest.raises(ValueError, match="canonical contract"):
        context.require_empirical()

