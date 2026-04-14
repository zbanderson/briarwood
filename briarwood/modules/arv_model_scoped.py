from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.routing_schema import ModulePayload


def run_arv_model(context: ExecutionContext) -> dict[str, object]:
    """Build a scoped after-repair value (ARV) view from prior module outputs.

    This is a composite wrapper that reads the already-produced valuation and
    renovation-impact outputs to synthesize an ARV snapshot for synthesis.
    It does not introduce new valuation math — it packages existing results
    into a single ARV-focused payload.
    """

    valuation_output = _require_prior_output(context, "valuation")
    renovation_output = _require_prior_output(context, "renovation_impact")

    val_data = dict(valuation_output.get("data", {}) or {})
    val_metrics = dict(val_data.get("metrics", {}) or {})
    val_summary = str(val_data.get("summary") or "")

    reno_data = dict(renovation_output.get("data", {}) or {})
    reno_metrics = dict(reno_data.get("metrics", {}) or {})
    reno_summary = str(reno_data.get("summary") or "")

    current_bcv = reno_metrics.get("current_bcv") or val_metrics.get("briarwood_current_value")
    renovated_bcv = reno_metrics.get("renovated_bcv")
    renovation_budget = reno_metrics.get("renovation_budget", 0.0)
    gross_value_creation = reno_metrics.get("gross_value_creation", 0.0)
    net_value_creation = reno_metrics.get("net_value_creation", 0.0)
    roi_pct = reno_metrics.get("roi_pct", 0.0)

    arv_summary = _build_arv_summary(
        current_bcv=current_bcv,
        renovated_bcv=renovated_bcv,
        renovation_budget=renovation_budget,
        roi_pct=roi_pct,
        reno_summary=reno_summary,
    )

    payload = ModulePayload(
        data={
            "module_name": "arv_model",
            "summary": arv_summary,
            "valuation": {
                "summary": val_summary,
                "metrics": val_metrics,
                "confidence": valuation_output.get("confidence"),
            },
            "renovation_impact": {
                "summary": reno_summary,
                "metrics": reno_metrics,
                "confidence": renovation_output.get("confidence"),
            },
            "arv_snapshot": {
                "current_bcv": current_bcv,
                "renovated_bcv": renovated_bcv,
                "renovation_budget": renovation_budget,
                "gross_value_creation": gross_value_creation,
                "net_value_creation": net_value_creation,
                "roi_pct": roi_pct,
                "condition_change": reno_metrics.get("condition_change"),
                "sqft_change": reno_metrics.get("sqft_change"),
                "comp_range_text": reno_metrics.get("comp_range_text"),
            },
        },
        confidence=_min_confidence(valuation_output, renovation_output),
        assumptions_used={
            "composite_from_prior_outputs": True,
            "required_prior_modules": ["valuation", "renovation_impact"],
            "uses_full_engine_report": False,
        },
        warnings=_merge_warnings(valuation_output, renovation_output),
    )
    return payload.model_dump()


def _build_arv_summary(
    *,
    current_bcv: float | None,
    renovated_bcv: float | None,
    renovation_budget: float | None,
    roi_pct: float | None,
    reno_summary: str,
) -> str:
    if renovated_bcv and current_bcv and renovation_budget:
        return (
            f"After-repair value estimated at ${renovated_bcv:,.0f} "
            f"(current ${current_bcv:,.0f}, budget ${renovation_budget:,.0f}, "
            f"ROI {roi_pct:.1f}%)."
        )
    if reno_summary:
        return f"ARV model based on renovation impact: {reno_summary}"
    return "ARV model could not produce a complete estimate from the available renovation and valuation outputs."


def _require_prior_output(context: ExecutionContext, module_name: str) -> dict[str, Any]:
    output = context.get_module_output(module_name)
    if not isinstance(output, dict):
        raise ValueError(
            f"Module '{module_name}' must run before arv_model so its scoped output is available."
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


__all__ = ["run_arv_model"]
