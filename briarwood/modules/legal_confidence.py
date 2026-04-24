from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.modules.property_data_quality import PropertyDataQualityModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
)
from briarwood.routing_schema import ModulePayload


def run_legal_confidence(context: ExecutionContext) -> dict[str, object]:
    """Build a structured legality-confidence payload for extra-unit paths.

    This wrapper does not perform legal classification. It surfaces how much
    structured evidence Briarwood has around zoning, additional-unit signals,
    and local-document coverage so synthesis can calibrate confidence.
    """

    try:
        property_input = build_property_input_from_context(context)
        data_quality_result = PropertyDataQualityModule().run(property_input)
        local_intelligence_result = (
            LocalIntelligenceModule().run(property_input)
            if property_input.local_documents
            else None
        )

        zone_flags = dict(property_input.zone_flags or {})
        has_accessory_signal = bool(property_input.has_back_house or property_input.adu_type or property_input.additional_units)
        payload = ModulePayload(
            data={
                "module_name": "legal_confidence",
                "summary": _build_summary(
                    has_accessory_signal=has_accessory_signal,
                    has_zone_flags=bool(zone_flags),
                    has_local_documents=bool(property_input.local_documents),
                    local_summary=local_intelligence_result.summary if local_intelligence_result else "",
                ),
                "legality_evidence": {
                    "has_accessory_signal": has_accessory_signal,
                    "adu_type": property_input.adu_type,
                    "has_back_house": property_input.has_back_house,
                    "additional_unit_count": len(property_input.additional_units or []),
                    "zone_flags": zone_flags,
                    "local_document_count": len(property_input.local_documents or []),
                    "multi_unit_allowed": zone_flags.get("multi_unit_allowed"),
                },
                "data_quality": {
                    "summary": data_quality_result.summary,
                    "metrics": dict(data_quality_result.metrics or {}),
                    "confidence": data_quality_result.confidence,
                },
                "local_intelligence": (
                    {
                        "summary": local_intelligence_result.summary,
                        "metrics": dict(local_intelligence_result.metrics or {}),
                        "confidence": local_intelligence_result.confidence,
                    }
                    if local_intelligence_result is not None
                    else None
                ),
            },
            confidence=_legal_evidence_confidence(
                data_quality_confidence=data_quality_result.confidence,
                local_confidence=local_intelligence_result.confidence if local_intelligence_result else None,
                has_zone_flags=bool(zone_flags),
                has_accessory_signal=has_accessory_signal,
            ),
            assumptions_used={
                "legacy_module": "PropertyDataQualityModule",
                "supporting_module": "LocalIntelligenceModule" if local_intelligence_result is not None else None,
                "uses_full_engine_report": False,
            },
            warnings=_legal_warnings(has_accessory_signal, zone_flags, property_input.local_documents),
        )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="legal_confidence",
            context=context,
            summary="Legal-confidence evidence unavailable — internal failure during evidence gathering.",
            warnings=[f"Legal-confidence fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "internal_exception"},
        ).model_dump()


def _build_summary(
    *,
    has_accessory_signal: bool,
    has_zone_flags: bool,
    has_local_documents: bool,
    local_summary: str,
) -> str:
    if not has_accessory_signal:
        return "No structured ADU or additional-unit signal was detected, so Briarwood does not yet have a specific extra-unit legality question to resolve."
    if has_zone_flags and has_local_documents and local_summary:
        return local_summary
    if has_zone_flags:
        return "Structured zoning flags are present, but source-backed local planning evidence is still limited."
    if has_local_documents:
        return "Local documents are available, but zoning flags are incomplete, so legality confidence remains conditional."
    return "Additional-unit signals exist, but legality confidence is limited because Briarwood lacks structured zoning and local-document evidence."


def _legal_evidence_confidence(
    *,
    data_quality_confidence: float,
    local_confidence: float | None,
    has_zone_flags: bool,
    has_accessory_signal: bool,
) -> float:
    values = [float(data_quality_confidence)]
    if local_confidence is not None:
        values.append(float(local_confidence))
    confidence = min(values)
    if has_zone_flags:
        confidence = max(confidence, 0.55)
    if not has_accessory_signal:
        confidence = min(confidence, 0.65)
    return round(confidence, 4)


def _legal_warnings(
    has_accessory_signal: bool,
    zone_flags: dict[str, object],
    local_documents: list[dict[str, object]],
) -> list[str]:
    warnings: list[str] = []
    if has_accessory_signal and not zone_flags:
        warnings.append("Accessory-unit signals exist, but no structured zoning flags were available.")
    if has_accessory_signal and not local_documents:
        warnings.append("No local planning or zoning documents were provided for extra-unit legality review.")
    return warnings


__all__ = ["run_legal_confidence"]
