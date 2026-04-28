"""Model confidence-vs-outcome alignment helpers for Stage 4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from briarwood.eval.outcomes import OutcomeRecord


HIGH_CONFIDENCE_THRESHOLD = 0.75
UNDERPERFORMANCE_APE_THRESHOLD = 0.10
ALIGNMENT_ZERO_SCORE_APE = 0.20


@dataclass(slots=True)
class AlignmentScore:
    absolute_error: float
    absolute_pct_error: float
    alignment_score: float
    high_confidence: bool
    underperformed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AlignmentResult:
    status: str
    reason: str | None = None
    row: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_alignment_score(
    *,
    predicted_value: float,
    confidence: float | None,
    outcome_value: float,
) -> AlignmentScore:
    absolute_error = abs(float(predicted_value) - float(outcome_value))
    absolute_pct_error = absolute_error / float(outcome_value)
    alignment_score = max(0.0, 1.0 - min(absolute_pct_error / ALIGNMENT_ZERO_SCORE_APE, 1.0))
    high_confidence = confidence is not None and float(confidence) >= HIGH_CONFIDENCE_THRESHOLD
    underperformed = high_confidence and absolute_pct_error >= UNDERPERFORMANCE_APE_THRESHOLD
    return AlignmentScore(
        absolute_error=round(absolute_error, 4),
        absolute_pct_error=round(absolute_pct_error, 6),
        alignment_score=round(alignment_score, 6),
        high_confidence=high_confidence,
        underperformed=underperformed,
    )


def receive_feedback_for_module(
    module_name: str,
    session_id: str,
    signal: dict[str, Any],
) -> dict[str, Any]:
    """Record one module feedback signal without recalibrating the module."""

    payload = signal.get("module_payload") or signal.get("payload") or signal.get("output")
    if not isinstance(payload, dict):
        return AlignmentResult("skipped", "module_payload is required").to_dict()

    outcome_raw = signal.get("outcome")
    outcome = _coerce_outcome(outcome_raw)
    if outcome is None:
        return AlignmentResult("skipped", "sale_price outcome is required").to_dict()

    prediction = extract_prediction(module_name, payload)
    if prediction is None:
        return AlignmentResult("skipped", "module prediction is unavailable").to_dict()
    predicted_value, predicted_label, confidence = prediction
    if confidence is None:
        return AlignmentResult("skipped", "module confidence is unavailable").to_dict()

    row = build_alignment_row(
        module_name=module_name,
        session_id=session_id,
        module_payload=payload,
        outcome=outcome,
        predicted_value=predicted_value,
        predicted_label=predicted_label,
        confidence=confidence,
        turn_trace_id=_clean_optional(signal.get("turn_trace_id")),
        conversation_id=_clean_optional(signal.get("conversation_id")),
        property_id=_clean_optional(signal.get("property_id") or outcome.property_id),
        match_method=_clean_optional(signal.get("match_method")),
    )

    store = signal.get("store")
    if store is None:
        from api.store import get_store

        store = get_store()
    inserted = store.insert_model_alignment(row)
    return AlignmentResult("recorded", row=inserted).to_dict()


def build_alignment_row(
    *,
    module_name: str,
    session_id: str,
    module_payload: dict[str, Any],
    outcome: OutcomeRecord,
    predicted_value: float,
    predicted_label: str | None,
    confidence: float,
    turn_trace_id: str | None = None,
    conversation_id: str | None = None,
    property_id: str | None = None,
    match_method: str | None = None,
) -> dict[str, Any]:
    score = compute_alignment_score(
        predicted_value=predicted_value,
        confidence=confidence,
        outcome_value=outcome.outcome_value,
    )
    return {
        "turn_trace_id": turn_trace_id,
        "conversation_id": conversation_id,
        "property_id": property_id or outcome.property_id,
        "module_name": module_name,
        "predicted_value": float(predicted_value),
        "predicted_label": predicted_label,
        "confidence": float(confidence),
        "outcome_type": outcome.outcome_type,
        "outcome_value": outcome.outcome_value,
        "outcome_date": outcome.outcome_date,
        **score.to_dict(),
        "evidence": {
            "session_id": session_id,
            "match_method": match_method,
            "outcome": outcome.to_dict(),
            "module_payload_subset": _payload_subset(module_payload),
            "thresholds": {
                "high_confidence": HIGH_CONFIDENCE_THRESHOLD,
                "underperformance_ape": UNDERPERFORMANCE_APE_THRESHOLD,
                "alignment_zero_score_ape": ALIGNMENT_ZERO_SCORE_APE,
            },
        },
    }


def extract_prediction(module_name: str, payload: dict[str, Any]) -> tuple[float, str | None, float | None] | None:
    if module_name in {"current_value", "valuation"}:
        value = _first_number(
            payload,
            ("data", "legacy_payload", "briarwood_current_value"),
            ("data", "metrics", "briarwood_current_value"),
            ("output", "briarwood_current_value"),
            ("briarwood_current_value",),
        )
        label = _first_str(
            payload,
            ("data", "legacy_payload", "pricing_view"),
            ("data", "metrics", "pricing_view"),
            ("output", "pricing_view"),
            ("pricing_view",),
        )
        confidence = _first_number(
            payload,
            ("confidence",),
            ("data", "legacy_payload", "pricing_view_confidence"),
            ("data", "metrics", "pricing_view_confidence"),
            ("output", "pricing_view_confidence"),
        )
        if value is None:
            return None
        return value, label, confidence

    if module_name == "comparable_sales":
        value = _first_number(
            payload,
            ("data", "metrics", "comparable_value"),
            ("data", "legacy_payload", "comparable_value"),
            ("output", "comparable_value"),
            ("comparable_value",),
        )
        confidence = _first_number(
            payload,
            ("confidence",),
            ("data", "metrics", "comp_confidence_score"),
            ("data", "metrics", "comp_confidence"),
            ("data", "legacy_payload", "comp_confidence_score"),
            ("data", "legacy_payload", "confidence"),
        )
        if value is None:
            return None
        return value, None, confidence

    return None


def _coerce_outcome(value: Any) -> OutcomeRecord | None:
    if isinstance(value, OutcomeRecord):
        outcome = value
    elif isinstance(value, dict):
        try:
            outcome = OutcomeRecord.from_mapping(value, default_source="manual_json")
        except ValueError:
            return None
    else:
        return None
    if outcome.outcome_type != "sale_price":
        return None
    return outcome


def _first_number(payload: dict[str, Any], *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        value = _get_path(payload, path)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _first_str(payload: dict[str, Any], *paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value = _get_path(payload, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _payload_subset(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "module_name": payload.get("module_name") or data.get("module_name"),
        "mode": payload.get("mode"),
        "confidence": payload.get("confidence"),
        "confidence_band": payload.get("confidence_band"),
        "summary": payload.get("summary") or data.get("summary"),
        "metrics": data.get("metrics"),
    }


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "ALIGNMENT_ZERO_SCORE_APE",
    "HIGH_CONFIDENCE_THRESHOLD",
    "UNDERPERFORMANCE_APE_THRESHOLD",
    "AlignmentResult",
    "AlignmentScore",
    "build_alignment_row",
    "compute_alignment_score",
    "extract_prediction",
    "receive_feedback_for_module",
]
