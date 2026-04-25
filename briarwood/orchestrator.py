from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from briarwood.execution.context import ExecutionContext
from briarwood.execution.executor import execute_plan
from briarwood.execution.macro_context import resolve_macro_context
from briarwood.execution.normalization import normalize_execution_inputs
from briarwood.execution.planner import ExecutionPlan, build_execution_plan
from briarwood.execution.registry import ModuleSpec, build_module_registry
from briarwood.interactions import InteractionTrace, run_all_bridges
from briarwood.router import RoutingError, normalize_text, route_user_input
from briarwood.routing_schema import (
    EngineOutput,
    ModuleName,
    ParserOutput,
    RoutingDecision,
    UnifiedIntelligenceOutput,
)
from briarwood.shadow_intelligence import run_shadow_intelligence

logger = logging.getLogger(__name__)


_ROUTING_DECISION_CACHE: dict[str, RoutingDecision] = {}
_MODULE_RESULTS_CACHE: dict[str, dict[str, Any]] = {}
_SYNTHESIS_OUTPUT_CACHE: dict[str, UnifiedIntelligenceOutput] = {}
_SCOPED_MODULE_OUTPUT_CACHE: dict[str, dict[str, Any]] = {}
_DEFAULT_SCOPED_REGISTRY: dict[str, ModuleSpec] | None = None

# F3: bump when the cache key shape or hashed fact set changes. Old entries
# carry the previous version in their key and silently stop matching.
_CACHE_KEY_VERSION = "v2"

# Structural property facts that must be part of the cache key: if the user
# edits any of these (e.g., corrects sqft, changes purchase_price), the
# cached routing / module / synthesis outputs are no longer valid even when
# property_id and the parser-output assumptions are unchanged.
_CACHE_KEY_PROPERTY_FACTS: tuple[str, ...] = (
    "property_type",
    "beds",
    "baths",
    "sqft",
    "lot_size",
    "year_built",
    "purchase_price",
    "taxes",
    "monthly_hoa",
    "has_back_house",
    "adu_type",
    "adu_sqft",
    "has_additional_units",
    "condition_profile",
    "capex_lane",
    "strategy_intent",
    "hold_period_years",
    "risk_tolerance",
    "days_on_market",
)


class ModuleRunner(Protocol):
    """Callable boundary for Briarwood-native module execution."""

    def __call__(
        self,
        selected_modules: list[ModuleName],
        property_data: dict[str, Any],
        parser_output: ParserOutput,
    ) -> EngineOutput | dict[str, Any]:
        ...


class Synthesizer(Protocol):
    """Callable boundary for Unified Intelligence synthesis."""

    def __call__(
        self,
        property_summary: dict[str, Any],
        parser_output: dict[str, Any],
        module_results: dict[str, Any],
    ) -> UnifiedIntelligenceOutput | dict[str, Any]:
        ...


class RoutedAnalysisArtifacts(Protocol):
    """Structured artifacts returned by the scoped-first routed orchestrator."""


def build_property_summary(property_data: dict[str, Any]) -> dict[str, Any]:
    """Build a compact synthesis-safe property summary from raw property data.

    The summary deliberately excludes raw listing text and other unbounded blobs.
    It is meant to provide enough structured context for synthesis without
    leaking raw intake payloads into the LLM boundary.
    """

    if not isinstance(property_data, dict):
        raise TypeError("property_data must be a dict.")

    allowed_fields = (
        "property_id",
        "address",
        "town",
        "state",
        "county",
        "zip_code",
        "property_type",
        "beds",
        "baths",
        "sqft",
        "lot_size",
        "year_built",
        "purchase_price",
        "taxes",
        "monthly_hoa",
        "days_on_market",
        "has_back_house",
        "adu_type",
        "adu_sqft",
        "has_additional_units",
        "condition_profile",
        "capex_lane",
        "strategy_intent",
        "hold_period_years",
        "risk_tolerance",
    )

    summary = {field: property_data.get(field) for field in allowed_fields if field in property_data}

    additional_units = property_data.get("additional_units")
    if isinstance(additional_units, list):
        summary["additional_units_count"] = len(additional_units)

    source_url = property_data.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        summary["source_url"] = source_url.strip()

    return summary


def _normalize_fact_fingerprint(property_data: Mapping[str, Any]) -> dict[str, Any]:
    """F3: project the structural property facts that must invalidate the cache.

    Numbers are coerced to float when possible so that ``3`` and ``3.0``
    collapse to the same fingerprint. ``None`` / missing fields are normalized
    to ``None`` so absence reads the same on every call.
    """

    def _coerce(value: Any) -> Any:
        if isinstance(value, bool) or value is None or isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if isinstance(value, (list, tuple)):
            return [_coerce(item) for item in value]
        if isinstance(value, Mapping):
            return {str(k): _coerce(v) for k, v in sorted(value.items())}
        return value

    return {field: _coerce(property_data.get(field)) for field in _CACHE_KEY_PROPERTY_FACTS}


def build_cache_key(
    property_data: dict[str, Any],
    parser_output: ParserOutput,
) -> str:
    """Build a lightweight cache key from stable routing and assumption inputs.

    F3: includes a hashed fingerprint of structural property facts (beds, sqft,
    taxes, etc.) and a schema version literal so edits to the property record
    or to the cache shape itself invalidate cleanly. Previously the key was
    property_id + parser assumptions only, which meant two different fact sets
    for the same property_id would collide and return stale results.
    """

    property_id = str(property_data.get("property_id") or property_data.get("address") or "unknown-property")
    assumptions = _extract_execution_assumptions(property_data, parser_output)
    fact_fingerprint = _normalize_fact_fingerprint(property_data)
    payload = {
        "_version": _CACHE_KEY_VERSION,
        "property_id": property_id,
        "intent_type": parser_output.intent_type.value,
        "analysis_depth": parser_output.analysis_depth.value,
        "question_focus": parser_output.question_focus,
        "hold_period_years": parser_output.hold_period_years,
        "occupancy_type": parser_output.occupancy_type.value,
        "exit_options": [option.value for option in parser_output.exit_options],
        "has_additional_units": parser_output.has_additional_units,
        "renovation_plan": parser_output.renovation_plan,
        "assumptions": assumptions,
        "property_facts": fact_fingerprint,
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_VERSION}:{digest}"


def _build_parse_cache_key(
    property_data: dict[str, Any],
    user_input: str,
) -> str:
    """Build a cache key for one property plus one normalized user question."""

    property_id = str(property_data.get("property_id") or property_data.get("address") or "unknown-property")
    payload = {
        "property_id": property_id,
        "user_input": normalize_text(user_input),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _validate_selected_modules(selected_modules: list[ModuleName]) -> list[ModuleName]:
    """Validate that the routing decision produced a usable module list."""

    if not selected_modules:
        raise RoutingError("Routing decision did not select any native modules.")
    invalid = [module for module in selected_modules if not isinstance(module, ModuleName)]
    if invalid:
        raise RoutingError(f"Routing decision returned invalid modules: {invalid!r}")
    return selected_modules


def _get_default_scoped_registry() -> dict[str, ModuleSpec]:
    """Build and cache the default scoped execution registry."""

    global _DEFAULT_SCOPED_REGISTRY
    if _DEFAULT_SCOPED_REGISTRY is None:
        _DEFAULT_SCOPED_REGISTRY = build_module_registry()
    return _DEFAULT_SCOPED_REGISTRY


def _module_has_scoped_runner(module_spec: ModuleSpec) -> bool:
    """Return True when a registry spec points at a real scoped runner."""

    runner = module_spec.runner
    if runner is None or not callable(runner):
        return False
    return getattr(runner, "__name__", "") != "_runner"


def supports_scoped_execution(
    selected_modules: list[ModuleName],
    registry: dict[str, ModuleSpec] | None = None,
) -> tuple[bool, ExecutionPlan | None]:
    """Return whether the routed module set is fully supported by scoped execution.

    A routed run is scoped-executable only when every selected module and every
    dependency pulled in by the planner has a concrete runner in the registry.
    """

    scoped_registry = registry or _get_default_scoped_registry()
    plan = build_execution_plan(
        [module.value if isinstance(module, ModuleName) else str(module) for module in selected_modules],
        scoped_registry,
    )
    for module_name in plan.ordered_modules:
        spec = scoped_registry.get(module_name)
        if spec is None or not _module_has_scoped_runner(spec):
            return False, plan
    return True, plan


def _build_execution_context(
    property_data: dict[str, Any],
    property_summary: dict[str, Any],
    parser_output: ParserOutput,
) -> ExecutionContext:
    """Build the shared scoped execution context for V2 module execution."""

    assumptions = _extract_execution_assumptions(property_data, parser_output)
    normalized = normalize_execution_inputs(
        property_data=property_data,
        property_summary=property_summary,
        assumptions=assumptions,
    )
    facts = dict(property_data.get("facts") or {})
    county = facts.get("county") or property_summary.get("county")
    state = facts.get("state") or property_summary.get("state")
    macro_context = resolve_macro_context(county=county, state=state) or {}
    return ExecutionContext(
        property_id=str(property_summary.get("property_id") or property_data.get("property_id") or ""),
        property_data=dict(normalized.property_data),
        property_summary=dict(property_summary),
        parser_output=parser_output.model_dump(),
        assumptions=dict(normalized.assumptions),
        market_context=dict(property_data.get("market_signals") or {}),
        comp_context=dict(property_data.get("comp_context") or {}),
        macro_context=macro_context,
        field_provenance=dict(normalized.field_provenance),
        missing_data_registry=dict(normalized.missing_data_registry),
        normalized_context=normalized.model_dump(),
    )


def _extract_execution_assumptions(
    property_data: dict[str, Any],
    parser_output: ParserOutput,
) -> dict[str, Any]:
    """Extract structured assumptions that matter for scoped reruns and synthesis."""

    property_assumptions = dict(property_data.get("user_assumptions") or {})
    values = {
        "hold_period_years": parser_output.hold_period_years,
        "occupancy_type": parser_output.occupancy_type.value,
        "exit_options": [option.value for option in parser_output.exit_options],
        "renovation_plan": parser_output.renovation_plan,
        "has_additional_units": parser_output.has_additional_units,
        "analysis_depth": parser_output.analysis_depth.value,
        "intent_type": parser_output.intent_type.value,
        "question_focus": list(parser_output.question_focus),
        "estimated_monthly_rent": property_assumptions.get("estimated_monthly_rent", property_data.get("estimated_monthly_rent")),
        "back_house_monthly_rent": property_assumptions.get("back_house_monthly_rent", property_data.get("back_house_monthly_rent")),
        "unit_rents": property_assumptions.get("unit_rents", property_data.get("unit_rents", [])),
        "insurance": property_assumptions.get("insurance", property_data.get("insurance")),
        "down_payment_percent": property_assumptions.get("down_payment_percent", property_data.get("down_payment_percent")),
        "interest_rate": property_assumptions.get("interest_rate", property_data.get("interest_rate")),
        "loan_term_years": property_assumptions.get("loan_term_years", property_data.get("loan_term_years")),
        "vacancy_rate": property_assumptions.get("vacancy_rate", property_data.get("vacancy_rate")),
        "monthly_maintenance_reserve_override": property_assumptions.get(
            "monthly_maintenance_reserve_override",
            property_data.get("monthly_maintenance_reserve_override"),
        ),
        "repair_capex_budget": property_assumptions.get("repair_capex_budget", property_data.get("repair_capex_budget")),
        "rent_confidence_override": property_assumptions.get(
            "rent_confidence_override",
            property_data.get("rent_confidence_override"),
        ),
        "purchase_price": property_data.get("purchase_price"),
        "capex_lane": property_data.get("capex_lane"),
        "repair_capex_budget_override": property_assumptions.get(
            "repair_capex_budget_override",
            property_data.get("repair_capex_budget_override"),
        ),
    }
    return values


def _normalize_module_results(module_results: EngineOutput | dict[str, Any]) -> dict[str, Any]:
    """Normalize module runner output into a synthesis-friendly dict."""

    if isinstance(module_results, EngineOutput):
        return {
            "outputs": {
                name: payload.model_dump()
                for name, payload in module_results.outputs.items()
            }
        }
    if isinstance(module_results, dict):
        return module_results
    raise TypeError("module_runner must return an EngineOutput or dict.")


def _sanitize_for_synthesis(value: Any) -> Any:
    """Remove unbounded raw text fields before anything reaches synthesis."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in {
                "raw_text",
                "cleaned_text",
                "listing_text",
                "listing_description",
                "full_listing_text",
                "raw_listing_text",
                "raw_comp_dump",
                "full_notes",
            }:
                continue
            sanitized[key] = _sanitize_for_synthesis(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_synthesis(item) for item in value]
    return value


def _compact_module_results_for_synthesis(module_results: dict[str, Any]) -> dict[str, Any]:
    """Keep synthesis inputs bounded to structured module outputs only."""

    return _sanitize_for_synthesis(module_results)


def _normalize_synthesis_output(
    synthesis_output: UnifiedIntelligenceOutput | dict[str, Any],
) -> UnifiedIntelligenceOutput:
    """Normalize synthesizer output into the canonical final contract."""

    if isinstance(synthesis_output, UnifiedIntelligenceOutput):
        return synthesis_output
    if isinstance(synthesis_output, dict):
        return UnifiedIntelligenceOutput.model_validate(synthesis_output)
    raise TypeError("synthesizer must return a UnifiedIntelligenceOutput or dict.")


def _has_property_context(property_summary: dict[str, Any]) -> bool:
    """Return True when the run is anchored to a specific property or location."""

    address = str(property_summary.get("address") or "").strip()
    town = str(property_summary.get("town") or "").strip()
    state = str(property_summary.get("state") or "").strip()
    return bool(address) or bool(town and state)


def _text_has_location_reference(user_input: str) -> bool:
    """Return True when the user text itself includes some location anchor."""

    normalized = normalize_text(user_input)
    patterns = (
        r"\b\d{1,6}\s+[a-z0-9.\-]+\s+(street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|place|pl|way|blvd)\b",
        r"\bin\s+[a-z]+(?:\s+[a-z]+){0,2},?\s+[A-Z]{2}\b",
        r"\b(in|around|near)\s+[a-z]+(?:\s+[a-z]+){0,2}\b",
    )
    return any(re.search(pattern, user_input, re.IGNORECASE) for pattern in patterns) or any(
        token in normalized for token in ("this property in", "house in", "home in", "deal in")
    )


def _validate_routing_context(property_summary: dict[str, Any], user_input: str) -> None:
    """Fail fast when a conversational question has no property or location anchor."""

    if _has_property_context(property_summary):
        return
    if _text_has_location_reference(user_input):
        return
    raise ValueError(
        "Conversational routing requires a property or location context. "
        "Provide a property input with address/town/state or ask about a specific location."
    )


def run_briarwood_analysis(
    property_data: dict[str, Any],
    user_input: str,
    llm_parser: Callable[[str], ParserOutput] | None = None,
    synthesizer: Synthesizer | None = None,
    scoped_registry: dict[str, ModuleSpec] | None = None,
    prior_context: list[dict[str, object]] | None = None,
    shadow_llm: Any | None = None,
) -> UnifiedIntelligenceOutput:
    """Return only the unified output from the full routed analysis flow."""

    artifacts = run_briarwood_analysis_with_artifacts(
        property_data=property_data,
        user_input=user_input,
        llm_parser=llm_parser,
        synthesizer=synthesizer,
        scoped_registry=scoped_registry,
        prior_context=prior_context,
        shadow_llm=shadow_llm,
    )
    return artifacts["unified_output"]


def run_briarwood_analysis_with_artifacts(
    property_data: dict[str, Any],
    user_input: str,
    llm_parser: Callable[[str], ParserOutput] | None = None,
    synthesizer: Synthesizer | None = None,
    scoped_registry: dict[str, ModuleSpec] | None = None,
    prior_context: list[dict[str, object]] | None = None,
    shadow_llm: Any | None = None,
) -> dict[str, Any]:
    """Run Briarwood's routed analysis flow through scoped execution.

    Flow:
    1. Route the user question into a structured routing decision
    2. Validate selected native modules
    3. Execute scoped plan through planner + executor
    4. Build a compact property summary for synthesis
    5. Call the injected synthesizer
    6. Return canonical unified intelligence output

    *prior_context* is an optional list of conversation history entries passed
    through to the router for smarter depth and focus decisions on follow-ups.
    """

    if not isinstance(property_data, dict):
        raise TypeError("property_data must be a dict.")
    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError("user_input must be a non-empty string.")
    if synthesizer is None:
        raise ValueError(
            "synthesizer is required. Pass a callable that converts structured module results "
            "into Unified Intelligence output."
        )

    property_summary = build_property_summary(property_data)
    _validate_routing_context(property_summary, user_input)
    parse_cache_key = _build_parse_cache_key(property_summary, user_input)
    routing_decision = _ROUTING_DECISION_CACHE.get(parse_cache_key)
    if routing_decision is None:
        routing_decision = route_user_input(
            user_input=user_input,
            llm_parser=llm_parser,
            prior_context=prior_context,
        )
        _ROUTING_DECISION_CACHE[parse_cache_key] = routing_decision

    selected_modules = _validate_selected_modules(routing_decision.selected_modules)
    scoped_supported, execution_plan = supports_scoped_execution(
        selected_modules,
        registry=scoped_registry,
    )
    if not scoped_supported or execution_plan is None:
        raise RoutingError(
            "Scoped execution registry does not cover the selected module set: "
            f"{[module.value for module in selected_modules]!r}. "
            "Every routable module must have a scoped runner."
        )

    analysis_cache_key = build_cache_key(
        property_summary,
        routing_decision.parser_output,
    )

    cached_output = _SYNTHESIS_OUTPUT_CACHE.get(analysis_cache_key)
    if cached_output is not None:
        cached_module_results = _MODULE_RESULTS_CACHE.get(analysis_cache_key, {})
        shadow = run_shadow_intelligence(
            user_input=user_input,
            selected_modules=[module.value for module in selected_modules],
            parser_output=routing_decision.parser_output.model_dump(),
            module_results=cached_module_results,
            unified_output=cached_output,
            llm=shadow_llm,
            registry=scoped_registry,
        )
        return {
            "routing_decision": routing_decision,
            "property_summary": property_summary,
            "module_results": cached_module_results,
            "unified_output": cached_output,
            "shadow_intelligence": shadow.model_dump(mode="json") if shadow else None,
        }

    module_results = _MODULE_RESULTS_CACHE.get(analysis_cache_key)
    if module_results is None:
        logger.info(
            "Running scoped execution path for property_id=%s modules=%s",
            property_summary.get("property_id") or property_summary.get("address"),
            execution_plan.ordered_modules,
        )
        execution_context = _build_execution_context(
            property_data,
            property_summary,
            routing_decision.parser_output,
        )
        module_results_raw = execute_plan(
            execution_plan,
            execution_context,
            scoped_registry or _get_default_scoped_registry(),
            module_output_cache=_SCOPED_MODULE_OUTPUT_CACHE,
        )
        module_results = _compact_module_results_for_synthesis(
            _normalize_module_results(module_results_raw)
        )
        _MODULE_RESULTS_CACHE[analysis_cache_key] = module_results

    # Phase 4: run the interaction layer between module execution and synthesis.
    # Bridges consume the full (uncompacted) module results and emit an
    # InteractionTrace that synthesis can reason over in Phase 5.
    interaction_trace: InteractionTrace = run_all_bridges(module_results)
    interaction_trace_dict = interaction_trace.to_dict()

    # Phase 5: expose the interaction trace to the synthesizer via a reserved
    # key inside module_results. This keeps the synthesizer Protocol signature
    # stable while letting structured synthesizers consult the trace.
    module_results_for_synth = dict(module_results)
    module_results_for_synth["__interaction_trace__"] = interaction_trace_dict

    synthesis_output_raw = synthesizer(
        property_summary,
        routing_decision.parser_output.model_dump(),
        module_results_for_synth,
    )
    synthesis_output = _normalize_synthesis_output(synthesis_output_raw)
    _SYNTHESIS_OUTPUT_CACHE[analysis_cache_key] = synthesis_output
    shadow = run_shadow_intelligence(
        user_input=user_input,
        selected_modules=[module.value for module in selected_modules],
        parser_output=routing_decision.parser_output.model_dump(),
        module_results=module_results,
        unified_output=synthesis_output,
        llm=shadow_llm,
        registry=scoped_registry,
    )
    return {
        "routing_decision": routing_decision,
        "property_summary": property_summary,
        "module_results": module_results,
        "interaction_trace": interaction_trace_dict,
        "unified_output": synthesis_output,
        "shadow_intelligence": shadow.model_dump(mode="json") if shadow else None,
    }


__all__ = [
    "ModuleRunner",
    "Synthesizer",
    "build_cache_key",
    "build_property_summary",
    "run_briarwood_analysis",
    "run_briarwood_analysis_with_artifacts",
    "supports_scoped_execution",
]
