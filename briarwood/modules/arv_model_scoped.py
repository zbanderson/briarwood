from __future__ import annotations

from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.modules.scoped_common import (
    module_payload_from_error,
    module_payload_from_missing_prior,
)
from briarwood.routing_schema import ModulePayload

_DEGRADED_MODES = {"error", "fallback"}


def run_arv_model(context: ExecutionContext) -> dict[str, object]:
    """Build a scoped after-repair value (ARV) view from prior module outputs.

    This is a composite wrapper that reads the already-produced valuation and
    renovation-impact outputs to synthesize an ARV snapshot for synthesis.
    It does not introduce new valuation math — it packages existing results
    into a single ARV-focused payload.

    Error contract (DECISIONS.md 2026-04-24): on missing or degraded priors
    returns ``module_payload_from_missing_prior`` (``mode="error"``,
    ``confidence=None``, ``extra_data={"arv_snapshot": {}}``). On internal
    exceptions returns ``module_payload_from_error`` (``mode="fallback"``,
    ``confidence=0.08``).
    """

    missing = _collect_missing_priors(context, ["valuation", "renovation_impact"])
    if missing:
        return module_payload_from_missing_prior(
            module_name="arv_model",
            context=context,
            missing=missing,
            extra_data={"arv_snapshot": {}},
            assumptions_used={
                "composite_from_prior_outputs": True,
                "uses_full_engine_report": False,
            },
        ).model_dump()

    valuation_output = context.get_module_output("valuation") or {}
    renovation_output = context.get_module_output("renovation_impact") or {}

    try:
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
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="arv_model",
            context=context,
            summary="ARV model unavailable — internal failure composing the ARV snapshot.",
            warnings=[f"Arv-model fallback: {type(exc).__name__}: {exc}"],
            extra_data={"arv_snapshot": {}},
            assumptions_used={
                "composite_from_prior_outputs": True,
                "uses_full_engine_report": False,
                "fallback_reason": "internal_exception",
            },
        ).model_dump()


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


def _collect_missing_priors(
    context: ExecutionContext, required: list[str]
) -> list[str]:
    """Return the subset of ``required`` that is absent OR degraded.

    A prior is treated as missing when its output is not a dict, or when its
    ``mode`` is in ``{"error", "fallback"}`` — in those cases the upstream
    wrapper already produced a no-signal payload, so the composite cannot
    safely compose on top of it.
    """

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
