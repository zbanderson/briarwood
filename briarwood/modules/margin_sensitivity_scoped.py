from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scoped_common import (
    module_payload_from_error,
    module_payload_from_missing_prior,
)
from briarwood.routing_schema import ModulePayload

_DEGRADED_MODES = {"error", "fallback"}


def run_margin_sensitivity(context: ExecutionContext) -> dict[str, object]:
    """Build a scoped margin-sensitivity view for renovation paths.

    This is a composite wrapper that reads the already-produced arv_model,
    renovation_impact, and carry_cost outputs to produce a margin-sensitivity
    analysis showing how renovation economics shift under different assumptions.

    Error contract (DECISIONS.md 2026-04-24): missing or degraded priors →
    ``module_payload_from_missing_prior`` (``mode="error"``). Internal
    exceptions → ``module_payload_from_error`` (``mode="fallback"``).
    """

    missing = _collect_missing_priors(
        context, ["arv_model", "renovation_impact", "carry_cost"]
    )
    if missing:
        return module_payload_from_missing_prior(
            module_name="margin_sensitivity",
            context=context,
            missing=missing,
            assumptions_used={
                "composite_from_prior_outputs": True,
                "uses_full_engine_report": False,
            },
        ).model_dump()

    arv_output = context.get_module_output("arv_model") or {}
    renovation_output = context.get_module_output("renovation_impact") or {}
    carry_output = context.get_module_output("carry_cost") or {}

    try:
        arv_data = dict(arv_output.get("data", {}) or {})
        arv_snapshot = dict(arv_data.get("arv_snapshot", {}) or {})
        reno_data = dict(renovation_output.get("data", {}) or {})
        reno_metrics = dict(reno_data.get("metrics", {}) or {})
        carry_data = dict(carry_output.get("data", {}) or {})
        carry_metrics = dict(carry_data.get("metrics", {}) or {})

        renovated_bcv = float(arv_snapshot.get("renovated_bcv") or 0.0)
        current_bcv = float(arv_snapshot.get("current_bcv") or 0.0)
        renovation_budget = float(arv_snapshot.get("renovation_budget") or 0.0)
        roi_pct = float(arv_snapshot.get("roi_pct") or 0.0)

        monthly_carry = float(carry_metrics.get("monthly_total_cost") or 0.0)
        holding_months = 6  # standard renovation + sale horizon

        # Margin scenarios: budget overrun, value miss, holding cost drag
        scenarios = _build_scenarios(
            renovated_bcv=renovated_bcv,
            current_bcv=current_bcv,
            renovation_budget=renovation_budget,
            monthly_carry=monthly_carry,
            holding_months=holding_months,
        )

        # Breakeven: how much can budget overrun before net value creation hits zero
        gross_value_creation = renovated_bcv - current_bcv
        total_hold_cost = monthly_carry * holding_months
        breakeven_budget = gross_value_creation - total_hold_cost if gross_value_creation > 0 else 0.0
        budget_overrun_margin = (
            ((breakeven_budget - renovation_budget) / renovation_budget * 100.0)
            if renovation_budget > 0
            else 0.0
        )

        summary = _build_summary(
            roi_pct=roi_pct,
            budget_overrun_margin=budget_overrun_margin,
            monthly_carry=monthly_carry,
            holding_months=holding_months,
        )

        payload = ModulePayload(
            data={
                "module_name": "margin_sensitivity",
                "summary": summary,
                "sensitivity_scenarios": scenarios,
                "margin_snapshot": {
                    "renovated_bcv": renovated_bcv,
                    "current_bcv": current_bcv,
                    "renovation_budget": renovation_budget,
                    "gross_value_creation": gross_value_creation,
                    "monthly_carry": monthly_carry,
                    "holding_months": holding_months,
                    "total_hold_cost": round(total_hold_cost, 2),
                    "breakeven_budget": round(breakeven_budget, 2),
                    "budget_overrun_margin_pct": round(budget_overrun_margin, 1),
                    "base_roi_pct": roi_pct,
                },
            },
            confidence=_min_confidence(arv_output, renovation_output, carry_output),
            assumptions_used={
                "composite_from_prior_outputs": True,
                "required_prior_modules": ["arv_model", "renovation_impact", "carry_cost"],
                "holding_months_assumption": holding_months,
                "uses_full_engine_report": False,
            },
            warnings=_merge_warnings(arv_output, renovation_output, carry_output),
        )
        return payload.model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="margin_sensitivity",
            context=context,
            summary="Margin sensitivity unavailable — internal failure composing sensitivity scenarios.",
            warnings=[f"Margin-sensitivity fallback: {type(exc).__name__}: {exc}"],
            assumptions_used={
                "composite_from_prior_outputs": True,
                "uses_full_engine_report": False,
                "fallback_reason": "internal_exception",
            },
        ).model_dump()


def _collect_missing_priors(
    context: ExecutionContext, required: list[str]
) -> list[str]:
    missing: list[str] = []
    for name in required:
        output = context.get_module_output(name)
        if not isinstance(output, dict):
            missing.append(name)
            continue
        mode = output.get("mode")
        if isinstance(mode, str) and mode in _DEGRADED_MODES:
            missing.append(name)
    return missing


def _build_scenarios(
    *,
    renovated_bcv: float,
    current_bcv: float,
    renovation_budget: float,
    monthly_carry: float,
    holding_months: int,
) -> list[dict[str, Any]]:
    """Build margin-sensitivity scenarios with budget and value shifts."""

    gross = renovated_bcv - current_bcv
    hold_cost = monthly_carry * holding_months
    scenarios: list[dict[str, Any]] = []

    for label, budget_mult, value_mult in [
        ("Base case", 1.0, 1.0),
        ("Budget +20%", 1.2, 1.0),
        ("Budget +40%", 1.4, 1.0),
        ("Value -10%", 1.0, 0.9),
        ("Value -20%", 1.0, 0.8),
        ("Budget +20%, Value -10%", 1.2, 0.9),
    ]:
        adj_budget = renovation_budget * budget_mult
        adj_gross = (gross * value_mult)
        net = adj_gross - adj_budget - hold_cost
        adj_roi = (net / adj_budget * 100.0) if adj_budget > 0 else 0.0
        scenarios.append({
            "label": label,
            "renovation_budget": round(adj_budget, 2),
            "gross_value_creation": round(adj_gross, 2),
            "hold_cost": round(hold_cost, 2),
            "net_profit": round(net, 2),
            "roi_pct": round(adj_roi, 1),
            "profitable": net > 0,
        })

    return scenarios


def _build_summary(
    *,
    roi_pct: float,
    budget_overrun_margin: float,
    monthly_carry: float,
    holding_months: int,
) -> str:
    total_hold = monthly_carry * holding_months
    if budget_overrun_margin > 30:
        margin_label = "comfortable"
    elif budget_overrun_margin > 10:
        margin_label = "moderate"
    elif budget_overrun_margin > 0:
        margin_label = "thin"
    else:
        margin_label = "negative"

    return (
        f"Base ROI {roi_pct:.1f}% with {margin_label} margin for budget overruns "
        f"({budget_overrun_margin:+.0f}% before breakeven). "
        f"Holding cost of ${total_hold:,.0f} over {holding_months} months "
        f"is factored into all scenarios."
    )


def _min_confidence(*outputs: dict[str, Any]) -> float | None:
    values = [
        float(output["confidence"])
        for output in outputs
        if isinstance(output, dict) and isinstance(output.get("confidence"), (int, float))
    ]
    if not values:
        return None
    return round(min(values), 4)


def _merge_warnings(*outputs: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for output in outputs:
        for warning in list(output.get("warnings") or []):
            text = str(warning).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


__all__ = ["run_margin_sensitivity"]
