from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.routing_schema import ModulePayload
from briarwood.schemas import (
    CanonicalFieldProvenance,
    CanonicalPropertyData,
    EvidenceMode,
    InferenceMethod,
    InputCoverageStatus,
    MarketLocationSignals,
    OccupancyStrategy,
    PropertyFacts,
    PropertyInput,
    SourceMetadata,
    SourceCoverageItem,
    SourceTier,
    UserAssumptions,
    VerifiedStatus,
)


def build_property_input_from_context(context: ExecutionContext) -> PropertyInput:
    """Build a legacy ``PropertyInput`` from a scoped execution context.

    Briarwood is still in a transition period where several legacy modules
    expect ``PropertyInput`` directly. This helper keeps that adaptation
    explicit so scoped runners can reuse the existing module logic without
    depending on the full-engine report blob.
    """

    property_data = dict(
        (context.normalized_context or {}).get("property_data")
        or context.property_data
        or {}
    )
    if not property_data:
        raise ValueError("ExecutionContext.property_data is required to build PropertyInput.")

    if "facts" in property_data and isinstance(property_data["facts"], dict):
        return _build_from_canonical_dict(context, property_data)
    return _build_from_flat_dict(context, property_data)


def module_payload_from_legacy_result(
    *,
    result: Any,
    context: ExecutionContext | None = None,
    assumptions_used: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    extra_data: dict[str, Any] | None = None,
    required_fields: list[str] | None = None,
    mode: str | None = None,
) -> ModulePayload:
    """Normalize a legacy ``ModuleResult`` into Briarwood's routed payload shape."""

    data = {
        "module_name": getattr(result, "module_name", None),
        "score": getattr(result, "score", None),
        "summary": getattr(result, "summary", ""),
        "metrics": dict(getattr(result, "metrics", {}) or {}),
    }
    payload = getattr(result, "payload", None)
    if payload is not None:
        if hasattr(payload, "model_dump"):
            data["legacy_payload"] = payload.model_dump()
        elif is_dataclass(payload):
            data["legacy_payload"] = asdict(payload)
        elif hasattr(payload, "__dict__"):
            data["legacy_payload"] = dict(payload.__dict__)
        else:
            data["legacy_payload"] = payload

    section_evidence = getattr(result, "section_evidence", None)
    if section_evidence is not None:
        data["section_evidence"] = (
            asdict(section_evidence)
            if is_dataclass(section_evidence)
            else section_evidence.__dict__
            if hasattr(section_evidence, "__dict__")
            else section_evidence
        )

    if extra_data:
        data.update(extra_data)

    missing_inputs, estimated_inputs = _module_input_flags(
        context=context,
        required_fields=required_fields,
    )
    payload_mode = mode or _infer_payload_mode(
        confidence=getattr(result, "confidence", None),
        missing_inputs=missing_inputs,
    )

    return ModulePayload(
        data=data,
        confidence=getattr(result, "confidence", None),
        assumptions_used=dict(assumptions_used or {}),
        warnings=list(warnings or []),
        mode=payload_mode,
        missing_inputs=missing_inputs,
        estimated_inputs=estimated_inputs,
        confidence_band=confidence_band(getattr(result, "confidence", None)),
        module_name=str(getattr(result, "module_name", "") or ""),
        score=getattr(result, "score", None),
        summary=str(getattr(result, "summary", "") or ""),
    )


def module_payload_from_error(
    *,
    module_name: str,
    context: ExecutionContext | None = None,
    summary: str,
    warnings: list[str] | None = None,
    assumptions_used: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
    required_fields: list[str] | None = None,
    confidence: float = 0.08,
) -> ModulePayload:
    """Return a typed fallback payload instead of throwing on sparse inputs."""

    missing_inputs, estimated_inputs = _module_input_flags(
        context=context,
        required_fields=required_fields,
    )
    return ModulePayload(
        data={
            "module_name": module_name,
            "summary": summary,
            "score": None,
            "metrics": {},
            **dict(extra_data or {}),
        },
        confidence=confidence,
        assumptions_used=dict(assumptions_used or {}),
        warnings=list(warnings or []),
        mode="fallback",
        missing_inputs=missing_inputs,
        estimated_inputs=estimated_inputs,
        confidence_band=confidence_band(confidence),
        module_name=module_name,
        score=None,
        summary=summary,
    )


def module_payload_from_missing_prior(
    *,
    module_name: str,
    context: ExecutionContext | None = None,
    missing: list[str],
    summary: str | None = None,
    assumptions_used: dict[str, Any] | None = None,
    extra_data: dict[str, Any] | None = None,
) -> ModulePayload:
    """Return a typed error payload when required prior module outputs are missing.

    Companion to ``module_payload_from_error``. Distinct from that helper because
    missing-prior is a different signal: no computation was attempted, so the
    caller gets ``mode="error"`` and ``confidence=None`` (not ``"fallback"`` /
    0.08). Composite wrappers call this when ``prior_outputs`` lacks a required
    upstream module output, or when the upstream's own ``mode`` is ``"error"``
    or ``"fallback"`` (i.e. the prior degraded and cannot be used).

    The shape mirrors ``opportunity_cost``'s existing missing-priors branch
    (briarwood/modules/opportunity_cost.py) so trust gates can key on
    ``mode in {"error","fallback"}`` uniformly across all scoped wrappers.
    """

    assumptions = dict(assumptions_used or {})
    assumptions.setdefault("required_prior_modules", list(missing))

    if summary is None:
        summary = (
            f"{module_name} unavailable — required prior module outputs missing: "
            + ", ".join(missing)
        )

    return ModulePayload(
        data={
            "module_name": module_name,
            "summary": summary,
            "score": None,
            "metrics": {},
            **dict(extra_data or {}),
        },
        confidence=None,
        assumptions_used=assumptions,
        warnings=[f"Missing prior module output: {name}" for name in missing],
        mode="error",
        missing_inputs=list(missing),
        estimated_inputs=[],
        confidence_band=confidence_band(None),
        module_name=module_name,
        score=None,
        summary=summary,
    )


def confidence_band(value: float | None) -> str:
    if value is None:
        return "Speculative"
    if value >= 0.75:
        return "High confidence"
    if value >= 0.55:
        return "Moderate confidence"
    if value >= 0.3:
        return "Low confidence"
    return "Speculative"


def _module_input_flags(
    *,
    context: ExecutionContext | None,
    required_fields: list[str] | None,
) -> tuple[list[str], list[str]]:
    registry = dict((context.missing_data_registry if context else {}) or {})
    fields = dict(registry.get("fields") or {})
    required = list(required_fields or [])
    if required:
        missing = [field for field in required if (fields.get(field) or {}).get("status") == "missing"]
        estimated = [
            field
            for field in required
            if (fields.get(field) or {}).get("status") in {"estimated", "defaulted"}
        ]
        return missing, estimated
    return (
        list(registry.get("missing") or []),
        list(registry.get("estimated") or []) + list(registry.get("defaulted") or []),
    )


def _infer_payload_mode(
    *,
    confidence: float | None,
    missing_inputs: list[str],
) -> str:
    if confidence is not None and confidence < 0.2:
        return "fallback"
    if missing_inputs:
        return "partial"
    return "full"


def _build_from_canonical_dict(
    context: ExecutionContext,
    property_data: dict[str, Any],
) -> PropertyInput:
    facts = PropertyFacts(**dict(property_data.get("facts") or {}))
    market_signals = MarketLocationSignals(
        **_clean_market_signals_dict(
            dict(property_data.get("market_signals") or {}),
            dict(context.market_context or {}),
        )
    )
    user_assumptions = UserAssumptions(
        **_clean_user_assumptions_dict(
            dict(property_data.get("user_assumptions") or {}),
            dict(context.assumptions or {}),
        )
    )
    source_metadata = _build_source_metadata(property_data.get("source_metadata"))
    canonical = CanonicalPropertyData(
        property_id=str(
            property_data.get("property_id")
            or context.property_id
            or "scoped-property"
        ),
        facts=facts,
        market_signals=market_signals,
        user_assumptions=user_assumptions,
        source_metadata=source_metadata,
    )
    return PropertyInput.from_canonical(canonical)


def _build_from_flat_dict(
    context: ExecutionContext,
    property_data: dict[str, Any],
) -> PropertyInput:
    allowed_fields = {field.name for field in fields(PropertyInput)}
    combined = dict(property_data)
    combined.setdefault("property_id", context.property_id or property_data.get("property_id") or "scoped-property")
    combined.update(_clean_user_assumptions_dict({}, dict(context.assumptions or {})))
    combined.update(_clean_market_signals_dict({}, dict(context.market_context or {})))
    combined.setdefault("source_metadata", property_data.get("source_metadata"))

    filtered = {key: value for key, value in combined.items() if key in allowed_fields}
    filtered.setdefault("address", str(filtered.get("address") or context.property_summary.get("address") or "Unknown"))
    filtered.setdefault("town", str(filtered.get("town") or context.property_summary.get("town") or "Unknown"))
    filtered.setdefault("state", str(filtered.get("state") or context.property_summary.get("state") or "Unknown"))
    filtered.setdefault("beds", int(filtered.get("beds") or context.property_summary.get("beds") or 0))
    filtered.setdefault("baths", float(filtered.get("baths") or context.property_summary.get("baths") or 0.0))
    filtered.setdefault("sqft", int(filtered.get("sqft") or context.property_summary.get("sqft") or 0))
    return PropertyInput(**filtered)


def _clean_market_signals_dict(
    property_market_signals: dict[str, Any],
    context_market_signals: dict[str, Any],
) -> dict[str, Any]:
    values = dict(property_market_signals)
    values.update({key: value for key, value in context_market_signals.items() if value is not None})
    allowed_fields = {field.name for field in fields(MarketLocationSignals)}
    return {key: value for key, value in values.items() if key in allowed_fields}


def _clean_user_assumptions_dict(
    property_assumptions: dict[str, Any],
    context_assumptions: dict[str, Any],
) -> dict[str, Any]:
    values = dict(property_assumptions)
    values.update({key: value for key, value in context_assumptions.items() if value is not None})
    occupancy = values.get("occupancy_strategy")
    if isinstance(occupancy, str):
        try:
            values["occupancy_strategy"] = OccupancyStrategy(occupancy)
        except ValueError:
            pass
    allowed_fields = {field.name for field in fields(UserAssumptions)}
    return {key: value for key, value in values.items() if key in allowed_fields}


def _build_source_metadata(raw_value: Any) -> SourceMetadata:
    if isinstance(raw_value, SourceMetadata):
        return raw_value

    raw_dict = dict(raw_value or {})
    raw_mode = raw_dict.get("evidence_mode", EvidenceMode.PUBLIC_RECORD.value)
    try:
        evidence_mode = raw_mode if isinstance(raw_mode, EvidenceMode) else EvidenceMode(str(raw_mode))
    except ValueError:
        evidence_mode = EvidenceMode.PUBLIC_RECORD

    return SourceMetadata(
        evidence_mode=evidence_mode,
        source_coverage=_normalize_source_coverage(raw_dict.get("source_coverage")),
        provenance=list(raw_dict.get("provenance") or []),
        freshest_as_of=raw_dict.get("freshest_as_of"),
        field_provenance=_normalize_field_provenance(raw_dict.get("field_provenance")),
        mapper_version=str(raw_dict.get("mapper_version") or "legacy"),
        property_evidence_profile=raw_dict.get("property_evidence_profile"),
    )


def _normalize_source_coverage(raw_value: Any) -> dict[str, SourceCoverageItem]:
    """Convert raw source coverage mappings into typed coverage items."""

    normalized: dict[str, SourceCoverageItem] = {}
    raw_dict = dict(raw_value or {})
    for key, value in raw_dict.items():
        if isinstance(value, SourceCoverageItem):
            normalized[str(key)] = value
            continue
        if not isinstance(value, dict):
            continue
        try:
            normalized[str(key)] = SourceCoverageItem(
                category=str(value.get("category") or key),
                status=InputCoverageStatus(str(value.get("status") or InputCoverageStatus.MISSING.value)),
                source_name=value.get("source_name"),
                freshness=value.get("freshness"),
                note=value.get("note"),
            )
        except ValueError:
            normalized[str(key)] = SourceCoverageItem(
                category=str(value.get("category") or key),
                status=InputCoverageStatus.MISSING,
                source_name=value.get("source_name"),
                freshness=value.get("freshness"),
                note=value.get("note"),
            )
    return normalized


def _normalize_field_provenance(raw_value: Any) -> dict[str, CanonicalFieldProvenance]:
    """Convert raw field provenance mappings into typed provenance entries."""

    normalized: dict[str, CanonicalFieldProvenance] = {}
    raw_dict = dict(raw_value or {})
    for key, value in raw_dict.items():
        if isinstance(value, CanonicalFieldProvenance):
            normalized[str(key)] = value
            continue
        if not isinstance(value, dict):
            continue
        try:
            raw_method = value.get("inference_method") or InferenceMethod.EXTRACTED.value
            try:
                inference_method = (
                    raw_method
                    if isinstance(raw_method, InferenceMethod)
                    else InferenceMethod(str(raw_method))
                )
            except ValueError:
                inference_method = InferenceMethod.EXTRACTED
            normalized[str(key)] = CanonicalFieldProvenance(
                value=value.get("value"),
                source=str(value.get("source") or "unknown"),
                source_tier=SourceTier(str(value.get("source_tier") or SourceTier.TIER_3.value)),
                verified_status=VerifiedStatus(
                    str(value.get("verified_status") or VerifiedStatus.UNVERIFIED.value)
                ),
                last_updated=value.get("last_updated"),
                confidence=float(value.get("confidence") or 0.0),
                mapper_version=str(value.get("mapper_version") or "legacy"),
                notes=list(value.get("notes") or []),
                inference_method=inference_method,
            )
        except (TypeError, ValueError):
            continue
    return normalized


__all__ = [
    "build_property_input_from_context",
    "confidence_band",
    "module_payload_from_error",
    "module_payload_from_legacy_result",
    "module_payload_from_missing_prior",
]
