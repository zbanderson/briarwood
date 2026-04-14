from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.routing_schema import ModulePayload


def run_hold_to_rent(context: ExecutionContext) -> dict[str, object]:
    """Build a scoped hold-to-rent view from prior routed module outputs.

    This is a transitional composite wrapper. It does not introduce new math;
    it packages the already-produced carry-cost and rent-stabilization outputs
    into a single hold-path payload for synthesis.
    """

    carry_cost_output = _require_prior_output(context, "carry_cost")
    rent_stabilization_output = _require_prior_output(context, "rent_stabilization")

    carry_metrics = dict(carry_cost_output.get("data", {}).get("metrics", {}) or {})
    stabilization_metrics = dict(rent_stabilization_output.get("data", {}).get("metrics", {}) or {})
    carry_summary = str(carry_cost_output.get("data", {}).get("summary") or "")
    stabilization_summary = str(rent_stabilization_output.get("data", {}).get("summary") or "")

    payload = ModulePayload(
        data={
            "module_name": "hold_to_rent",
            "summary": _join_summary(carry_summary, stabilization_summary),
            "carry_cost": {
                "summary": carry_summary,
                "metrics": carry_metrics,
                "confidence": carry_cost_output.get("confidence"),
            },
            "rent_stabilization": {
                "summary": stabilization_summary,
                "metrics": stabilization_metrics,
                "confidence": rent_stabilization_output.get("confidence"),
            },
            "hold_path_snapshot": {
                "monthly_cash_flow": carry_metrics.get("monthly_cash_flow"),
                "cap_rate": carry_metrics.get("cap_rate"),
                "rental_ease_label": stabilization_metrics.get("rental_ease_label"),
                "rental_ease_score": stabilization_metrics.get("rental_ease_score"),
                "estimated_days_to_rent": stabilization_metrics.get("estimated_days_to_rent"),
            },
        },
        confidence=_min_confidence(carry_cost_output, rent_stabilization_output),
        assumptions_used={
            "composite_from_prior_outputs": True,
            "required_prior_modules": ["carry_cost", "rent_stabilization"],
            "uses_full_engine_report": False,
        },
        warnings=_merge_warnings(carry_cost_output, rent_stabilization_output),
    )
    return payload.model_dump()


def _require_prior_output(context: ExecutionContext, module_name: str) -> dict[str, Any]:
    output = context.get_module_output(module_name)
    if not isinstance(output, dict):
        raise ValueError(
            f"Module '{module_name}' must run before hold_to_rent so its scoped output is available."
        )
    return output


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


def _join_summary(*parts: str) -> str:
    values = [part.strip() for part in parts if str(part).strip()]
    return " ".join(values)


__all__ = ["run_hold_to_rent"]
