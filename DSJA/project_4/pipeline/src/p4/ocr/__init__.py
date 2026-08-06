"""OCR recovery interfaces; raw asset collection remains Agent 1 owned."""

from p4.ocr.quality import (
    build_offline_pilot_manifest,
    compute_ocr_quality,
    count_ineligible_accepted_mappings,
)

__all__ = [
    "build_offline_pilot_manifest",
    "compute_ocr_quality",
    "count_ineligible_accepted_mappings",
]
