from __future__ import annotations


def ncs_band(level: int | None) -> str | None:
    if level is None:
        return None
    if 1 <= level <= 2:
        return "level1to2"
    if 3 <= level <= 4:
        return "level3to4"
    if 5 <= level <= 6:
        return "level5to6"
    if 7 <= level <= 8:
        return "level7to8"
    raise ValueError("NCS level must be in the range 1..8")

