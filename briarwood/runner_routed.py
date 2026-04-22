"""Routed runner: intent-based routing, scoped execution, and unified synthesis.

This module hosts the routing-aware analysis path that selects modules based
on user intent and delegates synthesis to ``briarwood.synthesis.build_unified_output``.
All module execution runs through the scoped registry — every routable module
has a concrete scoped runner.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from briarwood.inputs.property_loader import load_property_from_json, load_property_from_listing_text
from briarwood.intelligence_capture import (
    append_intelligence_capture,
    build_routed_capture_record,
)
from briarwood.orchestrator import run_briarwood_analysis_with_artifacts
from briarwood.pipeline.triage import (
    compute_contribution_map_from_outputs,
    load_model_weights,
)
from briarwood.schemas import PropertyInput
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionType,
    EngineOutput,
    ParserOutput,
)
from briarwood.decision_model.scoring_config import BullBaseBearSettings, RiskSettings
from briarwood.settings import CostValuationSettings

from briarwood.runner_common import (
    RoutedAnalysisResult,
    _prepare_property_input,
    validate_property_input,
)

logger = logging.getLogger(__name__)


def _extract_model_confidences(
    module_outputs: dict[str, Any],
) -> dict[str, float | None]:
    """Collect per-module confidence values from raw module outputs.

    Preserves ``None`` explicitly so downstream eval can distinguish between
    a module that never ran and one that ran but declined to emit confidence.
    """

    confidences: dict[str, float | None] = {}
    for name, payload in (module_outputs or {}).items():
        if not isinstance(payload, dict):
            continue
        conf = payload.get("confidence")
        if isinstance(conf, (int, float)):
            confidences[name] = float(conf)
        else:
            confidences[name] = None
    return confidences


def _routing_user_input_from_property(
    property_input: PropertyInput,
    *,
    user_input: str | None = None,
) -> str:
    """Build a compact routing-oriented prompt from structured property assumptions.

    This keeps existing fixed paths compatible with the new routing contract
    without sending raw listing text or large note dumps into the parser.
    """

    if user_input and user_input.strip():
        return user_input.strip()

    parts: list[str] = ["Should I buy this property?"]
    occupancy = getattr(property_input, "occupancy_strategy", None)
    if occupancy is not None:
        if occupancy.value == "owner_occupy_partial":
            parts.append("We may live in part of it and rent the rest.")
        elif occupancy.value == "owner_occupy_full":
            parts.append("We may live here as an owner occupant.")
        elif occupancy.value == "full_rental":
            parts.append("This may be an investment rental.")

    if getattr(property_input, "hold_period_years", None) is not None:
        parts.append(f"Hold period is about {property_input.hold_period_years} years.")
    if getattr(property_input, "estimated_monthly_rent", None) is not None or getattr(property_input, "unit_rents", None):
        parts.append("Future rental income matters.")
    if getattr(property_input, "back_house_monthly_rent", None) is not None or getattr(property_input, "has_back_house", None):
        parts.append("There may be a back house or additional unit that could offset payment.")
    if getattr(property_input, "renovation_scenario", None):
        parts.append("Renovation scenario is enabled.")
    if getattr(property_input, "teardown_scenario", None):
        parts.append("Redevelopment scenario is enabled.")
    if getattr(property_input, "strategy_intent", None):
        parts.append(f"Strategy intent: {property_input.strategy_intent}.")
    return " ".join(parts)


def _scoped_synthesizer(
    property_summary: dict[str, Any],
    parser_output: dict[str, Any],
    module_results: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic unified answer directly from scoped module outputs.

    Delegates to ``build_unified_output`` so the decision, stance, trust flags,
    and value position are all derivable from module + interaction trace state
    without an LLM.
    """

    from briarwood.synthesis import build_unified_output

    interaction_trace = module_results.get("__interaction_trace__") or {}
    module_results_only = {
        k: v for k, v in module_results.items() if k != "__interaction_trace__"
    }
    return build_unified_output(
        property_summary=property_summary,
        parser_output=parser_output,
        module_results=module_results_only,
        interaction_trace=interaction_trace,
    )


def _next_questions_for_scoped_modules(
    parser_output: ParserOutput,
    outputs: dict[str, Any],
) -> list[str]:
    """Generate a few next questions without depending on a full legacy report."""

    questions: list[str] = []
    for item in parser_output.missing_inputs:
        if item == "rent_estimate":
            questions.append("What is the most defensible rent assumption for this property?")
        elif item == "hold_period_years":
            questions.append("What hold period are we actually underwriting here?")
        elif item == "purchase_price":
            questions.append("What is the true all-in basis after negotiation and closing costs?")
    if "legal_confidence" in outputs:
        questions.append("What source-backed zoning or local document evidence can confirm the extra-unit path?")
    if "hold_to_rent" in outputs:
        questions.append("How durable is the rent path if rents soften or leasing takes longer than expected?")
    if not questions:
        questions.append("Which unresolved assumption would most change the recommendation if verified?")
    return questions


def _recommended_next_run(parser_output: ParserOutput) -> str | None:
    """Suggest the next routing pass when a deeper answer would be useful."""

    if parser_output.analysis_depth == AnalysisDepth.SNAPSHOT:
        return "decision"
    if parser_output.analysis_depth == AnalysisDepth.DECISION:
        return "scenario"
    if parser_output.analysis_depth == AnalysisDepth.SCENARIO and parser_output.renovation_plan:
        return "deep_dive"
    return None


def _best_path_from_intent(
    parser_output: ParserOutput,
    decision: DecisionType,
) -> str:
    """Turn routed intent into an action-oriented best-path recommendation."""

    if parser_output.intent_type.value == "owner_occupant_then_rent":
        return (
            "Owner-occupy first, then verify the rent-conversion path before committing to a longer hold."
            if decision != DecisionType.PASS
            else "Do not underwrite this as a hold-to-rent deal until the economics improve."
        )
    if parser_output.intent_type.value == "owner_occupant_short_hold":
        return (
            "Treat this as a short-hold owner-occupant path and pressure-test the resale case."
            if decision != DecisionType.PASS
            else "Pass unless the short-hold resale path becomes materially stronger."
        )
    if parser_output.intent_type.value == "renovate_then_sell":
        return (
            "Underwrite the renovation path only if margin remains strong after cost and execution friction."
            if decision != DecisionType.PASS
            else "Do not rely on the renovation-to-sale path unless basis or scope improves."
        )
    if parser_output.intent_type.value == "house_hack_multi_unit":
        return (
            "Treat the additional-unit income as an option and verify rentability before leaning on it."
            if decision != DecisionType.PASS
            else "Pass unless the extra-unit income path becomes both legal and economically durable."
        )
    return (
        "Proceed as a straight buy decision and verify the carry and evidence stack before committing."
        if decision != DecisionType.PASS
        else "Pass unless the core value and carry signals improve."
    )


def run_routed_analysis_for_property(
    property_input: PropertyInput,
    *,
    user_input: str | None = None,
    llm_parser: Any | None = None,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
    prior_context: list[dict[str, object]] | None = None,
) -> RoutedAnalysisResult:
    """Run a routed analysis through the scoped execution path.

    The routed decision and unified answer come from the orchestrator's
    scoped execution flow. Every routable module set is fully covered by
    the scoped registry; there is no legacy-engine fallback.

    *prior_context* is an optional conversation history passed through to the
    router so follow-up questions route at the right depth and focus.
    """

    del cost_settings, bull_base_bear_settings, risk_settings  # kept for API compat

    validate_property_input(property_input)
    _prepare_property_input(property_input)
    property_data = property_input.to_dict()
    routing_text = _routing_user_input_from_property(property_input, user_input=user_input)
    routed_artifacts = run_briarwood_analysis_with_artifacts(
        property_data=property_data,
        user_input=routing_text,
        llm_parser=llm_parser,
        synthesizer=_scoped_synthesizer,
        prior_context=prior_context,
    )

    routing_decision = routed_artifacts["routing_decision"]
    property_summary = routed_artifacts["property_summary"]
    unified_output = routed_artifacts["unified_output"]
    unified_output.supporting_facts.update(
        {
            "context_type": "property",
            "missing_context": False,
            "was_conditional_answer": False,
        }
    )

    module_results = dict(routed_artifacts.get("module_results") or {})
    module_outputs = dict(module_results.get("outputs") or {})
    engine_output = EngineOutput.model_validate({"outputs": module_outputs})

    import uuid as _uuid
    session_id = _uuid.uuid4().hex[:12]
    contribution_map = compute_contribution_map_from_outputs(
        module_outputs, weights=load_model_weights()
    )
    model_confidences = _extract_model_confidences(module_outputs)

    append_intelligence_capture(
        build_routed_capture_record(
            question=routing_text,
            context_type="property",
            routing_decision=routing_decision.model_dump(mode="json"),
            unified_output=unified_output.model_dump(mode="json"),
            missing_context=False,
            was_conditional_answer=False,
            session_id=session_id,
            contribution_map=contribution_map,
            model_confidences=model_confidences,
            explicit_signal=None,
            outcome=None,
        )
    )

    return RoutedAnalysisResult(
        routing_decision=routing_decision,
        engine_output=engine_output,
        unified_output=unified_output,
        property_summary=property_summary,
    )


def run_routed_report(
    property_path: str | Path,
    *,
    user_input: str | None = None,
    llm_parser: Any | None = None,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
    prior_context: list[dict[str, object]] | None = None,
) -> RoutedAnalysisResult:
    """Run a JSON property through the routing layer and scoped execution."""

    property_input = load_property_from_json(property_path)
    return run_routed_analysis_for_property(
        property_input,
        user_input=user_input,
        llm_parser=llm_parser,
        cost_settings=cost_settings,
        bull_base_bear_settings=bull_base_bear_settings,
        risk_settings=risk_settings,
        prior_context=prior_context,
    )


def run_routed_report_from_listing_text(
    listing_text: str,
    *,
    property_id: str = "listing-intake",
    source_url: str | None = None,
    user_input: str | None = None,
    llm_parser: Any | None = None,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
    prior_context: list[dict[str, object]] | None = None,
) -> RoutedAnalysisResult:
    """Run listing-text intake through the routing layer and scoped execution."""

    property_input = load_property_from_listing_text(
        listing_text,
        property_id=property_id,
        source_url=source_url,
    )
    return run_routed_analysis_for_property(
        property_input,
        user_input=user_input,
        llm_parser=llm_parser,
        cost_settings=cost_settings,
        bull_base_bear_settings=bull_base_bear_settings,
        risk_settings=risk_settings,
        prior_context=prior_context,
    )


def format_routed_analysis(result: RoutedAnalysisResult, property_source: str | Path) -> str:
    """Render a concise decision-first text view for routed CLI runs."""

    unified = result.unified_output
    address = result.property_summary.get("address", str(property_source))
    lines = [
        f"Briarwood routed analysis for {address}",
        f"source: {property_source}",
        "",
        f"Recommendation: {unified.recommendation}",
        f"Decision: {unified.decision.value}",
        f"Best path: {unified.best_path}",
        f"Confidence: {unified.confidence:.0%}",
        f"Analysis depth: {unified.analysis_depth_used.value}",
        "",
    ]
    if unified.key_risks:
        lines.append("Key risks:")
        lines.extend(f"- {item}" for item in unified.key_risks[:3])
        lines.append("")
    if unified.next_questions:
        lines.append("Next questions:")
        lines.extend(f"- {item}" for item in unified.next_questions[:3])
        lines.append("")
    if unified.recommended_next_run:
        lines.append(f"Recommended next run: {unified.recommended_next_run}")
        lines.append("")
    lines.append(f"Selected modules: {', '.join(module.value for module in result.routing_decision.selected_modules)}")
    return "\n".join(lines)
