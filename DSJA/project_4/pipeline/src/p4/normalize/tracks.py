from __future__ import annotations

from typing import Any

from p4.common.keys import make_track_id, normalize


TRACK_TYPES = {
    "entry",
    "intern",
    "experienced",
    "entryInternMixed",
    "entryExperiencedMixed",
    "internExperiencedMixed",
    "allMixed",
    "mixedUnresolved",
    "unknown",
}


def infer_track_type(text: str) -> str:
    normalized = normalize(text)
    entry = "신입" in normalized or "경력무관" in normalized
    intern = "인턴" in normalized
    experienced = "경력" in normalized and "경력무관" not in normalized
    flags = (entry, intern, experienced)
    if flags == (True, False, False):
        return "entry"
    if flags == (False, True, False):
        return "intern"
    if flags == (False, False, True):
        return "experienced"
    if flags == (True, True, False):
        return "entryInternMixed"
    if flags == (True, False, True):
        return "entryExperiencedMixed"
    if flags == (False, True, True):
        return "internExperiencedMixed"
    if flags == (True, True, True):
        return "allMixed"
    return "unknown"


def split_tracks(posting: dict[str, Any], explicit_tracks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    posting_id = posting["postingId"]
    if explicit_tracks:
        rows = []
        for ordinal, track in enumerate(explicit_tracks):
            text = str(track.get("text") or "")
            track_type = track.get("trackType") or infer_track_type(text)
            rows.append(
                {
                    "trackId": make_track_id(posting_id, ordinal),
                    "postingId": posting_id,
                    "trackType": track_type if track_type in TRACK_TYPES else "unknown",
                    "trackOrdinal": ordinal,
                    "mixedResolvedFlag": track_type not in {"mixedUnresolved", "unknown"},
                    "jobCodeLevel": track.get("jobCodeLevel"),
                    "jobCode": track.get("jobCode"),
                    "trackText": text,
                }
            )
        return rows

    text = f"{posting.get('titleText', '')}\n{posting.get('bodyText', '')}"
    inferred = infer_track_type(text)
    mixed = inferred.endswith("Mixed") or inferred == "allMixed"
    track_type = "mixedUnresolved" if mixed else inferred
    return [
        {
            "trackId": make_track_id(posting_id, 0),
            "postingId": posting_id,
            "trackType": track_type,
            "trackOrdinal": 0,
            "mixedResolvedFlag": not mixed and track_type != "unknown",
            "jobCodeLevel": None,
            "jobCode": None,
            "trackText": text,
        }
    ]
