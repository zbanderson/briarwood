from __future__ import annotations

from briarwood.schemas import (
    EvidenceMode,
    InputCoverageStatus,
    PropertyInput,
    SectionEvidence,
    SourceCoverageItem,
)


def build_section_evidence(
    property_input: PropertyInput,
    *,
    categories: list[str],
    notes: list[str] | None = None,
    extra_missing_inputs: list[str] | None = None,
    extra_estimated_inputs: list[str] | None = None,
) -> SectionEvidence:
    coverage_items: list[SourceCoverageItem] = [property_input.coverage_for(category) for category in categories]
    missing_inputs = [item.category for item in coverage_items if item.status == InputCoverageStatus.MISSING]
    estimated_inputs = [item.category for item in coverage_items if item.status == InputCoverageStatus.ESTIMATED]
    if extra_missing_inputs:
        for item in extra_missing_inputs:
            if item not in missing_inputs:
                missing_inputs.append(item)
    if extra_estimated_inputs:
        for item in extra_estimated_inputs:
            if item not in estimated_inputs:
                estimated_inputs.append(item)
    return SectionEvidence(
        evidence_mode=(property_input.source_metadata.evidence_mode if property_input.source_metadata else EvidenceMode.PUBLIC_RECORD),
        categories=coverage_items,
        major_missing_inputs=missing_inputs,
        estimated_inputs=estimated_inputs,
        notes=list(notes or []),
    )


def infer_overall_report_confidence(property_input: PropertyInput, module_confidences: list[float]) -> float:
    if not module_confidences:
        return 0.0
    confidence = sum(module_confidences) / len(module_confidences)
    if property_input.source_metadata is None:
        return round(confidence, 2)
    if any(
        item.status == InputCoverageStatus.MISSING
        for key, item in property_input.source_metadata.source_coverage.items()
        if key in {"price_ask", "rent_estimate", "insurance_estimate", "comp_support"}
    ):
        confidence = min(confidence, 0.68)
    if any(item.status == InputCoverageStatus.ESTIMATED for item in property_input.source_metadata.source_coverage.values()):
        confidence = min(confidence, 0.76)
    return round(confidence, 2)
