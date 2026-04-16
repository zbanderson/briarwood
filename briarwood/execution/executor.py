from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from briarwood.execution.context import ExecutionContext
from briarwood.execution.planner import ExecutionPlan
from briarwood.execution.registry import ModuleSpec
from briarwood.routing_schema import ModulePayload

MODULE_CACHE_FIELDS: dict[str, dict[str, list[str]]] = {
    # These field lists are intentionally explicit so partial reruns stay
    # inspectable. A module only invalidates on the structured inputs it
    # actually cares about in V2, not on every assumption in the run.
    "valuation": {
        "property": [
            "address",
            "town",
            "state",
            "county",
            "property_type",
            "beds",
            "baths",
            "sqft",
            "lot_size",
            "year_built",
            "stories",
            "garage_spaces",
            "purchase_price",
            "days_on_market",
            "listing_date",
            "has_back_house",
            "adu_type",
            "adu_sqft",
            "additional_units",
            "manual_comp_inputs",
        ],
        "assumptions": [],
        "market": [
            "market_history_current_value",
            "market_history_one_year_change_pct",
            "market_history_three_year_change_pct",
            "market_price_to_rent_benchmark",
        ],
    },
    "carry_cost": {
        "property": ["purchase_price", "taxes", "monthly_hoa", "sqft"],
        "assumptions": [
            "insurance",
            "down_payment_percent",
            "interest_rate",
            "loan_term_years",
            "monthly_maintenance_reserve_override",
        ],
        "market": [],
    },
    "risk_model": {
        "property": [
            "purchase_price",
            "taxes",
            "days_on_market",
            "flood_risk",
            "vacancy_rate",
            "year_built",
        ],
        "assumptions": [],
        "market": [],
    },
    "confidence": {
        "property": [
            "taxes",
            "beds",
            "baths",
            "sqft",
            "property_type",
            "source_metadata",
        ],
        "assumptions": [],
        "market": [],
    },
    "rent_stabilization": {
        "property": [
            "town",
            "state",
            "county",
            "property_type",
            "beds",
            "baths",
            "sqft",
            "days_on_market",
            "flood_risk",
        ],
        "assumptions": [
            "estimated_monthly_rent",
            "back_house_monthly_rent",
            "unit_rents",
            "vacancy_rate",
            "rent_confidence_override",
        ],
        "market": [
            "town_price_trend",
            "county_price_trend",
            "liquidity_signal",
            "scarcity_signal",
            "market_price_to_rent_benchmark",
        ],
    },
    "hold_to_rent": {
        "property": [],
        "assumptions": [
            "estimated_monthly_rent",
            "back_house_monthly_rent",
            "unit_rents",
            "vacancy_rate",
            "rent_confidence_override",
        ],
        "market": [],
    },
    "unit_income_offset": {
        "property": [
            "has_back_house",
            "adu_type",
            "adu_sqft",
            "additional_units",
            "property_type",
            "purchase_price",
        ],
        "assumptions": [
            "back_house_monthly_rent",
            "unit_rents",
            "estimated_monthly_rent",
            "vacancy_rate",
        ],
        "market": [],
    },
    "legal_confidence": {
        "property": [
            "has_back_house",
            "adu_type",
            "additional_units",
            "local_documents",
            "source_metadata",
        ],
        "assumptions": [],
        "market": ["zone_flags"],
    },
}


def validate_required_context(module_spec: ModuleSpec, context: ExecutionContext) -> None:
    """Raise when a module cannot run because required context is missing."""

    missing_keys: list[str] = []
    for key in module_spec.required_context_keys:
        value = getattr(context, key, None)
        if value in (None, ""):
            missing_keys.append(key)
            continue
        if isinstance(value, dict) and not value:
            missing_keys.append(key)

    if missing_keys:
        raise ValueError(
            f"Module '{module_spec.name}' is missing required context keys: "
            + ", ".join(missing_keys)
        )


def normalize_module_result(module_name: str, result: Any) -> dict[str, Any]:
    """Normalize one module result into a ModulePayload-compatible dict."""

    if isinstance(result, ModulePayload):
        return result.model_dump()

    if isinstance(result, dict):
        data = dict(result.get("data") or result)
        confidence = result.get("confidence")
        assumptions_used = result.get("assumptions_used") or {}
        warnings = result.get("warnings") or []
        return ModulePayload(
            data=data,
            confidence=confidence,
            assumptions_used=dict(assumptions_used),
            warnings=list(warnings),
        ).model_dump()

    raise TypeError(
        f"Module '{module_name}' returned unsupported result type: {type(result).__name__}"
    )


def build_execution_trace(
    module_name: str,
    module_spec: ModuleSpec,
    normalized_result: dict[str, Any],
    *,
    source: str = "run",
    cache_key: str | None = None,
) -> dict[str, Any]:
    """Build a compact trace row for one executed module."""

    data = normalized_result.get("data") if isinstance(normalized_result, dict) else {}
    return {
        "module": module_name,
        "depends_on": list(module_spec.depends_on),
        "required_context_keys": list(module_spec.required_context_keys),
        "confidence": normalized_result.get("confidence"),
        "warning_count": len(normalized_result.get("warnings") or []),
        "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
        "source": source,
        "cache_key": cache_key,
    }


def build_module_cache_key(
    module_name: str,
    context: ExecutionContext,
) -> str:
    """Build a lightweight per-module cache key from relevant structured inputs."""

    property_id = str(
        context.property_id
        or context.property_summary.get("property_id")
        or context.property_data.get("property_id")
        or context.property_data.get("address")
        or "unknown-property"
    )
    selected = MODULE_CACHE_FIELDS.get(module_name, {"property": [], "assumptions": [], "market": []})
    payload = {
        "property_id": property_id,
        "module_name": module_name,
        "property_inputs": {
            field: _get_property_field(context.property_data, field)
            for field in selected["property"]
        },
        "assumptions": {
            field: context.assumptions.get(field)
            for field in selected["assumptions"]
        },
        "market_context": {
            field: _get_market_field(context, field)
            for field in selected["market"]
        },
    }
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return digest


def _get_property_field(property_data: dict[str, Any], field_name: str) -> Any:
    if field_name in property_data:
        return property_data.get(field_name)
    facts = property_data.get("facts")
    if isinstance(facts, dict) and field_name in facts:
        return facts.get(field_name)
    assumptions = property_data.get("user_assumptions")
    if isinstance(assumptions, dict) and field_name in assumptions:
        return assumptions.get(field_name)
    return None


def _get_market_field(context: ExecutionContext, field_name: str) -> Any:
    if field_name in context.market_context:
        return context.market_context.get(field_name)
    market_signals = context.property_data.get("market_signals")
    if isinstance(market_signals, dict) and field_name in market_signals:
        return market_signals.get(field_name)
    if field_name == "zone_flags":
        return context.property_data.get("zone_flags") or (
            market_signals.get("zone_flags") if isinstance(market_signals, dict) else None
        )
    return None


def execute_plan(
    plan: ExecutionPlan,
    context: ExecutionContext,
    registry: dict[str, ModuleSpec],
    module_output_cache: dict[str, dict[str, Any]] | None = None,
    *,
    parallel: bool = False,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Execute only the modules in an execution plan using shared context.

    Each module runner receives the shared ``ExecutionContext`` and is expected
    to return a structured result compatible with the ModulePayload contract.

    When ``parallel=True`` (opt-in, new pipeline adapters only) independent
    modules within the same dependency level run concurrently via a thread
    pool. ``parallel=False`` preserves the legacy sequential behavior.
    """

    if parallel:
        return _execute_plan_parallel(
            plan, context, registry, module_output_cache, max_workers=max_workers
        )

    if not isinstance(plan, ExecutionPlan):
        raise TypeError("plan must be an ExecutionPlan instance.")
    if not isinstance(context, ExecutionContext):
        raise TypeError("context must be an ExecutionContext instance.")
    if not isinstance(registry, dict):
        raise TypeError("registry must be a dict[str, ModuleSpec].")

    outputs: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    rerun_modules: set[str] = set()

    for module_name in plan.ordered_modules:
        if module_name not in registry:
            raise ValueError(f"Execution plan references unknown module '{module_name}'.")

        module_spec = registry[module_name]
        validate_required_context(module_spec, context)
        runner = module_spec.runner
        if runner is None:
            raise ValueError(f"Module '{module_name}' does not define a runner.")

        cache_key = build_module_cache_key(module_name, context)
        dependency_reran = any(dependency in rerun_modules for dependency in module_spec.depends_on)
        cached_result = None if dependency_reran else (module_output_cache or {}).get(cache_key)

        if cached_result is not None:
            normalized_result = dict(cached_result)
            source = "cache"
        else:
            result = runner(context)
            normalized_result = normalize_module_result(module_name, result)
            if module_output_cache is not None:
                module_output_cache[cache_key] = dict(normalized_result)
            rerun_modules.add(module_name)
            source = "run"

        outputs[module_name] = normalized_result
        context.store_module_output(module_name, normalized_result)
        trace.append(
            build_execution_trace(
                module_name,
                module_spec,
                normalized_result,
                source=source,
                cache_key=cache_key,
            )
        )

    return {
        "outputs": outputs,
        "trace": trace,
    }


def _execute_plan_parallel(
    plan: ExecutionPlan,
    context: ExecutionContext,
    registry: dict[str, ModuleSpec],
    module_output_cache: dict[str, dict[str, Any]] | None,
    *,
    max_workers: int,
) -> dict[str, Any]:
    """Level-by-level parallel execution honoring the DAG.

    Modules at the same dependency level run concurrently. Context writes
    happen on the main thread after each level resolves, so ExecutionContext
    mutation stays single-threaded.
    """

    outputs: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    rerun_modules: set[str] = set()

    completed: set[str] = set()
    remaining = [m for m in plan.ordered_modules if m in registry]
    for m in plan.ordered_modules:
        if m not in registry:
            raise ValueError(f"Execution plan references unknown module '{m}'.")

    while remaining:
        level = [
            m for m in remaining
            if all(dep in completed for dep in registry[m].depends_on)
        ]
        if not level:
            raise ValueError("Execution stalled — unresolved module dependencies.")

        def _run_one(module_name: str) -> tuple[str, dict[str, Any], str, str]:
            module_spec = registry[module_name]
            validate_required_context(module_spec, context)
            runner = module_spec.runner
            if runner is None:
                raise ValueError(f"Module '{module_name}' does not define a runner.")
            cache_key = build_module_cache_key(module_name, context)
            dep_reran = any(d in rerun_modules for d in module_spec.depends_on)
            cached = None if dep_reran else (module_output_cache or {}).get(cache_key)
            if cached is not None:
                return module_name, dict(cached), "cache", cache_key
            result = runner(context)
            normalized = normalize_module_result(module_name, result)
            return module_name, normalized, "run", cache_key

        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            results = list(pool.map(_run_one, level))

        for module_name, normalized, source, cache_key in results:
            module_spec = registry[module_name]
            if source == "run":
                if module_output_cache is not None:
                    module_output_cache[cache_key] = dict(normalized)
                rerun_modules.add(module_name)
            outputs[module_name] = normalized
            context.store_module_output(module_name, normalized)
            trace.append(
                build_execution_trace(
                    module_name, module_spec, normalized, source=source, cache_key=cache_key,
                )
            )
            completed.add(module_name)
            remaining.remove(module_name)

    return {"outputs": outputs, "trace": trace}


__all__ = [
    "build_execution_trace",
    "build_module_cache_key",
    "execute_plan",
    "normalize_module_result",
    "validate_required_context",
]
