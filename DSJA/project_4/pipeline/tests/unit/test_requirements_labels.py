import pytest

from p4.label.career import LabelEvidence, career_class, intern_access_class, label_track
from p4.parse.requirements import experience_months, extract_requirements


def evidence(**overrides):
    values = {
        "is_intern": False,
        "nominal_entry": False,
        "explicit_experienced": False,
        "min_experience_months": None,
        "mandatory_prior_experience": False,
        "portfolio_required": False,
        "boundary_resolved": True,
    }
    values.update(overrides)
    return LabelEvidence(**values)


@pytest.mark.parametrize(
    "months,expected",
    [(25, "E2"), (35, "E2"), (36, "E3"), (60, "E3")],
)
def test_experience_month_boundaries(months, expected):
    assert career_class(evidence(min_experience_months=months)) == expected


def test_entry_and_unknown_rules():
    assert career_class(evidence(nominal_entry=True)) == "E0"
    assert career_class(evidence(nominal_entry=True, min_experience_months=1)) == "E1"
    assert career_class(evidence(nominal_entry=True, mandatory_prior_experience=True)) == "E1"
    assert career_class(evidence(boundary_resolved=False)) == "U"
    assert career_class(evidence(explicit_experienced=True)) == "E3"


def test_intern_rules_do_not_treat_portfolio_as_prior_experience():
    portfolio_only = evidence(is_intern=True, portfolio_required=True)
    assert intern_access_class(portfolio_only) == "I0"
    label = label_track("TRK_1", portfolio_only)
    assert label["experiencedInternFlag"] is False
    assert label["restrictedInternFlag"] is False


def test_preferred_experience_does_not_restrict_intern():
    preferred_section = {
        "sectionId": "SEC_1",
        "sectionType": "preferred",
        "sectionText": "관련 실무 경험 2년 우대",
        "boundaryResolvedFlag": True,
    }
    requirement = extract_requirements(preferred_section)[0]
    assert requirement["mandatoryFlag"] is False
    assert requirement["priorExperienceFlag"] is False
    assert intern_access_class(evidence(is_intern=True)) == "I0"


def test_required_prior_experience_restricts_intern():
    required_section = {
        "sectionId": "SEC_2",
        "sectionType": "required",
        "sectionText": "관련 프로젝트 경험 필수",
        "boundaryResolvedFlag": True,
    }
    requirement = extract_requirements(required_section)[0]
    assert requirement["mandatoryFlag"] is True
    assert requirement["priorExperienceFlag"] is True
    assert intern_access_class(evidence(is_intern=True, mandatory_prior_experience=True)) == "I1"


def test_unresolved_intern_is_iu():
    assert intern_access_class(evidence(is_intern=True, boundary_resolved=False)) == "IU"


def test_experience_parser():
    assert experience_months("경력 2년 이상") == 24
    assert experience_months("25개월 이상") == 25
    assert experience_months("신입") is None

