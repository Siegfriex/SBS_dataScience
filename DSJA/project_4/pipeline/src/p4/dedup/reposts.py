from __future__ import annotations

from difflib import SequenceMatcher

import pandas as pd

from p4.common.keys import make_duplicate_group_id, normalize


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def assign_repost_groups(
    postings: pd.DataFrame,
    window_days: int = 90,
    title_threshold: float = 0.90,
) -> pd.DataFrame:
    required = {"postingId", "companyKey", "titleText", "postedAt", "postingEligibleFlag"}
    missing = required.difference(postings.columns)
    if missing:
        raise ValueError(f"postings missing dedup columns: {sorted(missing)}")
    result = postings.copy()
    result["postedAt"] = pd.to_datetime(result["postedAt"], utc=True)
    result = result.sort_values(["companyKey", "postedAt", "postingId"]).reset_index(drop=True)
    groups: list[dict[str, object]] = []
    assignments: dict[str, tuple[str, str, bool]] = {}

    for row in result.to_dict(orient="records"):
        posting_id = row["postingId"]
        if not bool(row["postingEligibleFlag"]):
            group_id = make_duplicate_group_id(row["companyKey"], row["titleText"], row["postedAt"])
            assignments[posting_id] = (group_id, posting_id, True)
            continue
        matched = None
        for group in reversed(groups):
            if group["companyKey"] != row["companyKey"]:
                continue
            days = (row["postedAt"] - group["firstPostedAt"]).days
            if days > window_days:
                continue
            if title_similarity(row["titleText"], str(group["titleText"])) >= title_threshold:
                matched = group
                break
        if matched is None:
            group_id = make_duplicate_group_id(row["companyKey"], row["titleText"], row["postedAt"])
            matched = {
                "duplicateGroupId": group_id,
                "companyKey": row["companyKey"],
                "titleText": row["titleText"],
                "firstPostedAt": row["postedAt"],
                "canonicalPostingId": posting_id,
            }
            groups.append(matched)
            canonical = True
        else:
            canonical = False
        assignments[posting_id] = (
            str(matched["duplicateGroupId"]),
            str(matched["canonicalPostingId"]),
            canonical,
        )

    result["duplicateGroupId"] = result["postingId"].map(lambda value: assignments[value][0])
    result["canonicalPostingId"] = result["postingId"].map(lambda value: assignments[value][1])
    result["canonicalRecordFlag"] = result["postingId"].map(lambda value: assignments[value][2])
    return result

