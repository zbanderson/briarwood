"""Scoped composite wrapper for hybrid_value.

Canonical composite pattern (DECISIONS.md 2026-04-24 *Scoped wrapper error
contract*): this wrapper requires ``comparable_sales`` AND ``income_support``
to have produced usable prior outputs before it runs. It treats any prior whose
``mode`` is in ``{"error", "fallback"}`` as missing, matching the behavior
established by ``arv_model_scoped``.

Design note on ``prior_results`` passthrough. The legacy ``HybridValueModule.run``
accepts a ``prior_results: dict[str, ModuleResult]`` kwarg so it can skip
recomputation, but ``ExecutionContext.prior_outputs`` stores *scoped payload
dicts* (``ModulePayload.model_dump()``), not typed ``ModuleResult`` objects.
Reconstructing typed ``ModuleResult`` instances from the dict form would be
brittle and require round-tripping each payload's typed sub-schemas
(``ComparableSalesOutput``, ``IncomeAgentOutput``). Instead, after confirming
the upstream priors ran cleanly, this wrapper invokes
``HybridValueModule().run(property_input)`` **without** passing
``prior_results`` — the legacy module re-runs its comp and income deps
in-process. The duplication is acceptable because (a) the missing-priors gate
is about refusing to run when upstream is degraded, not about avoiding
redundant compute, and (b) ``ComparableSalesModule`` and ``IncomeSupportModule``
are both file-backed / deterministic under production fixtures so the cost is
modest. The tradeoff is documented here so future handoffs can revisit.
"""

from __future__ import annotations

from briarwood.execution.context import ExecutionContext
from briarwood.modules.hybrid_value import HybridValueModule
from briarwood.modules.scoped_common import (
    build_property_input_from_context,
    module_payload_from_error,
    module_payload_from_legacy_result,
    module_payload_from_missing_prior,
)

_DEGRADED_MODES = {"error", "fallback"}


def run_hybrid_value(context: ExecutionContext) -> dict[str, object]:
    """Build a scoped hybrid-value payload for primary+accessory properties.

    Composite wrapper with the canonical missing-priors contract. Reads the
    ``comparable_sales`` and ``income_support`` priors from
    ``ExecutionContext.prior_outputs`` solely to verify they ran cleanly;
    the legacy ``HybridValueModule`` re-runs them in-process on the happy
    path (see module docstring for why).

    Error contract (DECISIONS.md 2026-04-24):
    - Missing or degraded priors → ``module_payload_from_missing_prior``
      (``mode="error"``, ``confidence=None``, ``missing_inputs`` populated).
    - Internal exception during the happy path →
      ``module_payload_from_error`` (``mode="fallback"``, ``confidence=0.08``).

    Preserves the legacy module's ``is_hybrid=False`` short-circuit. When
    the subject does not screen as a hybrid property, the legacy module
    returns a structured ``ModuleResult`` with a zero-confidence payload and
    a non-hybrid narrative — this wrapper passes that through as a valid
    legacy-result payload (NOT as an error). "Not a hybrid property" is a
    legitimate product answer, not a module failure. Constraint from
    PROMOTION_PLAN.md entry 2.

    Preserved payload field names (from ``HybridValueOutput``):
    ``is_hybrid``, ``reason``, ``detected_primary_structure_type``,
    ``detected_accessory_income_type``, ``primary_house_value``,
    ``rear_income_value``, ``rear_income_method_used``,
    ``optionality_premium_value``, ``low_case_hybrid_value``,
    ``base_case_hybrid_value``, ``high_case_hybrid_value``,
    ``market_friction_discount``, ``market_feedback_adjustment``,
    ``confidence``. Readers: ``current_value``, ``risk_bar``, and
    ``value_finder`` (deprecating).
    """
    missing = _collect_missing_priors(
        context, ["comparable_sales", "income_support"]
    )
    if missing:
        return module_payload_from_missing_prior(
            module_name="hybrid_value",
            context=context,
            missing=missing,
            extra_data={
                "is_hybrid": None,
                "hybrid_decomposition": {},
            },
            assumptions_used={
                "composite_from_prior_outputs": True,
                "required_prior_modules": ["comparable_sales", "income_support"],
                "uses_full_engine_report": False,
            },
        ).model_dump()

    try:
        property_input = build_property_input_from_context(context)
        # Legacy HybridValueModule.run re-runs its comparable_sales and
        # income_support deps in-process because ExecutionContext.prior_outputs
        # holds scoped payload dicts, not typed ModuleResult objects (see
        # module docstring). Do NOT collapse the comp_is_hybrid passthrough
        # path at hybrid_value.py:118-132 — when comparable_sales already
        # performed the hybrid decomposition, the primary + rear values are
        # reused to avoid double-counting. Constraint from PROMOTION_PLAN.md
        # entry 2.
        result = HybridValueModule().run(property_input)
        assumptions_used = {
            "legacy_module": "HybridValueModule",
            "property_id": property_input.property_id,
            "composite_from_prior_outputs": True,
            "required_prior_modules": ["comparable_sales", "income_support"],
            "prior_gate_passed": True,
            "uses_full_engine_report": False,
        }
        return module_payload_from_legacy_result(
            result=result,
            context=context,
            assumptions_used=assumptions_used,
            required_fields=["sqft", "beds", "baths", "town", "state"],
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return module_payload_from_error(
            module_name="hybrid_value",
            context=context,
            summary="Hybrid decomposition unavailable — internal failure composing primary + accessory value.",
            warnings=[f"Hybrid-value fallback: {type(exc).__name__}: {exc}"],
            extra_data={"hybrid_decomposition": {}},
            assumptions_used={
                "composite_from_prior_outputs": True,
                "uses_full_engine_report": False,
                "fallback_reason": "internal_exception",
            },
            required_fields=["sqft", "beds", "baths", "town", "state"],
        ).model_dump()


def _collect_missing_priors(
    context: ExecutionContext, required: list[str]
) -> list[str]:
    """Return the subset of ``required`` that is absent OR degraded.

    Mirrors the canonical helper at ``arv_model_scoped._collect_missing_priors``.
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


__all__ = ["run_hybrid_value"]
