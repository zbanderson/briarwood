from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfidenceClassification:
    """Shared confidence taxonomy for product surfaces and calibrated narratives."""

    band: str
    narrative_level: str


def classify_confidence(
    *,
    overall_confidence: float,
    comp_count: int,
    rent_source: str,
    town_confidence: float,
) -> ConfidenceClassification:
    """Return one shared confidence assessment for UI and narrative layers."""
    weak_count = 0
    strong_count = 0

    if comp_count < 3:
        weak_count += 1
    elif comp_count >= 5:
        strong_count += 1

    normalized_rent_source = str(rent_source or "missing").strip().lower()
    if normalized_rent_source == "missing":
        weak_count += 1
    elif normalized_rent_source in {"manual_input", "provided"}:
        strong_count += 1

    if town_confidence < 0.50:
        weak_count += 1
    elif town_confidence >= 0.75:
        strong_count += 1

    if weak_count >= 2 or overall_confidence < 0.55:
        return ConfidenceClassification(band="Low", narrative_level="Provisional")
    if strong_count >= 3 and overall_confidence >= 0.75:
        return ConfidenceClassification(band="High", narrative_level="Grounded")
    return ConfidenceClassification(band="Medium", narrative_level="Estimated")

