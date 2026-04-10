from __future__ import annotations

from briarwood.agents.current_value import CurrentValueAgent, CurrentValueInput, CurrentValueOutput
from briarwood.field_audit import audit_property_fields
from briarwood.evidence import build_section_evidence
from briarwood.modules.comparable_sales import ComparableSalesModule, get_comparable_sales_payload
from briarwood.modules.hybrid_value import HybridValueModule, get_hybrid_value_payload
from briarwood.modules.income_support import IncomeSupportModule, get_income_support_payload
from briarwood.modules.market_value_history import (
    MarketValueHistoryModule,
    get_market_value_history_payload,
)
from briarwood.modules.town_aggregation_diagnostics import get_town_context
from briarwood.opportunity_metrics import calculate_net_opportunity_delta
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import CurrentValueSettings, DEFAULT_CURRENT_VALUE_SETTINGS


class CurrentValueModule:
    """Estimate today's Briarwood Current Value from market, listing, and income anchors."""

    name = "current_value"

    def __init__(
        self,
        *,
        agent: CurrentValueAgent | None = None,
        comparable_sales_module: ComparableSalesModule | None = None,
        market_value_history_module: MarketValueHistoryModule | None = None,
        income_support_module: IncomeSupportModule | None = None,
        hybrid_value_module: HybridValueModule | None = None,
        settings: CurrentValueSettings | None = None,
    ) -> None:
        self.agent = agent or CurrentValueAgent()
        self.comparable_sales_module = comparable_sales_module or ComparableSalesModule()
        self.market_value_history_module = market_value_history_module or MarketValueHistoryModule()
        self.income_support_module = income_support_module or IncomeSupportModule()
        self.hybrid_value_module = hybrid_value_module or HybridValueModule(
            comparable_sales_module=self.comparable_sales_module,
            income_support_module=self.income_support_module,
        )
        self.settings = settings or DEFAULT_CURRENT_VALUE_SETTINGS

    def run(
        self,
        property_input: PropertyInput,
        *,
        prior_results: dict[str, ModuleResult] | None = None,
    ) -> ModuleResult:
        if property_input.purchase_price is None or property_input.purchase_price <= 0:
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary="Briarwood Current Value could not be estimated because ask price is missing.",
                metrics={
                    "briarwood_current_value": None,
                    "mispricing_pct": None,
                    "pricing_view": "unavailable",
                },
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["price_ask", "market_history", "comp_support", "rent_estimate"],
                    extra_missing_inputs=["price_ask"],
                    notes=["BCV needs an ask price to compare current support against the market ask."],
                ),
            )

        comparable_result = (
            prior_results.get("comparable_sales")
            if prior_results is not None and "comparable_sales" in prior_results
            else self.comparable_sales_module.run(property_input)
        )
        history_result = (
            prior_results.get("market_value_history")
            if prior_results is not None and "market_value_history" in prior_results
            else self.market_value_history_module.run(property_input)
        )
        income_result = (
            prior_results.get("income_support")
            if prior_results is not None and "income_support" in prior_results
            else self.income_support_module.run(property_input)
        )
        hybrid_result = (
            prior_results.get("hybrid_value")
            if prior_results is not None and "hybrid_value" in prior_results
            else self.hybrid_value_module.run(
                property_input,
                prior_results={
                    "comparable_sales": comparable_result,
                    "income_support": income_result,
                },
            )
        )
        comparable_sales = get_comparable_sales_payload(comparable_result)
        history = get_market_value_history_payload(history_result)
        income = get_income_support_payload(income_result)
        hybrid_value = get_hybrid_value_payload(hybrid_result)
        town_context = get_town_context(property_input.town)

        output = self.agent.run(
            CurrentValueInput(
                ask_price=property_input.purchase_price,
                comparable_sales_value=comparable_sales.comparable_value,
                comparable_sales_confidence=comparable_sales.confidence,
                comparable_sales_count=comparable_sales.comp_count,
                market_value_today=history.current_value,
                market_history_points=history.points,
                sqft=property_input.sqft if property_input.sqft and property_input.sqft > 0 else None,
                beds=property_input.beds,
                baths=property_input.baths,
                lot_size=property_input.lot_size,
                property_type=property_input.property_type,
                year_built=property_input.year_built,
                listing_date=property_input.listing_date,
                price_history=property_input.price_history,
                days_on_market=property_input.days_on_market,
                effective_annual_rent=(
                    # When the comp module already used hybrid valuation (comping
                    # primary dwelling + income-capitalizing additional units),
                    # exclude the income component here to avoid double-counting
                    # the rental unit income.
                    None if getattr(comparable_sales, "is_hybrid_valuation", False)
                    else (income.effective_monthly_rent * 12 if income.effective_monthly_rent is not None else None)
                ),
                cap_rate_assumption=self.settings.income_cap_rate_assumption,
                town_median_price=(town_context.median_price if town_context else None),
                town_median_ppsf=(town_context.median_ppsf if town_context else None),
                town_median_sqft=(town_context.median_sqft if town_context else None),
                town_median_lot_size=(town_context.median_lot_size if town_context else None),
                town_context_confidence=(town_context.context_confidence if town_context else None),
            )
        )
        modeled_fields, non_modeled_fields = audit_property_fields(property_input)
        opportunity_delta = calculate_net_opportunity_delta(
            value_anchor=output.briarwood_current_value,
            property_input=property_input,
        )
        output = output.model_copy(
            update={
                "modeled_fields": modeled_fields,
                "non_modeled_fields": non_modeled_fields,
                "all_in_basis": opportunity_delta.all_in_basis,
                "capex_basis_used": opportunity_delta.capex_amount,
                "capex_basis_source": opportunity_delta.capex_source,
                "net_opportunity_delta_value": opportunity_delta.delta_value,
                "net_opportunity_delta_pct": opportunity_delta.delta_pct,
                "direct_value_range": comparable_sales.direct_value_range,
                "income_adjusted_value_range": comparable_sales.income_adjusted_value_range,
                "location_adjustment_range": comparable_sales.location_adjustment_range,
                "lot_adjustment_range": comparable_sales.lot_adjustment_range,
                "blended_value_range": comparable_sales.blended_value_range,
                "comp_confidence_score": comparable_sales.comp_confidence_score,
            }
        )
        output = self._apply_input_confidence_caps(output=output, income=income)
        output = self._apply_hybrid_adjustment(output=output, hybrid_value=hybrid_value)

        if hybrid_value.is_hybrid and hybrid_value.base_case_hybrid_value is not None:
            summary = (
                f"Briarwood Current Value is about ${output.briarwood_current_value:,.0f} under a hybrid front-house plus accessory-income framework, "
                f"which {output.pricing_view} versus the ask by {abs(output.mispricing_pct):.1%}. "
                f"Confidence is {output.confidence:.0%}."
            )
        else:
            summary = (
                f"Briarwood Current Value is about ${output.briarwood_current_value:,.0f}, "
                f"which {output.pricing_view} versus the ask by "
                f"{abs(output.mispricing_pct):.1%}. Confidence is {output.confidence:.0%}."
            )

        return ModuleResult(
            module_name=self.name,
            metrics={
                "briarwood_current_value": round(output.briarwood_current_value, 2),
                "value_low": round(output.value_low, 2),
                "value_high": round(output.value_high, 2),
                "mispricing_amount": round(output.mispricing_amount, 2),
                "mispricing_pct": round(output.mispricing_pct, 4),
                "pricing_view": output.pricing_view,
                "all_in_basis": round(output.all_in_basis, 2) if output.all_in_basis is not None else None,
                "capex_basis_used": round(output.capex_basis_used, 2) if output.capex_basis_used is not None else None,
                "capex_basis_source": output.capex_basis_source,
                "net_opportunity_delta_value": round(output.net_opportunity_delta_value, 2)
                if output.net_opportunity_delta_value is not None
                else None,
                "net_opportunity_delta_pct": round(output.net_opportunity_delta_pct, 4)
                if output.net_opportunity_delta_pct is not None
                else None,
                "comparable_sales_value": output.components.comparable_sales_value,
                "market_adjusted_value": output.components.market_adjusted_value,
                "backdated_listing_value": output.components.backdated_listing_value,
                "income_supported_value": output.components.income_supported_value,
                "town_prior_value": output.components.town_prior_value,
                "value_drivers": ", ".join(
                    f"{item.component} {item.normalized_weight:.0%}"
                    for item in output.value_drivers
                    if item.normalized_weight > 0
                ),
                "comparable_sales_weight": round(output.weights.comparable_sales_weight, 4),
                "market_adjusted_weight": round(output.weights.market_adjusted_weight, 4),
                "backdated_listing_weight": round(output.weights.backdated_listing_weight, 4),
                "income_weight": round(output.weights.income_weight, 4),
                "town_prior_weight": round(output.weights.town_prior_weight, 4),
                "town_context_confidence": output.town_context_confidence,
                "direct_value_low": output.direct_value_range.low if output.direct_value_range is not None else None,
                "direct_value_midpoint": output.direct_value_range.midpoint if output.direct_value_range is not None else None,
                "direct_value_high": output.direct_value_range.high if output.direct_value_range is not None else None,
                "income_adjusted_value_low": output.income_adjusted_value_range.low if output.income_adjusted_value_range is not None else None,
                "income_adjusted_value_midpoint": output.income_adjusted_value_range.midpoint if output.income_adjusted_value_range is not None else None,
                "income_adjusted_value_high": output.income_adjusted_value_range.high if output.income_adjusted_value_range is not None else None,
                "location_adjustment_low": output.location_adjustment_range.low if output.location_adjustment_range is not None else None,
                "location_adjustment_midpoint": output.location_adjustment_range.midpoint if output.location_adjustment_range is not None else None,
                "location_adjustment_high": output.location_adjustment_range.high if output.location_adjustment_range is not None else None,
                "lot_adjustment_low": output.lot_adjustment_range.low if output.lot_adjustment_range is not None else None,
                "lot_adjustment_midpoint": output.lot_adjustment_range.midpoint if output.lot_adjustment_range is not None else None,
                "lot_adjustment_high": output.lot_adjustment_range.high if output.lot_adjustment_range is not None else None,
                "blended_value_low": output.blended_value_range.low if output.blended_value_range is not None else None,
                "blended_value_midpoint": output.blended_value_range.midpoint if output.blended_value_range is not None else None,
                "blended_value_high": output.blended_value_range.high if output.blended_value_range is not None else None,
                "comp_confidence_score": output.comp_confidence_score,
                "valuation_method": "hybrid" if hybrid_value.is_hybrid else "standard",
                "hybrid_indicated_value": hybrid_value.base_case_hybrid_value,
                "hybrid_low_value": hybrid_value.low_case_hybrid_value,
                "hybrid_high_value": hybrid_value.high_case_hybrid_value,
            },
            score=max(0.0, min(output.confidence * 100, 100.0)),
            confidence=output.confidence,
            summary=summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["price_ask", "market_history", "comp_support", "rent_estimate", "listing_history"],
                extra_estimated_inputs=(["rent_estimate"] if getattr(income, "rent_source_type", "missing") == "estimated" else []),
                notes=["BCV blends sourced market context with comp support, a bounded town-aware prior, and any income-backed check that is available."],
            ),
        )

    def _apply_input_confidence_caps(
        self,
        *,
        output: CurrentValueOutput,
        income: object,
    ) -> CurrentValueOutput:
        warnings = list(output.warnings)
        confidence = output.confidence

        s = self.settings
        if getattr(income, "rent_source_type", "missing") == "missing":
            confidence = min(confidence, s.confidence_cap_rent_missing)
            warnings.append("Current value confidence is capped because rent is missing and the income-backed value check is unavailable.")
        elif getattr(income, "rent_source_type", "missing") == "estimated":
            confidence = min(confidence, s.confidence_cap_rent_estimated)
            warnings.append("Current value confidence is capped because rent support uses an estimated rent input.")

        if not getattr(income, "financing_complete", False):
            confidence = min(confidence, s.confidence_cap_financing_incomplete)
            warnings.append("Current value confidence is capped because financing inputs are incomplete.")

        if "annual_insurance" in getattr(income, "missing_inputs", []):
            confidence = min(confidence, s.confidence_cap_insurance_missing)

        if confidence == output.confidence and warnings == output.warnings:
            return output
        return output.model_copy(update={"confidence": round(confidence, 2), "warnings": warnings})

    def _apply_hybrid_adjustment(self, *, output: CurrentValueOutput, hybrid_value: object) -> CurrentValueOutput:
        if not getattr(hybrid_value, "is_hybrid", False):
            return output
        hybrid_base = getattr(hybrid_value, "base_case_hybrid_value", None)
        if hybrid_base is None or hybrid_base <= 0:
            return output

        hybrid_confidence = float(getattr(hybrid_value, "confidence", 0.0) or 0.0)
        confidence = round(max(0.4, min((output.confidence * 0.55) + (hybrid_confidence * 0.45), 0.86)), 2)
        mispricing_amount = hybrid_base - output.ask_price
        mispricing_pct = mispricing_amount / output.ask_price if output.ask_price else 0.0
        assumptions = list(output.assumptions)
        warnings = list(output.warnings)
        assumptions.append(
            "Hybrid value is used when a front-house comp anchor plus accessory-income decomposition fits the subject better than a pure single-family or pure multi-unit comp set."
        )
        warnings.append(
            "Hybrid current value remains conservative: accessory-unit credit is capped and legality or rent uncertainty can still limit the indicated range."
        )
        low_value = getattr(hybrid_value, "low_case_hybrid_value", None) or output.value_low
        high_value = getattr(hybrid_value, "high_case_hybrid_value", None) or output.value_high
        return output.model_copy(
            update={
                "briarwood_current_value": round(float(hybrid_base), 2),
                "value_low": round(float(low_value), 2),
                "value_high": round(float(high_value), 2),
                "mispricing_amount": round(float(mispricing_amount), 2),
                "mispricing_pct": round(float(mispricing_pct), 4),
                "pricing_view": self.agent._pricing_view(float(mispricing_pct)),
                "confidence": confidence,
                "assumptions": assumptions,
                "warnings": warnings,
            }
        )


def get_current_value_payload(result: ModuleResult) -> CurrentValueOutput:
    if not isinstance(result.payload, CurrentValueOutput):
        raise TypeError("current_value module payload is not a CurrentValueOutput")
    return result.payload
