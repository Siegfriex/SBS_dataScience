from __future__ import annotations

from dataclasses import dataclass


CAREER_CLASSES = {"E0", "E1", "E2", "E3", "U"}
INTERN_ACCESS_CLASSES = {"I0", "I1", "IU"}


@dataclass(frozen=True)
class LabelEvidence:
    is_intern: bool
    nominal_entry: bool
    explicit_experienced: bool
    min_experience_months: int | None
    mandatory_prior_experience: bool
    portfolio_required: bool
    boundary_resolved: bool


def career_class(evidence: LabelEvidence) -> str:
    if evidence.is_intern or not evidence.boundary_resolved:
        return "U"
    months = evidence.min_experience_months
    if evidence.nominal_entry:
        if (months is not None and months > 0) or evidence.mandatory_prior_experience:
            return "E1"
        return "E0"
    if evidence.explicit_experienced:
        return "E3"
    if months is not None and 12 <= months <= 35:
        return "E2"
    if months is not None and months >= 36:
        return "E3"
    return "U"


def intern_access_class(evidence: LabelEvidence) -> str | None:
    if not evidence.is_intern:
        return None
    if not evidence.boundary_resolved:
        return "IU"
    if (evidence.min_experience_months is not None and evidence.min_experience_months > 0) or evidence.mandatory_prior_experience:
        return "I1"
    return "I0"


def label_track(track_id: str, evidence: LabelEvidence) -> dict[str, object]:
    access = intern_access_class(evidence)
    restricted = None if not evidence.is_intern or access == "IU" else access == "I1"
    experienced = None if not evidence.is_intern or access == "IU" else evidence.mandatory_prior_experience
    return {
        "trackId": track_id,
        "careerClass": career_class(evidence),
        "internAccessClass": access,
        "restrictedInternFlag": restricted,
        "experiencedInternFlag": experienced,
        "boundaryResolvedFlag": evidence.boundary_resolved,
    }

