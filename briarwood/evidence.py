from __future__ import annotations

from dataclasses import dataclass, field

from briarwood.schemas import (
    AnalysisReport,
    EvidenceMode,
    InputCoverageStatus,
    PropertyInput,
    SectionEvidence,
    SourceCoverageItem,
)


def build_section_evidence(
    property_input: PropertyInput,
    *,
    categories: list[str],
    notes: list[str] | None = None,
    extra_missing_inputs: list[str] | None = None,
    extra_estimated_inputs: list[str] | None = None,
) -> SectionEvidence:
    coverage_items: list[SourceCoverageItem] = [property_input.coverage_for(category) for category in categories]
    missing_inputs = [item.category for item in coverage_items if item.status == InputCoverageStatus.MISSING]
    estimated_inputs = [item.category for item in coverage_items if item.status == InputCoverageStatus.ESTIMATED]
    if extra_missing_inputs:
        for item in extra_missing_inputs:
            if item not in missing_inputs:
                missing_inputs.append(item)
    if extra_estimated_inputs:
        for item in extra_estimated_inputs:
            if item not in estimated_inputs:
                estimated_inputs.append(item)
    evidence_mode = EvidenceMode.PUBLIC_RECORD
    if property_input.source_metadata:
        if isinstance(property_input.source_metadata, dict):
            raw_mode = property_input.source_metadata.get("evidence_mode")
            if raw_mode:
                evidence_mode = raw_mode if isinstance(raw_mode, EvidenceMode) else EvidenceMode(str(raw_mode))
        else:
            evidence_mode = property_input.source_metadata.evidence_mode
    return SectionEvidence(
        evidence_mode=evidence_mode,
        categories=coverage_items,
        major_missing_inputs=missing_inputs,
        estimated_inputs=estimated_inputs,
        notes=list(notes or []),
    )


@dataclass(slots=True)
class ConfidenceComponent:
    key: str
    label: str
    confidence: float
    weight: float
    reason: str


@dataclass(slots=True)
class ConfidenceBreakdown:
    overall_confidence: float
    components: list[ConfidenceComponent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MetricInputStatus:
    key: str
    label: str
    status: str
    facts_used: list[str] = field(default_factory=list)
    user_inputs_used: list[str] = field(default_factory=list)
    assumptions_used: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    confidence_impact: str = ""
    prompt_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CriticalAssumptionStatus:
    key: str
    label: str
    status: str  # confirmed / estimated / missing
    value: str
    source_label: str
    note: str = ""
    affected_components: list[str] = field(default_factory=list)


CONFIDENCE_COMPONENT_WEIGHTS: dict[str, float] = {
    "rent": 0.30,
    "capex": 0.25,
    "market": 0.25,
    "liquidity": 0.20,
}


def _is_known_detail(value: object) -> bool:
    return value is not None and value != ""


def has_known_optionality_detail(property_input: PropertyInput) -> bool:
    return any(
        _is_known_detail(getattr(property_input, field_name))
        for field_name in ("has_back_house", "adu_type", "adu_sqft", "has_basement", "garage_spaces", "garage_type")
    )


def compute_confidence_breakdown(report: AnalysisReport) -> ConfidenceBreakdown:
    property_input = report.property_input
    metric_statuses = compute_metric_input_statuses(report)
    critical_assumptions = compute_critical_assumption_statuses(report)
    status_map = {status.key: status for status in metric_statuses}
    components = [
        _rent_confidence_component(report, property_input),
        _capex_confidence_component(property_input),
        _market_confidence_component(report),
        _liquidity_confidence_component(report, property_input),
    ]
    components = _apply_metric_status_caps(components, status_map)
    components = _apply_assumption_quality_caps(components, critical_assumptions)
    components = _apply_town_context_caps(components, property_input)
    total_weight = sum(component.weight for component in components if component.confidence is not None)
    if total_weight <= 0:
        return ConfidenceBreakdown(overall_confidence=0.0, components=components, notes=[])
    overall_confidence = round(
        sum(component.confidence * component.weight for component in components) / total_weight,
        2,
    )
    notes = [
        f"{component.label} confidence is still below 70%: {component.reason}"
        for component in components
        if component.confidence < 0.70
    ]
    notes.extend(
        f"{status.label} is {status.status.replace('_', ' ')} because {status.confidence_impact}"
        for status in metric_statuses
        if status.status == "unresolved"
    )
    return ConfidenceBreakdown(
        overall_confidence=overall_confidence,
        components=components,
        notes=notes[:4],
    )


def compute_critical_assumption_statuses(report: AnalysisReport) -> list[CriticalAssumptionStatus]:
    property_input = report.property_input
    if property_input is None:
        return []

    income_module = report.module_results.get("income_support")
    income_metrics = income_module.metrics if income_module is not None else {}
    assumptions = property_input.user_assumptions
    statuses: list[CriticalAssumptionStatus] = []

    def _status_from_coverage(category: str) -> str:
        coverage = property_input.coverage_for(category).status
        if coverage in {InputCoverageStatus.SOURCED, InputCoverageStatus.USER_SUPPLIED}:
            return "confirmed"
        if coverage is InputCoverageStatus.ESTIMATED:
            return "estimated"
        return "missing"

    rent_source_type = str(income_metrics.get("rent_source_type") or "missing")
    rent_value = income_metrics.get("monthly_rent_estimate") or income_metrics.get("effective_monthly_rent")
    if assumptions and assumptions.unit_rents:
        rent_status = "confirmed"
        rent_value_text = f"${sum(assumptions.unit_rents):,.0f}/mo"
        rent_source = "User Confirmed"
        rent_note = "Unit-level rent schedule is driving the underwriting."
    elif assumptions and assumptions.estimated_monthly_rent is not None:
        rent_status = "confirmed"
        rent_value_text = f"${assumptions.estimated_monthly_rent:,.0f}/mo"
        rent_source = "User Confirmed"
        rent_note = "User-entered rent is driving the underwriting."
    elif rent_source_type == "provided" and rent_value is not None:
        rent_status = "confirmed"
        rent_value_text = f"${rent_value:,.0f}/mo"
        rent_source = "Property Input"
        rent_note = "Property-level rent was supplied directly."
    elif rent_source_type == "estimated" and rent_value is not None:
        rent_status = "estimated"
        rent_value_text = f"${rent_value:,.0f}/mo"
        rent_source = "Model Estimated"
        rent_note = "Rent is still estimated from market context rather than confirmed."
    else:
        rent_status = "missing"
        rent_value_text = "Missing"
        rent_source = "Missing"
        rent_note = "No property-level rent assumption is available."
    statuses.append(
        CriticalAssumptionStatus(
            key="rent",
            label="Rent",
            status=rent_status,
            value=rent_value_text,
            source_label=rent_source,
            note=rent_note,
            affected_components=["rent", "liquidity"],
        )
    )

    taxes_status = _status_from_coverage("taxes")
    statuses.append(
        CriticalAssumptionStatus(
            key="taxes",
            label="Taxes",
            status=taxes_status if property_input.taxes is not None else "missing",
            value=f"${property_input.taxes:,.0f}/yr" if property_input.taxes is not None else "Missing",
            source_label=(
                "User Confirmed"
                if property_input.coverage_for("taxes").status is InputCoverageStatus.USER_SUPPLIED
                else "Sourced"
                if property_input.coverage_for("taxes").status is InputCoverageStatus.SOURCED
                else "Model Estimated"
                if property_input.coverage_for("taxes").status is InputCoverageStatus.ESTIMATED
                else "Missing"
            ),
            note="Property taxes feed carry, downside burden, and investor return metrics.",
            affected_components=["rent"],
        )
    )

    insurance_status = "missing"
    insurance_source = "Missing"
    if property_input.insurance is not None:
        if assumptions and assumptions.insurance is not None:
            insurance_status = "confirmed"
            insurance_source = "User Confirmed"
        elif _status_from_coverage("insurance_estimate") == "estimated" or "insurance" in getattr(property_input, "defaults_applied", {}):
            insurance_status = "estimated"
            insurance_source = "Model Estimated"
        else:
            insurance_status = "confirmed"
            insurance_source = "Sourced"
    statuses.append(
        CriticalAssumptionStatus(
            key="insurance",
            label="Insurance",
            status=insurance_status,
            value=f"${property_input.insurance:,.0f}/yr" if property_input.insurance is not None else "Missing",
            source_label=insurance_source,
            note="Insurance feeds monthly carry and downside support.",
            affected_components=["rent"],
        )
    )

    financing_fields = {
        "down_payment_percent": property_input.down_payment_percent,
        "interest_rate": property_input.interest_rate,
        "loan_term_years": property_input.loan_term_years,
    }
    financing_present = sum(value is not None for value in financing_fields.values())
    financing_status = "confirmed" if financing_present == 3 else "estimated" if financing_present > 0 else "missing"
    financing_source = "User Confirmed" if financing_present > 0 else "Missing"
    statuses.extend(
        [
            CriticalAssumptionStatus(
                key="down_payment_percent",
                label="Down Payment",
                status="confirmed" if property_input.down_payment_percent is not None else "missing",
                value=f"{property_input.down_payment_percent * 100:.0f}%" if property_input.down_payment_percent is not None else "Missing",
                source_label="User Confirmed" if property_input.down_payment_percent is not None else "Missing",
                note="Down payment affects leverage, cash invested, and monthly carry.",
                affected_components=["rent"],
            ),
            CriticalAssumptionStatus(
                key="interest_rate",
                label="Interest Rate",
                status="confirmed" if property_input.interest_rate is not None else "missing",
                value=f"{property_input.interest_rate * 100:.2f}%" if property_input.interest_rate is not None else "Missing",
                source_label="User Confirmed" if property_input.interest_rate is not None else "Missing",
                note="Interest rate drives debt service and cash flow.",
                affected_components=["rent"],
            ),
            CriticalAssumptionStatus(
                key="loan_term_years",
                label="Loan Term",
                status="confirmed" if property_input.loan_term_years is not None else "missing",
                value=f"{property_input.loan_term_years} years" if property_input.loan_term_years is not None else "Missing",
                source_label="User Confirmed" if property_input.loan_term_years is not None else "Missing",
                note="Loan term shapes monthly carry and amortization.",
                affected_components=["rent"],
            ),
            CriticalAssumptionStatus(
                key="financing",
                label="Financing",
                status=financing_status,
                value=(
                    " / ".join(
                        [
                            f"{property_input.down_payment_percent * 100:.0f}% down" if property_input.down_payment_percent is not None else "down payment missing",
                            f"{property_input.interest_rate * 100:.2f}% rate" if property_input.interest_rate is not None else "rate missing",
                            f"{property_input.loan_term_years}y term" if property_input.loan_term_years is not None else "term missing",
                        ]
                    )
                ),
                source_label=financing_source,
                note="Financing is only fully underwritten when all three fields are present.",
                affected_components=["rent"],
            ),
        ]
    )

    condition_status = "missing"
    condition_source = "Missing"
    if property_input.condition_profile:
        if bool(getattr(property_input, "condition_confirmed", False)) or bool(getattr(assumptions, "condition_profile_override", None)):
            condition_status = "confirmed"
            condition_source = "User Confirmed"
        else:
            condition_status = "estimated"
            condition_source = "Model Estimated"
    statuses.append(
        CriticalAssumptionStatus(
            key="condition_profile",
            label="Condition",
            status=condition_status,
            value=property_input.condition_profile.replace("_", " ").title() if property_input.condition_profile else "Missing",
            source_label=condition_source,
            note="Condition influences CapEx burden and renovation confidence.",
            affected_components=["capex"],
        )
    )

    capex_status = "missing"
    capex_source = "Missing"
    capex_value = "Missing"
    if property_input.repair_capex_budget is not None:
        capex_status = "confirmed"
        capex_source = "User Confirmed"
        capex_value = f"${property_input.repair_capex_budget:,.0f}"
    elif property_input.capex_lane:
        if bool(getattr(property_input, "capex_confirmed", False)) or bool(getattr(assumptions, "capex_lane_override", None)):
            capex_status = "confirmed"
            capex_source = "User Confirmed"
        else:
            capex_status = "estimated"
            capex_source = "Model Estimated"
        capex_value = property_input.capex_lane.replace("_", " ").title()
    statuses.append(
        CriticalAssumptionStatus(
            key="capex",
            label="CapEx",
            status=capex_status,
            value=capex_value,
            source_label=capex_source,
            note="CapEx should be explicit before leaning hard on value-add or downside protection.",
            affected_components=["capex"],
        )
    )

    return statuses


def compute_metric_input_statuses(report: AnalysisReport) -> list[MetricInputStatus]:
    property_input = report.property_input
    if property_input is None:
        return []

    current_value = report.module_results.get("current_value")
    income = report.module_results.get("income_support")
    liquidity = report.module_results.get("liquidity_signal")
    momentum = report.module_results.get("market_momentum_signal")
    local = report.module_results.get("local_intelligence")

    statuses = [
        _price_to_rent_status(report, property_input, income.metrics if income else {}),
        _net_monthly_cost_status(property_input, income.metrics if income else {}),
        _price_per_sqft_status(property_input, report),
        _capex_load_status(property_input),
        _liquidity_status(property_input, liquidity.metrics if liquidity else {}),
        _optionality_status(property_input, report),
        _net_opportunity_delta_status(property_input, current_value.metrics if current_value else {}),
        _market_momentum_status(report, momentum.metrics if momentum else {}, local.metrics if local else {}),
    ]
    return statuses


def infer_overall_report_confidence(property_input: PropertyInput, module_confidences: list[float]) -> float:
    if not module_confidences:
        return 0.0
    confidence = sum(module_confidences) / len(module_confidences)
    if property_input.source_metadata is None:
        return round(confidence, 2)
    if any(
        item.status == InputCoverageStatus.MISSING
        for key, item in property_input.source_metadata.source_coverage.items()
        if key in {"price_ask", "rent_estimate", "insurance_estimate", "comp_support"}
    ):
        confidence = min(confidence, 0.68)
    if any(item.status == InputCoverageStatus.ESTIMATED for item in property_input.source_metadata.source_coverage.values()):
        confidence = min(confidence, 0.76)
    return round(confidence, 2)


def _clamp_confidence(value: float) -> float:
    return round(max(0.15, min(value, 0.95)), 2)


def _module_confidence(report: AnalysisReport, module_name: str) -> float | None:
    module = report.module_results.get(module_name)
    return None if module is None else float(module.confidence)


def _rent_confidence_component(report: AnalysisReport, property_input: PropertyInput | None) -> ConfidenceComponent:
    income = report.get_module("income_support").payload
    rent_source_type = getattr(income, "rent_source_type", "missing")
    rent_confidence_override = (getattr(property_input, "rent_confidence_override", None) or "").lower() if property_input else ""
    unit_breakdown = getattr(income, "unit_breakdown", []) or []

    if rent_source_type == "manual_input":
        confidence = 0.88
        reason = "Rent confidence improved because a manual unit-rent schedule is driving the income support view."
    elif rent_source_type == "provided":
        confidence = 0.80
        reason = "Rent confidence is supported by a property-level provided rent assumption."
    elif rent_source_type == "estimated":
        confidence = 0.56
        reason = "Rent confidence remains moderate because rent is still model-estimated."
    else:
        confidence = 0.22
        reason = "Rent confidence is low because no usable rent assumption was supplied."

    if len(unit_breakdown) >= 2:
        confidence += 0.03
    if rent_confidence_override == "high" and rent_source_type in {"manual_input", "provided"}:
        confidence += 0.05
        reason = "Rent confidence improved by user-provided rent assumptions marked high confidence."
    elif rent_confidence_override == "low":
        confidence -= 0.12
        reason = "Rent confidence was reduced because the user marked rent assumptions low confidence."

    return ConfidenceComponent(
        key="rent",
        label="Rent",
        confidence=_clamp_confidence(confidence),
        weight=CONFIDENCE_COMPONENT_WEIGHTS["rent"],
        reason=reason,
    )


def _capex_confidence_component(property_input: PropertyInput | None) -> ConfidenceComponent:
    if property_input is None:
        return ConfidenceComponent(
            key="capex",
            label="CapEx",
            confidence=0.25,
            weight=CONFIDENCE_COMPONENT_WEIGHTS["capex"],
            reason="CapEx confidence is low because no property assumptions were available.",
        )

    explicit_budget = property_input.repair_capex_budget
    condition_confirmed = bool(getattr(property_input, "condition_confirmed", False))
    capex_confirmed = bool(getattr(property_input, "capex_confirmed", False))
    condition_profile = (property_input.condition_profile or "").lower()
    capex_lane = (property_input.capex_lane or "").lower()

    if explicit_budget is not None:
        confidence = 0.90
        reason = "CapEx confidence improved because an explicit repair budget replaced heuristic renovation assumptions."
        if condition_confirmed or capex_confirmed:
            confidence += 0.04
            reason = "CapEx confidence improved because an explicit repair budget was paired with user-confirmed condition assumptions."
    elif capex_confirmed and capex_lane:
        confidence = 0.82
        reason = "CapEx confidence is strong because the renovation burden was user-confirmed through a capex lane."
    elif condition_confirmed and condition_profile:
        confidence = 0.78
        reason = "CapEx confidence improved because the current condition was user-confirmed."
    elif capex_lane:
        confidence = 0.62
        reason = "CapEx confidence remains moderate because renovation burden is inferred from the capex lane."
    elif condition_profile in {"updated", "renovated", "turnkey"}:
        confidence = 0.70
        reason = "CapEx confidence is moderate because low renovation burden is implied from condition rather than an explicit budget."
    elif condition_profile:
        confidence = 0.55
        reason = "CapEx confidence remains moderate because renovation burden is inferred from condition profile only."
    else:
        confidence = 0.35
        reason = "CapEx confidence is low because renovation burden is still largely inferred."

    return ConfidenceComponent(
        key="capex",
        label="CapEx",
        confidence=_clamp_confidence(confidence),
        weight=CONFIDENCE_COMPONENT_WEIGHTS["capex"],
        reason=reason,
    )


def _market_confidence_component(report: AnalysisReport) -> ConfidenceComponent:
    weighted_modules = [
        ("market_value_history", "market history", 0.35),
        ("town_county_outlook", "town/county context", 0.35),
        ("location_intelligence", "geo benchmarking", 0.15),
        ("local_intelligence", "local development signals", 0.15),
    ]
    available: list[tuple[str, float, float]] = []
    labels: list[str] = []
    for module_name, label, weight in weighted_modules:
        confidence = _module_confidence(report, module_name)
        if confidence is None:
            continue
        available.append((module_name, confidence, weight))
        if confidence > 0:
            labels.append(label)

    if not available:
        return ConfidenceComponent(
            key="market",
            label="Market",
            confidence=0.30,
            weight=CONFIDENCE_COMPONENT_WEIGHTS["market"],
            reason="Market confidence is low because no usable market evidence modules were available.",
        )

    total_weight = sum(weight for _, _, weight in available)
    confidence = sum(value * weight for _, value, weight in available) / total_weight if total_weight else 0.0
    if {"location_intelligence", "local_intelligence"} <= {name for name, _, _ in available}:
        reason = "Market confidence uses market history, town/county context, and local/location overlays."
    elif any(name in {"location_intelligence", "local_intelligence"} for name, _, _ in available):
        reason = "Market confidence uses core market context plus one local overlay, but some place-specific evidence is still thin."
    else:
        reason = "Market confidence is mostly based on market history and town/county proxy context."

    return ConfidenceComponent(
        key="market",
        label="Market",
        confidence=_clamp_confidence(confidence),
        weight=CONFIDENCE_COMPONENT_WEIGHTS["market"],
        reason=reason,
    )


def _liquidity_confidence_component(
    report: AnalysisReport,
    property_input: PropertyInput | None,
) -> ConfidenceComponent:
    weighted_modules = [
        ("comparable_sales", 0.40),
        ("risk_constraints", 0.30),
        ("town_county_outlook", 0.20),
        ("rental_ease", 0.10),
    ]
    available = [
        (module_name, _module_confidence(report, module_name), weight)
        for module_name, weight in weighted_modules
        if _module_confidence(report, module_name) is not None
    ]
    total_weight = sum(weight for _, _, weight in available)
    confidence = (
        sum(float(value) * weight for _, value, weight in available) / total_weight
        if total_weight
        else 0.35
    )

    comparable_sales = report.get_module("comparable_sales")
    comp_count = int(comparable_sales.metrics.get("comp_count") or 0)
    dom_present = bool(property_input and property_input.days_on_market is not None)
    if comp_count >= 4:
        confidence += 0.03
    elif comp_count <= 1:
        confidence -= 0.08
    if dom_present:
        confidence += 0.04
        reason = "Liquidity confidence is supported by comparable-sale depth and observed days-on-market evidence."
    else:
        confidence -= 0.04
        reason = "Liquidity confidence remains moderate because exit evidence leans on proxy liquidity signals and limited days-on-market data."

    return ConfidenceComponent(
        key="liquidity",
        label="Liquidity",
        confidence=_clamp_confidence(confidence),
        weight=CONFIDENCE_COMPONENT_WEIGHTS["liquidity"],
        reason=reason,
    )


def _coverage_label(property_input: PropertyInput, category: str, *, fallback_label: str) -> tuple[str | None, str | None]:
    item = property_input.coverage_for(category)
    if item.status is InputCoverageStatus.SOURCED:
        return fallback_label, None
    if item.status is InputCoverageStatus.USER_SUPPLIED:
        return None, fallback_label
    return None, None


def _classify_metric_status(
    *,
    facts_used: list[str],
    user_inputs_used: list[str],
    assumptions_used: list[str],
    missing_required: list[str],
) -> str:
    if missing_required and not (facts_used or user_inputs_used or assumptions_used):
        return "unresolved"
    if missing_required and assumptions_used:
        return "estimated"
    if assumptions_used:
        return "estimated"
    if user_inputs_used:
        return "user_confirmed"
    return "fact_based"


def _price_to_rent_status(report: AnalysisReport, property_input: PropertyInput, income_metrics: dict) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    fact, user = _coverage_label(property_input, "price_ask", fallback_label="purchase price")
    if fact:
        facts_used.append(fact)
    if user:
        user_inputs_used.append(user)

    rent_source_type = str(income_metrics.get("rent_source_type") or "missing")
    if rent_source_type == "manual_input":
        user_inputs_used.append("manual unit rents")
    elif rent_source_type == "provided":
        user_inputs_used.append("provided monthly rent")
    elif rent_source_type == "estimated":
        assumptions_used.append("estimated monthly rent")
    else:
        missing_inputs.append("rent")

    if property_input.market_price_to_rent_benchmark is not None:
        facts_used.append("market price-to-rent benchmark")
    else:
        assumptions_used.append("heuristic price-to-rent benchmark")

    if property_input.purchase_price is None:
        missing_inputs.append("purchase price")

    status = _classify_metric_status(
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_required=missing_inputs,
    )
    impact = (
        "rent is missing, so price-to-rent cannot be verified"
        if "rent" in missing_inputs
        else "rent is estimated, so price-to-rent should be treated as modeled support"
        if "estimated monthly rent" in assumptions_used
        else "price-to-rent is grounded in purchase basis and property-level rent inputs"
    )
    return MetricInputStatus(
        key="price_to_rent",
        label="Price-to-Rent",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["estimated_monthly_rent", "unit_rents", "market_price_to_rent_benchmark"] if status != "fact_based" else [],
    )


def _net_monthly_cost_status(property_input: PropertyInput, income_metrics: dict) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    if property_input.purchase_price is not None:
        price_fact, price_user = _coverage_label(property_input, "price_ask", fallback_label="purchase price")
        if price_fact:
            facts_used.append(price_fact)
        if price_user:
            user_inputs_used.append(price_user)
    else:
        missing_inputs.append("purchase price")

    if property_input.taxes is not None:
        facts_used.append("taxes")
    else:
        missing_inputs.append("taxes")
    if property_input.insurance is not None:
        user_inputs_used.append("insurance")
    else:
        missing_inputs.append("insurance")

    if property_input.down_payment_percent is not None:
        user_inputs_used.append("down payment")
    else:
        missing_inputs.append("down payment")
    if property_input.interest_rate is not None:
        user_inputs_used.append("interest rate")
    else:
        missing_inputs.append("interest rate")
    if property_input.loan_term_years is not None:
        user_inputs_used.append("loan term")
    else:
        missing_inputs.append("loan term")

    if property_input.monthly_hoa is not None:
        facts_used.append("hoa")
    if property_input.monthly_maintenance_reserve_override is not None:
        user_inputs_used.append("maintenance reserve override")
    else:
        assumptions_used.append("default maintenance reserve")

    financing_complete = bool(income_metrics.get("financing_complete"))
    if not financing_complete and {"down payment", "interest rate", "loan term"} & set(missing_inputs):
        assumptions_used.append("partial operating-cost view without full financing")

    status = _classify_metric_status(
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_required=missing_inputs if property_input.purchase_price is None else [],
    )
    if property_input.purchase_price is None:
        status = "unresolved"
    elif not financing_complete or "taxes" in missing_inputs or "insurance" in missing_inputs:
        status = "estimated"
    impact = (
        "monthly carry is partial because financing, tax, or insurance facts are incomplete"
        if status == "estimated"
        else "monthly carry cannot be computed without purchase basis"
        if status == "unresolved"
        else "monthly carry is grounded in explicit financing and operating inputs"
    )
    return MetricInputStatus(
        key="net_monthly_cost",
        label="Net Monthly Cost",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["taxes", "insurance", "down_payment_percent", "interest_rate", "loan_term_years"] if status != "fact_based" else [],
    )


def _price_per_sqft_status(property_input: PropertyInput, report: AnalysisReport) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    missing_inputs: list[str] = []

    price_fact, price_user = _coverage_label(property_input, "price_ask", fallback_label="purchase price")
    if property_input.purchase_price is not None:
        if price_fact:
            facts_used.append(price_fact)
        if price_user:
            user_inputs_used.append(price_user)
    else:
        missing_inputs.append("purchase price")

    sqft_fact, sqft_user = _coverage_label(property_input, "sqft", fallback_label="square footage")
    if property_input.sqft:
        if sqft_fact:
            facts_used.append(sqft_fact)
        if sqft_user:
            user_inputs_used.append(sqft_user)
    else:
        missing_inputs.append("square footage")

    assumptions_used: list[str] = []
    if report.get_module("comparable_sales").metrics.get("comp_count", 0) <= 0:
        assumptions_used.append("no comp benchmark available for relative PPSF framing")

    status = _classify_metric_status(
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used if not missing_inputs else [],
        missing_required=missing_inputs,
    )
    impact = (
        "price per square foot is unresolved without both price and square footage"
        if missing_inputs
        else "relative physical value is weaker because local comp PPSF support is thin"
        if assumptions_used
        else "price per square foot is a fact-based physical value metric"
    )
    return MetricInputStatus(
        key="price_per_sqft",
        label="Price Per Square Foot",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["sqft"] if missing_inputs else [],
    )


def _capex_load_status(property_input: PropertyInput) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    capex_confirmed = getattr(property_input, "capex_confirmed", False)
    condition_confirmed = getattr(property_input, "condition_confirmed", False)

    if property_input.repair_capex_budget is not None:
        user_inputs_used.append("repair budget")
        if capex_confirmed or condition_confirmed:
            user_inputs_used.append("confirmed condition/capex")
    elif property_input.capex_lane:
        if capex_confirmed:
            user_inputs_used.append("confirmed capex lane")
        else:
            assumptions_used.append("capex lane heuristic")
    elif property_input.condition_profile:
        if condition_confirmed:
            user_inputs_used.append("confirmed condition")
        else:
            assumptions_used.append("condition-based capex inference")
    else:
        missing_inputs.extend(["condition", "renovation budget"])

    if property_input.sqft:
        facts_used.append("square footage")

    status = _classify_metric_status(
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_required=missing_inputs,
    )
    impact = (
        "capex load is unresolved without condition or renovation budget"
        if status == "unresolved"
        else "capex burden is inferred rather than explicitly budgeted"
        if status == "estimated"
        else "capex load is grounded in explicit or user-confirmed renovation inputs"
    )
    return MetricInputStatus(
        key="capex_load",
        label="CapEx Load",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["repair_capex_budget", "condition_profile_override", "capex_lane_override", "condition_confirmed"] if status != "fact_based" else [],
    )


def _liquidity_status(property_input: PropertyInput, liquidity_metrics: dict) -> MetricInputStatus:
    facts_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    if property_input.days_on_market is not None:
        facts_used.append("days on market")
    if liquidity_metrics.get("market_liquidity_view"):
        facts_used.append("market liquidity backdrop")
    if int(liquidity_metrics.get("comp_count") or 0) > 0:
        facts_used.append("comp depth")
    if liquidity_metrics.get("rental_liquidity_score") is not None:
        assumptions_used.append("rental absorption proxy")

    if not facts_used and not assumptions_used:
        missing_inputs.extend(["days on market", "liquidity context", "comp depth"])

    status = "unresolved" if missing_inputs else "estimated" if "rental absorption proxy" in assumptions_used and len(facts_used) < 2 else "fact_based"
    impact = (
        "exit liquidity is unresolved because no property or market liquidity evidence is available"
        if status == "unresolved"
        else "exit liquidity uses proxy evidence and should be treated as directional"
        if status == "estimated"
        else "exit liquidity is grounded in observed DOM, market context, and resale depth"
    )
    return MetricInputStatus(
        key="liquidity",
        label="Liquidity",
        status=status,
        facts_used=facts_used,
        user_inputs_used=[],
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["days_on_market", "manual_comp_inputs"] if status != "fact_based" else [],
    )


def _optionality_status(property_input: PropertyInput, report: AnalysisReport) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    for field_name, label in [
        ("lot_size", "lot size"),
        ("has_back_house", "back house"),
        ("adu_type", "adu"),
        ("has_basement", "basement"),
        ("garage_spaces", "garage"),
        ("property_type", "property type"),
    ]:
        value = getattr(property_input, field_name)
        if _is_known_detail(value):
            facts_used.append(label)
    if getattr(property_input, "strategy_intent", None):
        user_inputs_used.append("strategy intent")
    if getattr(property_input, "hold_period_years", None) is not None:
        user_inputs_used.append("hold period")

    has_lot_size = _is_known_detail(getattr(property_input, "lot_size", None))
    if not has_lot_size:
        missing_inputs.append("lot size")
    if not has_known_optionality_detail(property_input):
        missing_inputs.append("ADU/basement/garage detail")
    if report.module_results.get("renovation_scenario") is None and report.module_results.get("teardown_scenario") is None:
        assumptions_used.append("strategy flexibility is inferred without project scenarios")

    status = "unresolved" if missing_inputs else "estimated" if assumptions_used else "user_confirmed" if user_inputs_used else "fact_based"
    impact = (
        "optionality is weakly grounded until physical upside features are confirmed"
        if status == "unresolved"
        else "optionality still mixes some inferred strategic flexibility"
        if status == "estimated"
        else "optionality is tied to explicit physical and strategy inputs"
    )
    return MetricInputStatus(
        key="optionality",
        label="Optionality",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["lot_size", "adu_type", "has_back_house", "has_basement", "garage_spaces", "strategy_intent"] if status != "fact_based" else [],
    )


def _net_opportunity_delta_status(property_input: PropertyInput, current_value_metrics: dict) -> MetricInputStatus:
    facts_used: list[str] = []
    user_inputs_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    if current_value_metrics.get("briarwood_current_value") is not None:
        facts_used.append("BCV anchor")
    else:
        missing_inputs.append("BCV anchor")
    if property_input.purchase_price is not None:
        price_fact, price_user = _coverage_label(property_input, "price_ask", fallback_label="purchase price")
        if price_fact:
            facts_used.append(price_fact)
        if price_user:
            user_inputs_used.append(price_user)
    else:
        missing_inputs.append("purchase price")

    capex_source = str(current_value_metrics.get("capex_basis_source") or "unknown")
    if capex_source == "user_budget":
        user_inputs_used.append("repair budget")
    elif capex_source in {"inferred_lane", "inferred_condition"}:
        assumptions_used.append("inferred capex basis")
    else:
        missing_inputs.append("capex basis")

    status = _classify_metric_status(
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_required=missing_inputs,
    )
    impact = (
        "net opportunity delta is unresolved without BCV, purchase basis, and a usable capex basis"
        if status == "unresolved"
        else "delta is directionally useful but capex is still inferred"
        if status == "estimated"
        else "delta is grounded in BCV, purchase basis, and explicit required work"
    )
    return MetricInputStatus(
        key="net_opportunity_delta",
        label="Net Opportunity Delta",
        status=status,
        facts_used=facts_used,
        user_inputs_used=user_inputs_used,
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["repair_capex_budget", "condition_profile_override"] if status != "fact_based" else [],
    )


def _market_momentum_status(report: AnalysisReport, momentum_metrics: dict, local_metrics: dict) -> MetricInputStatus:
    facts_used: list[str] = []
    assumptions_used: list[str] = []
    missing_inputs: list[str] = []

    if momentum_metrics.get("history_trend_score") is not None:
        facts_used.append("market history trend")
    if momentum_metrics.get("town_market_score") is not None:
        facts_used.append("town/county market score")
    if momentum_metrics.get("local_activity_score") is not None:
        facts_used.append("local activity signals")
    elif local_metrics:
        assumptions_used.append("no structured local documents")
    if momentum_metrics.get("scenario_drift_score") is not None:
        assumptions_used.append("forward market drift assumption")

    if not facts_used and not assumptions_used:
        missing_inputs.extend(["market history", "town/county outlook"])

    status = "unresolved" if missing_inputs else "estimated" if assumptions_used else "fact_based"
    impact = (
        "market momentum is unresolved because both history and market context are missing"
        if status == "unresolved"
        else "momentum blends observed trend data with modeled forward drift"
        if status == "estimated"
        else "momentum is grounded in observed market history and current market context"
    )
    return MetricInputStatus(
        key="market_momentum",
        label="Market Momentum",
        status=status,
        facts_used=facts_used,
        user_inputs_used=[],
        assumptions_used=assumptions_used,
        missing_inputs=missing_inputs,
        confidence_impact=impact,
        prompt_fields=["local_documents"] if status != "fact_based" else [],
    )


def _apply_metric_status_caps(
    components: list[ConfidenceComponent],
    status_map: dict[str, MetricInputStatus],
) -> list[ConfidenceComponent]:
    updated: list[ConfidenceComponent] = []
    cap_rules = {
        "rent": [("price_to_rent", {"estimated": 0.72, "unresolved": 0.38}), ("net_monthly_cost", {"estimated": 0.68, "unresolved": 0.4})],
        "capex": [("capex_load", {"estimated": 0.68, "unresolved": 0.42}), ("net_opportunity_delta", {"estimated": 0.72, "unresolved": 0.45})],
        "market": [("market_momentum", {"estimated": 0.74, "unresolved": 0.45})],
        "liquidity": [("liquidity", {"estimated": 0.72, "unresolved": 0.45})],
    }
    for component in components:
        confidence = component.confidence
        reason = component.reason
        for metric_key, caps in cap_rules.get(component.key, []):
            status = status_map.get(metric_key)
            if status is None:
                continue
            cap = caps.get(status.status)
            if cap is not None and confidence > cap:
                confidence = cap
                reason = f"{reason} Confidence reduced because {status.label.lower()} is {status.status.replace('_', ' ')}."
        updated.append(
            ConfidenceComponent(
                key=component.key,
                label=component.label,
                confidence=_clamp_confidence(confidence),
                weight=component.weight,
                reason=reason,
            )
        )
    return updated


def _apply_assumption_quality_caps(
    components: list[ConfidenceComponent],
    assumption_statuses: list[CriticalAssumptionStatus],
) -> list[ConfidenceComponent]:
    status_map = {item.key: item for item in assumption_statuses}
    component_caps: dict[str, list[tuple[str, float, float]]] = {
        "rent": [
            ("rent", 0.76, 0.42),
            ("insurance", 0.76, 0.48),
            ("taxes", 0.80, 0.52),
            ("financing", 0.74, 0.46),
        ],
        "capex": [
            ("condition_profile", 0.74, 0.50),
            ("capex", 0.68, 0.40),
        ],
    }
    updated: list[ConfidenceComponent] = []
    for component in components:
        confidence = component.confidence
        reason = component.reason
        for status_key, estimated_cap, missing_cap in component_caps.get(component.key, []):
            status = status_map.get(status_key)
            if status is None:
                continue
            if status.status == "estimated" and confidence > estimated_cap:
                confidence = estimated_cap
                reason = f"{reason} Confidence reduced because {status.label.lower()} is estimated."
            elif status.status == "missing" and confidence > missing_cap:
                confidence = missing_cap
                reason = f"{reason} Confidence reduced because {status.label.lower()} is missing."
        updated.append(
            ConfidenceComponent(
                key=component.key,
                label=component.label,
                confidence=_clamp_confidence(confidence),
                weight=component.weight,
                reason=reason,
            )
        )
    return updated


def _apply_town_context_caps(
    components: list[ConfidenceComponent],
    property_input: PropertyInput | None,
) -> list[ConfidenceComponent]:
    if property_input is None:
        return components
    from briarwood.modules.town_aggregation_diagnostics import get_town_context

    town_context = get_town_context(property_input.town)
    if town_context is None:
        return components

    flag_count = len(town_context.qa_flags)
    if flag_count == 0 and town_context.context_confidence >= 0.78:
        return components

    if town_context.context_confidence < 0.45 or flag_count >= 3:
        caps = {"market": 0.62, "liquidity": 0.58}
    elif town_context.context_confidence < 0.60 or flag_count >= 2:
        caps = {"market": 0.70, "liquidity": 0.66}
    else:
        caps = {"market": 0.78, "liquidity": 0.74}

    town_reason = f"Town context for {town_context.town} is weaker ({', '.join(town_context.qa_flags) or 'coverage risk'})."
    updated: list[ConfidenceComponent] = []
    for component in components:
        confidence = component.confidence
        reason = component.reason
        cap = caps.get(component.key)
        if cap is not None and confidence > cap:
            confidence = cap
            reason = f"{reason} {town_reason}"
        updated.append(
            ConfidenceComponent(
                key=component.key,
                label=component.label,
                confidence=_clamp_confidence(confidence),
                weight=component.weight,
                reason=reason,
            )
        )
    return updated
