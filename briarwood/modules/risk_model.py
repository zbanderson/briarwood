from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.macro_reader import apply_macro_nudge
from briarwood.modules.risk_constraints import RiskConstraintsModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
)

OVERPRICED_THRESHOLD = 0.15
UNDERPRICED_THRESHOLD = -0.10
CONFIDENCE_STEP = 0.05
MACRO_MAX_NUDGE = 0.04


def run_risk_model(context: ExecutionContext) -> dict[str, object]:
    """Run Briarwood's risk-constraint logic through a scoped wrapper.

    Consumes the prior ``valuation`` output (when available) to surface a
    valuation-premium signal alongside the property-attribute risk flags.
    When valuation is absent, falls back to legacy behavior so the module
    is safe to run out of order.

    Error contract (DECISIONS.md 2026-04-24): internal exceptions are caught
    and returned as a ``module_payload_from_error`` fallback
    (``mode="fallback"``, ``confidence=0.08``). Missing ``legal_confidence``
    is valid and is not a missing-priors case — the dampener is load-bearing
    only when legal_conf is present.
    """

    try:
        property_input = build_property_input_from_context(context)
        result = RiskConstraintsModule().run(property_input)
        legacy_confidence = result.confidence

        bridge = _valuation_bridge(context, property_input)
        legal_conf = _legal_confidence(context)

        adjusted_confidence = legacy_confidence
        if bridge["premium_pct"] is not None and legacy_confidence is not None:
            if bridge["premium_pct"] >= OVERPRICED_THRESHOLD:
                adjusted_confidence = max(0.0, legacy_confidence - CONFIDENCE_STEP)
            elif bridge["premium_pct"] <= UNDERPRICED_THRESHOLD:
                adjusted_confidence = min(1.0, legacy_confidence + CONFIDENCE_STEP)
            adjusted_confidence = round(adjusted_confidence, 4)
        if legal_conf is not None and adjusted_confidence is not None and legal_conf < 0.5:
            adjusted_confidence = max(0.0, round(adjusted_confidence - 0.08, 4))

        macro_nudge = apply_macro_nudge(
            base_confidence=adjusted_confidence,
            context=context,
            dimension="liquidity",
            max_nudge=MACRO_MAX_NUDGE,
        )
        adjusted_confidence = macro_nudge.adjusted_confidence

        payload = module_payload_from_legacy_result(
            result=result,
            assumptions_used={
                "legacy_module": "RiskConstraintsModule",
                "property_id": property_input.property_id,
                "valuation_dependency_declared": True,
                "valuation_dependency_used": bridge["premium_pct"] is not None,
                "macro_context_used": macro_nudge.signal is not None,
                "uses_full_engine_report": False,
            },
            extra_data={
                "valuation_bridge": {
                    "fair_value_base": bridge["fair_value"],
                    "listed_price": bridge["listed_price"],
                    "premium_pct": bridge["premium_pct"],
                    "flag": bridge["flag"],
                },
                "legal_confidence_signal": legal_conf,
                "macro_nudge": macro_nudge.to_meta(),
            },
            warnings=list(bridge["warnings"]) + (
                ["Legal confidence is low, so risk confidence is dampened."] if legal_conf is not None and legal_conf < 0.5 else []
            ),
            required_fields=["purchase_price", "sqft", "beds", "baths"],
        )
        if adjusted_confidence is not None:
            payload = payload.model_copy(update={"confidence": adjusted_confidence})
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="risk_model",
            context=context,
            summary="Risk model unavailable — internal failure while evaluating risk constraints.",
            warnings=[f"Risk-model fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={"uses_full_engine_report": False, "fallback_reason": "internal_exception"},
        ).model_dump()


def _legal_confidence(context: ExecutionContext) -> float | None:
    legal_output = context.get_module_output("legal_confidence") if hasattr(context, "get_module_output") else None
    if not isinstance(legal_output, dict):
        return None
    confidence = legal_output.get("confidence")
    if isinstance(confidence, (int, float)):
        return float(confidence)
    return None


def _valuation_bridge(context: ExecutionContext, property_input: Any) -> dict[str, Any]:
    valuation_output = context.get_module_output("valuation") if hasattr(context, "get_module_output") else None
    fair_value: float | None = None
    listed_price: float | None = None
    flag: str | None = None
    warnings: list[str] = []

    if isinstance(valuation_output, dict):
        data = valuation_output.get("data") or {}
        metrics = data.get("metrics") if isinstance(data, dict) else None
        if isinstance(metrics, dict):
            raw_fair = metrics.get("briarwood_current_value")
            if isinstance(raw_fair, (int, float)) and raw_fair > 0:
                fair_value = float(raw_fair)

    raw_listed = getattr(property_input, "purchase_price", None)
    if isinstance(raw_listed, (int, float)) and raw_listed > 0:
        listed_price = float(raw_listed)

    premium_pct: float | None = None
    if fair_value is not None and listed_price is not None:
        premium_pct = round((listed_price - fair_value) / fair_value, 4)
        if premium_pct >= OVERPRICED_THRESHOLD:
            flag = "overpriced_vs_briarwood_fair_value"
            warnings.append(
                f"Listed at ${listed_price:,.0f} vs Briarwood fair value ${fair_value:,.0f} — "
                f"premium {premium_pct * 100:.1f}%."
            )
        elif premium_pct <= UNDERPRICED_THRESHOLD:
            flag = "priced_below_briarwood_fair_value"

    return {
        "fair_value": fair_value,
        "listed_price": listed_price,
        "premium_pct": premium_pct,
        "flag": flag,
        "warnings": warnings,
    }


__all__ = ["run_risk_model"]
