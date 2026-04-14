"""V2 routed runner: intent-based routing, scoped execution, and unified synthesis.

This module contains the new routing-aware analysis path that selects
modules based on user intent and produces a UnifiedIntelligenceOutput.
It falls back to the legacy engine when scoped execution is not fully
supported for the selected module set.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from briarwood.decision_engine import build_decision
from briarwood.inputs.property_loader import load_property_from_json, load_property_from_listing_text
from briarwood.intelligence_capture import (
    append_intelligence_capture,
    build_routed_capture_record,
)
from briarwood.orchestrator import run_briarwood_analysis_with_artifacts
from briarwood.schemas import AnalysisReport, PropertyInput
from briarwood.routing_schema import (
    AnalysisDepth,
    DecisionType,
    EngineOutput,
    ModuleName,
    ModulePayload,
    ParserOutput,
    RoutingDecision,
    UnifiedIntelligenceOutput,
)
from briarwood.decision_model.scoring_config import BullBaseBearSettings, RiskSettings
from briarwood.settings import CostValuationSettings

from briarwood.runner_common import (
    RoutedAnalysisResult,
    _prepare_property_input,
    validate_property_input,
)
from briarwood.runner_legacy import build_engine

logger = logging.getLogger(__name__)


ROUTING_MODULE_MAP: dict[ModuleName, tuple[str, ...]] = {
    ModuleName.VALUATION: ("current_value", "comparable_sales", "hybrid_value"),
    ModuleName.CARRY_COST: ("cost_valuation", "income_support"),
    ModuleName.RISK_MODEL: ("risk_constraints", "liquidity_signal", "market_momentum_signal"),
    ModuleName.CONFIDENCE: ("property_data_quality", "current_value", "comparable_sales"),
    ModuleName.RESALE_SCENARIO: ("bull_base_bear", "teardown_scenario"),
    ModuleName.RENTAL_OPTION: ("income_support", "rental_ease"),
    ModuleName.RENT_STABILIZATION: ("rental_ease", "town_county_outlook"),
    ModuleName.HOLD_TO_RENT: ("income_support", "rental_ease", "bull_base_bear"),
    ModuleName.RENOVATION_IMPACT: ("renovation_scenario", "value_drivers"),
    ModuleName.ARV_MODEL: ("renovation_scenario", "current_value", "comparable_sales"),
    ModuleName.MARGIN_SENSITIVITY: ("renovation_scenario", "bull_base_bear"),
    ModuleName.UNIT_INCOME_OFFSET: ("income_support", "comparable_sales"),
    ModuleName.LEGAL_CONFIDENCE: ("property_data_quality", "rental_ease"),
}


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


def _decision_type_from_recommendation(recommendation: str) -> DecisionType:
    """Map existing decision-engine labels into the routing decision contract."""

    if recommendation in {"BUY", "LEAN BUY"}:
        return DecisionType.BUY
    if recommendation in {"LEAN PASS", "AVOID"}:
        return DecisionType.PASS
    return DecisionType.MIXED


def _build_module_payload(module_name: ModuleName, report: AnalysisReport) -> ModulePayload:
    """Adapt the full report into the routing-layer module payload shape."""

    source_names = ROUTING_MODULE_MAP.get(module_name, ())
    data: dict[str, Any] = {}
    assumptions_used: dict[str, Any] = {}
    warnings: list[str] = []
    confidences: list[float] = []

    for source_name in source_names:
        result = report.module_results.get(source_name)
        if result is None:
            continue
        data[source_name] = {
            "summary": result.summary,
            "metrics": result.metrics,
            "score": result.score,
        }
        if result.confidence is not None:
            confidences.append(float(result.confidence))
        metrics = result.metrics or {}
        metric_warnings = metrics.get("warnings")
        if isinstance(metric_warnings, list):
            warnings.extend(str(item) for item in metric_warnings if item)
        metric_assumptions = metrics.get("assumptions")
        if isinstance(metric_assumptions, list) and metric_assumptions:
            assumptions_used[source_name] = metric_assumptions

    confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    deduped_warnings = list(dict.fromkeys(warnings))
    return ModulePayload(
        data=data,
        confidence=confidence,
        assumptions_used=assumptions_used,
        warnings=deduped_warnings,
    )


def _build_engine_output_for_selected_modules(
    selected_modules: list[ModuleName],
    report: AnalysisReport,
) -> EngineOutput:
    """Project the legacy full report into the routing-layer engine output."""

    outputs = {
        module_name.value: _build_module_payload(module_name, report)
        for module_name in selected_modules
    }
    return EngineOutput(outputs=outputs)


def _make_legacy_module_runner(
    property_input: PropertyInput,
    *,
    cost_settings: CostValuationSettings | None = None,
    bull_base_bear_settings: BullBaseBearSettings | None = None,
    risk_settings: RiskSettings | None = None,
):
    """Create a fallback module runner that executes the legacy engine once."""

    report_cache: dict[str, AnalysisReport] = {}

    def _runner(
        selected_modules: list[ModuleName],
        property_data: dict[str, Any],
        parser_output: ParserOutput,
    ) -> dict[str, Any]:
        del property_data, parser_output
        if "report" not in report_cache:
            engine = build_engine(
                cost_settings=cost_settings,
                bull_base_bear_settings=bull_base_bear_settings,
                risk_settings=risk_settings,
            )
            report_cache["report"] = engine.run_all(property_input)
        report = report_cache["report"]
        return _build_engine_output_for_selected_modules(
            selected_modules,
            report,
        ).model_dump()

    return _runner, report_cache


def _scoped_synthesizer(
    property_summary: dict[str, Any],
    parser_output: dict[str, Any],
    module_results: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic unified answer directly from scoped module outputs.

    Phase 5: this delegates to ``build_unified_output`` so the decision,
    stance, trust flags, and value position are all derivable from module +
    interaction trace state without an LLM.
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


def _scoped_synthesizer_legacy(
    property_summary: dict[str, Any],
    parser_output: dict[str, Any],
    module_results: dict[str, Any],
) -> dict[str, Any]:
    """Pre-Phase-5 narrative-first synthesizer (kept for comparison tests)."""

    outputs = dict(module_results.get("outputs") or {})
    valuation = outputs.get("valuation", {})
    carry_cost = outputs.get("carry_cost", {})
    risk_model = outputs.get("risk_model", {})
    confidence = outputs.get("confidence", {})
    rent_stabilization = outputs.get("rent_stabilization", {})
    hold_to_rent = outputs.get("hold_to_rent", {})
    unit_income_offset = outputs.get("unit_income_offset", {})
    legal_confidence = outputs.get("legal_confidence", {})

    parser = ParserOutput.model_validate(parser_output)
    focus_set = {str(item).strip().lower() for item in parser.question_focus}
    decision = DecisionType.MIXED
    recommendation = "Mixed. More diligence is needed before committing."

    valuation_summary = str(valuation.get("data", {}).get("summary") or "")
    carry_summary = str(carry_cost.get("data", {}).get("summary") or "")
    risk_summary = str(risk_model.get("data", {}).get("summary") or "")
    legal_summary = str(legal_confidence.get("data", {}).get("summary") or "")

    valuation_metrics = valuation.get("data", {}).get("metrics", {}) or {}
    mispricing_pct = valuation_metrics.get("mispricing_pct")
    monthly_cash_flow = (carry_cost.get("data", {}).get("metrics", {}) or {}).get("monthly_cash_flow")

    if isinstance(mispricing_pct, (int, float)) and mispricing_pct >= 0.03:
        recommendation = "Buy with measured conviction."
        decision = DecisionType.BUY
    elif isinstance(mispricing_pct, (int, float)) and mispricing_pct <= -0.10:
        recommendation = "Pass unless the basis improves."
        decision = DecisionType.PASS
    elif isinstance(monthly_cash_flow, (int, float)) and monthly_cash_flow < -2000:
        recommendation = "Mixed. The property may work only if the carry or plan improves."
        decision = DecisionType.MIXED

    if "future_income" in focus_set:
        if isinstance(monthly_cash_flow, (int, float)) and monthly_cash_flow >= 0:
            recommendation = "The rent path looks viable enough to keep underwriting."
        else:
            recommendation = "The rent path needs more proof before it can carry the decision."
    elif "what_could_go_wrong" in focus_set:
        recommendation = "The risk case is what should drive this decision right now."
    elif "where_is_value" in focus_set:
        if isinstance(mispricing_pct, (int, float)) and mispricing_pct > 0:
            recommendation = "There may be value here, but only if the basis and plan hold up."
        else:
            recommendation = "Value creation is not obvious enough yet to carry the thesis."
    elif "best_path" in focus_set:
        recommendation = "The best path depends on choosing the right strategy before committing."

    value_candidates = [
        valuation_summary,
        carry_summary if parser.analysis_depth != AnalysisDepth.SNAPSHOT else "",
        str(unit_income_offset.get("data", {}).get("summary") or ""),
        str(hold_to_rent.get("data", {}).get("summary") or ""),
    ]
    risk_candidates = [
        risk_summary,
        legal_summary,
        str(rent_stabilization.get("data", {}).get("summary") or ""),
        carry_summary if isinstance(monthly_cash_flow, (int, float)) and monthly_cash_flow < 0 else "",
    ]
    strategy_candidates = [
        str(hold_to_rent.get("data", {}).get("summary") or ""),
        str(unit_income_offset.get("data", {}).get("summary") or ""),
        valuation_summary,
        carry_summary,
    ]

    if "future_income" in focus_set:
        driver_candidates = [
            str(hold_to_rent.get("data", {}).get("summary") or ""),
            str(unit_income_offset.get("data", {}).get("summary") or ""),
            str(rent_stabilization.get("data", {}).get("summary") or ""),
            carry_summary,
        ]
        risk_candidates = [
            str(rent_stabilization.get("data", {}).get("summary") or ""),
            legal_summary,
            risk_summary,
            carry_summary,
        ]
    elif "what_could_go_wrong" in focus_set:
        driver_candidates = [risk_summary, legal_summary, carry_summary]
        risk_candidates = [risk_summary, legal_summary, str(rent_stabilization.get("data", {}).get("summary") or ""), carry_summary]
    elif "where_is_value" in focus_set:
        driver_candidates = value_candidates
    elif "best_path" in focus_set:
        driver_candidates = strategy_candidates
    else:
        driver_candidates = value_candidates

    key_value_drivers = [text for text in driver_candidates if text][:3]
    key_risks = [text for text in risk_candidates if text][:3]

    confidence_values = [
        float(item.get("confidence"))
        for item in (valuation, carry_cost, risk_model, confidence, rent_stabilization, hold_to_rent, unit_income_offset, legal_confidence)
        if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
    ]
    final_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else round(parser.confidence, 2)
    final_confidence = max(0.0, min(1.0, final_confidence))

    if "what_could_go_wrong" in focus_set and risk_summary:
        best_path = "Pressure-test the downside first and do not outrun the current risk evidence."
    elif "future_income" in focus_set:
        best_path = (
            "Treat the rent path as the gating question and verify real income durability before leaning on it."
        )
    elif "where_is_value" in focus_set:
        best_path = (
            "Only lean in if the value edge is real after basis, carry, and execution friction are all included."
        )
    else:
        best_path = _best_path_from_intent(parser, decision)

    return {
        "recommendation": recommendation,
        "decision": decision.value,
        "best_path": best_path,
        "key_value_drivers": key_value_drivers,
        "key_risks": key_risks,
        "confidence": final_confidence,
        "analysis_depth_used": parser.analysis_depth.value,
        "next_questions": list(dict.fromkeys(_next_questions_for_scoped_modules(parser, outputs)))[:3],
        "recommended_next_run": _recommended_next_run(parser),
        "supporting_facts": {
            "property_id": property_summary.get("property_id"),
            "selected_modules": sorted(outputs.keys()),
            "mispricing_pct": mispricing_pct,
            "monthly_cash_flow": monthly_cash_flow,
        },
    }


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


def _next_questions_for_decision(
    parser_output: ParserOutput,
    report: AnalysisReport,
) -> list[str]:
    """Generate a small set of high-leverage next questions from current uncertainty."""

    questions: list[str] = []
    for item in parser_output.missing_inputs:
        if item == "purchase_price":
            questions.append("What is the true all-in purchase basis after negotiation and closing costs?")
        elif item == "rent_estimate":
            questions.append("What is the most defensible rent assumption for this property as it exists today?")
        elif item == "hold_period_years":
            questions.append("What hold period are we actually underwriting here?")
        elif item == "renovation_scope":
            questions.append("What renovation scope and budget are we actually assuming?")
        elif item == "occupancy_plan":
            questions.append("Is this an owner-occupant path, a rental path, or a hybrid plan?")

    reno_result = report.module_results.get("renovation_scenario")
    if reno_result is not None and reno_result.summary and "could not" in reno_result.summary.lower():
        questions.append("What renovation inputs are missing enough to make the renovation path decision-grade?")

    if not questions:
        if parser_output.analysis_depth == AnalysisDepth.SNAPSHOT:
            questions.append("What is the next highest-conviction decision question for this property?")
        else:
            questions.append("Which unresolved assumption would most change the recommendation if verified?")
    return questions[:3]


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


def _synthesize_unified_output(
    report: AnalysisReport,
    routing_decision: RoutingDecision,
    property_summary: dict[str, Any],
    engine_output: EngineOutput,
) -> UnifiedIntelligenceOutput:
    """Build a deterministic unified-intelligence output from native modules."""

    legacy_decision = build_decision(report)
    decision = _decision_type_from_recommendation(legacy_decision.recommendation)
    parser_output = routing_decision.parser_output

    current_value = report.module_results.get("current_value")
    income_support = report.module_results.get("income_support")
    comparable_sales = report.module_results.get("comparable_sales")
    risk_constraints = report.module_results.get("risk_constraints")

    key_value_drivers = [legacy_decision.primary_reason]
    if legacy_decision.secondary_reason and "thin" not in legacy_decision.secondary_reason.lower():
        key_value_drivers.append(legacy_decision.secondary_reason)

    key_risks = list(legacy_decision.required_beliefs[:2])
    if risk_constraints is not None and risk_constraints.summary:
        key_risks.append(risk_constraints.summary)
    if parser_output.missing_inputs:
        key_risks.append(
            "Missing inputs still matter: " + ", ".join(parser_output.missing_inputs[:3]).replace("_", " ")
        )

    confidence_components = [legacy_decision.conviction, parser_output.confidence]
    if current_value is not None:
        confidence_components.append(float(current_value.confidence))
    if comparable_sales is not None:
        confidence_components.append(float(comparable_sales.confidence))
    confidence = sum(confidence_components) / len(confidence_components)
    confidence -= min(0.15, 0.05 * len(parser_output.missing_inputs))
    confidence = max(0.0, min(1.0, round(confidence, 2)))

    supporting_facts: dict[str, Any] = {
        "property_id": property_summary.get("property_id"),
        "selected_modules": [module.value for module in routing_decision.selected_modules],
    }
    if current_value is not None:
        supporting_facts["mispricing_pct"] = current_value.metrics.get("mispricing_pct")
        supporting_facts["briarwood_current_value"] = current_value.metrics.get("briarwood_current_value")
    if income_support is not None:
        supporting_facts["monthly_cash_flow"] = income_support.metrics.get("monthly_cash_flow")
        supporting_facts["income_support_ratio"] = income_support.metrics.get("income_support_ratio")
    if comparable_sales is not None:
        supporting_facts["comp_count"] = comparable_sales.metrics.get("comp_count")

    return UnifiedIntelligenceOutput(
        recommendation=legacy_decision.primary_reason,
        decision=decision,
        best_path=_best_path_from_intent(parser_output, decision),
        key_value_drivers=list(dict.fromkeys(item for item in key_value_drivers if item))[:3],
        key_risks=list(dict.fromkeys(item for item in key_risks if item))[:3],
        confidence=confidence,
        analysis_depth_used=routing_decision.analysis_depth,
        next_questions=_next_questions_for_decision(parser_output, report),
        recommended_next_run=_recommended_next_run(parser_output),
        supporting_facts=supporting_facts,
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
    """Run a routed analysis with scoped execution first and safe legacy fallback.

    The routed decision and unified answer come from the orchestrator's
    scoped-first execution flow.  When scoped execution handles all selected
    modules, the legacy engine is **not** run and ``result.report`` is None.
    The legacy engine only runs when the orchestrator falls back to it for
    modules that scoped execution cannot handle.

    *prior_context* is an optional conversation history passed through to the
    router so follow-up questions route at the right depth and focus.
    """

    validate_property_input(property_input)
    _prepare_property_input(property_input)
    property_data = property_input.to_dict()
    routing_text = _routing_user_input_from_property(property_input, user_input=user_input)
    legacy_module_runner, report_cache = _make_legacy_module_runner(
        property_input,
        cost_settings=cost_settings,
        bull_base_bear_settings=bull_base_bear_settings,
        risk_settings=risk_settings,
    )
    routed_artifacts = run_briarwood_analysis_with_artifacts(
        property_data=property_data,
        user_input=routing_text,
        llm_parser=llm_parser,
        synthesizer=_scoped_synthesizer,
        module_runner=legacy_module_runner,
        prior_context=prior_context,
    )

    routing_decision = routed_artifacts["routing_decision"]
    property_summary = routed_artifacts["property_summary"]
    unified_output = routed_artifacts["unified_output"]
    execution_mode = str(routed_artifacts["execution_mode"])
    unified_output.supporting_facts.update(
        {
            "execution_mode": execution_mode,
            "context_type": "property",
            "missing_context": False,
            "was_conditional_answer": False,
        }
    )

    # report is non-None only when the legacy module_runner was invoked as a
    # fallback during orchestration.  When scoped execution handled the full
    # module set the legacy engine never ran — and we no longer force it.
    report = report_cache.get("report")

    module_results = dict(routed_artifacts.get("module_results") or {})
    engine_output = EngineOutput.model_validate(
        {"outputs": dict(module_results.get("outputs") or {})}
    )
    append_intelligence_capture(
        build_routed_capture_record(
            question=routing_text,
            context_type="property",
            routing_decision=routing_decision.model_dump(mode="json"),
            execution_mode=execution_mode,
            unified_output=unified_output.model_dump(mode="json"),
            missing_context=False,
            was_conditional_answer=False,
        )
    )

    return RoutedAnalysisResult(
        report=report,
        routing_decision=routing_decision,
        engine_output=engine_output,
        unified_output=unified_output,
        property_summary=property_summary,
        execution_mode=execution_mode,
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
    """Run a JSON property through the legacy engine plus the new routing layer."""

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
    """Run listing-text intake through the legacy engine plus the new routing layer."""

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
    address = result.report.address if result.report else result.property_summary.get("address", str(property_source))
    lines = [
        f"Briarwood routed analysis for {address}",
        f"source: {property_source}",
        f"execution: {result.execution_mode}",
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
