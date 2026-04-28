"""Deterministic chat-tier ADU / accessory-unit Scout pattern."""

from __future__ import annotations

from briarwood.claims.base import SurfacedInsight
from briarwood.routing_schema import UnifiedIntelligenceOutput
from briarwood.value_scout.patterns._unified_helpers import (
    as_bool,
    as_float,
    first_path,
    unified_dict,
)

MIN_LEGAL_CONFIDENCE = 0.55

_ACCESSORY_SIGNAL_PATHS: tuple[str, ...] = (
    "supporting_facts.legal_confidence.legality_evidence.has_accessory_signal",
    "supporting_facts.legal_confidence.has_accessory_signal",
    "legal_confidence.legality_evidence.has_accessory_signal",
)

_LEGAL_CONFIDENCE_PATHS: tuple[str, ...] = (
    "supporting_facts.legal_confidence.confidence",
    "legal_confidence.confidence",
)

_ADU_TYPE_PATHS: tuple[str, ...] = (
    "supporting_facts.legal_confidence.legality_evidence.adu_type",
    "legal_confidence.legality_evidence.adu_type",
)


def detect(unified: UnifiedIntelligenceOutput) -> SurfacedInsight | None:
    """Surface accessory-unit optionality when legal evidence is credible."""

    data = unified_dict(unified)
    signal, signal_path = first_path(data, _ACCESSORY_SIGNAL_PATHS)
    if not as_bool(signal):
        return None

    confidence_value, confidence_path = first_path(data, _LEGAL_CONFIDENCE_PATHS)
    legal_confidence = as_float(confidence_value)
    if legal_confidence is not None and legal_confidence < MIN_LEGAL_CONFIDENCE:
        return None

    adu_type, adu_type_path = first_path(data, _ADU_TYPE_PATHS)
    label = str(adu_type).replace("_", " ") if adu_type else "accessory-unit"
    score = legal_confidence if legal_confidence is not None else 0.62

    return SurfacedInsight(
        headline="Accessory-unit optionality is hiding in the evidence.",
        reason=(
            f"The legal-confidence evidence flags a {label} signal, which can "
            "change the income or repositioning path before it changes the "
            "headline valuation."
        ),
        supporting_fields=[
            path
            for path in (signal_path, confidence_path, adu_type_path)
            if path is not None
        ],
        category="adu_signal",
        confidence=round(min(0.88, max(0.6, score)), 3),
    )
