from __future__ import annotations

import dataclasses

from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.current_value import CurrentValueModule, get_current_value_payload
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import DEFAULT_RENOVATION_SCENARIO_SETTINGS, RenovationScenarioSettings


class RenovationScenarioModule:
    """
    Estimates value creation from a planned renovation.

    Creates a hypothetical post-renovation PropertyInput, runs it through the comp
    and current-value infrastructure, then computes renovation economics.

    No-op if renovation_scenario is absent or disabled.
    """

    name = "renovation_scenario"

    def __init__(
        self,
        settings: RenovationScenarioSettings | None = None,
        *,
        comparable_sales_module: ComparableSalesModule | None = None,
        current_value_module: CurrentValueModule | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_RENOVATION_SCENARIO_SETTINGS
        self.comparable_sales_module = comparable_sales_module or ComparableSalesModule()
        self.current_value_module = current_value_module or CurrentValueModule()

    def run(
        self,
        property_input: PropertyInput,
        prior_results: dict[str, ModuleResult] | None = None,
    ) -> ModuleResult:
        scenario = property_input.renovation_scenario
        if not scenario or not scenario.get("enabled"):
            return ModuleResult(module_name=self.name, summary="Renovation scenario not enabled.")

        budget = float(scenario.get("renovation_budget") or 0.0)
        s = self.settings
        if budget < s.min_renovation_budget:
            return ModuleResult(
                module_name=self.name,
                summary=f"Renovation budget ${budget:,.0f} is below minimum ${s.min_renovation_budget:,.0f} — scenario skipped.",
            )

        # Pull current BCV from prior_results if available
        if prior_results and "current_value" in prior_results:
            current_value_result = prior_results["current_value"]
        else:
            current_value_result = self.current_value_module.run(property_input)
        current_cv = get_current_value_payload(current_value_result)
        current_bcv = current_cv.briarwood_current_value

        # Build renovated input
        target_condition = str(scenario.get("target_condition") or "renovated")
        sqft_addition = scenario.get("sqft_addition")
        beds_after = scenario.get("beds_after")
        baths_after = scenario.get("baths_after")
        adds_adu = bool(scenario.get("adds_adu"))
        adds_garage = bool(scenario.get("adds_garage"))

        new_sqft = property_input.sqft + int(sqft_addition or 0)
        new_beds = int(beds_after) if beds_after is not None else property_input.beds
        new_baths = float(baths_after) if baths_after is not None else property_input.baths
        new_garage_spaces = property_input.garage_spaces
        if adds_garage and (new_garage_spaces is None or new_garage_spaces == 0):
            new_garage_spaces = 1
        new_adu_type = property_input.adu_type
        if adds_adu and new_adu_type is None:
            new_adu_type = "detached_cottage"

        renovated_input = dataclasses.replace(
            property_input,
            condition_profile=target_condition,
            sqft=new_sqft,
            beds=new_beds,
            baths=new_baths,
            garage_spaces=new_garage_spaces,
            adu_type=new_adu_type,
            capex_lane=None,  # post-reno, no capex needed
            repair_capex_budget=None,
        )

        # Run comp + current_value against renovated profile
        renovated_comp_result = self.comparable_sales_module.run(renovated_input)
        renovated_cv_result = self.current_value_module.run(renovated_input)
        renovated_cv = get_current_value_payload(renovated_cv_result)
        renovated_bcv = renovated_cv.briarwood_current_value

        # Economics
        gross_value_creation = renovated_bcv - current_bcv
        net_value_creation = gross_value_creation - budget
        roi_pct = (net_value_creation / budget * 100.0) if budget > 0 else 0.0
        cost_per_dollar = (budget / gross_value_creation) if gross_value_creation > 0 else float("inf")

        # Confidence: start from renovated_cv confidence, penalize if few renovated comps
        renovated_comps_payload = renovated_comp_result.payload
        renovated_comp_count = 0
        if hasattr(renovated_comps_payload, "comps"):
            renovated_comp_count = len(renovated_comps_payload.comps or [])
        confidence = renovated_cv_result.confidence
        warnings: list[str] = list(renovated_cv.warnings)
        if renovated_comp_count < s.min_renovated_comps_for_full_confidence:
            confidence = max(confidence - s.confidence_penalty_few_renovated_comps, s.confidence_floor)
            warnings.append(
                f"Only {renovated_comp_count} renovated-condition comp(s) found — renovated BCV estimate has wider uncertainty."
            )
        confidence = max(confidence, s.confidence_floor)

        # Build condition change description
        original_condition = property_input.condition_profile or "unknown"
        condition_change = f"{original_condition} → {target_condition}"
        sqft_change = f"{property_input.sqft} → {new_sqft}" if sqft_addition else None
        comp_range_text = _comp_range_text(renovated_comps_payload)

        # Narrative
        summary = _renovation_narrative(
            address=property_input.address,
            current_bcv=current_bcv,
            renovated_bcv=renovated_bcv,
            budget=budget,
            gross_value_creation=gross_value_creation,
            net_value_creation=net_value_creation,
            roi_pct=roi_pct,
            cost_per_dollar=cost_per_dollar,
            target_condition=target_condition,
            sqft_addition=int(sqft_addition) if sqft_addition else None,
            new_sqft=new_sqft,
            new_beds=new_beds,
            town=property_input.town,
            comp_range_text=comp_range_text,
        )

        payload = {
            "enabled": True,
            "renovation_budget": budget,
            "current_bcv": round(current_bcv, 2),
            "renovated_bcv": round(renovated_bcv, 2),
            "gross_value_creation": round(gross_value_creation, 2),
            "net_value_creation": round(net_value_creation, 2),
            "roi_pct": round(roi_pct, 1),
            "cost_per_dollar_of_value": round(cost_per_dollar, 3) if cost_per_dollar != float("inf") else None,
            "condition_change": condition_change,
            "sqft_change": sqft_change,
            "comp_range_text": comp_range_text,
            "confidence": round(confidence, 2),
            "warnings": warnings,
            "summary": summary,
        }

        return ModuleResult(
            module_name=self.name,
            metrics={
                "enabled": True,
                "renovation_budget": round(budget, 2),
                "current_bcv": round(current_bcv, 2),
                "renovated_bcv": round(renovated_bcv, 2),
                "gross_value_creation": round(gross_value_creation, 2),
                "net_value_creation": round(net_value_creation, 2),
                "roi_pct": round(roi_pct, 1),
                "cost_per_dollar_of_value": round(cost_per_dollar, 3) if cost_per_dollar != float("inf") else None,
                "condition_change": condition_change,
                "sqft_change": sqft_change,
                "comp_range_text": comp_range_text,
            },
            score=min(100.0, max(0.0, 50.0 + roi_pct * 0.5)),
            confidence=round(confidence, 2),
            summary=summary,
            payload=payload,
        )


def _comp_range_text(comp_payload) -> str:
    """Extract a human-readable comp range from the comp output payload."""
    if comp_payload is None:
        return "No comp data available."
    comps = getattr(comp_payload, "comps", None)
    if not comps:
        return "No comps found for renovated profile."
    prices = [c.adjusted_price for c in comps if getattr(c, "adjusted_price", None) is not None]
    if not prices:
        return "Comp prices unavailable."
    lo, hi = min(prices), max(prices)
    return f"${lo:,.0f}–${hi:,.0f}"


def _renovation_narrative(
    *,
    address: str,
    current_bcv: float,
    renovated_bcv: float,
    budget: float,
    gross_value_creation: float,
    net_value_creation: float,
    roi_pct: float,
    cost_per_dollar: float,
    target_condition: str,
    sqft_addition: int | None,
    new_sqft: int,
    new_beds: int,
    town: str,
    comp_range_text: str,
) -> str:
    sqft_note = f", including {sqft_addition:,} sqft of additional living space," if sqft_addition else ""
    value_per_dollar = 1.0 / cost_per_dollar if cost_per_dollar > 0 and cost_per_dollar != float("inf") else 0.0

    if roi_pct < 0 or cost_per_dollar > 1.0:
        return (
            f"The renovation economics are unfavorable. A ${budget:,.0f} investment targeting '{target_condition}' condition{sqft_note} "
            f"is projected to create only ${gross_value_creation:,.0f} in value — a net {'loss' if net_value_creation < 0 else 'gain'} "
            f"of ${abs(net_value_creation):,.0f}. "
            f"Renovated {new_beds}BR homes in {town} are trading in the {comp_range_text} range. "
            f"The property's price point may be near the ceiling for its location, and renovation spending would not be fully recaptured."
        )
    return (
        f"At current condition, this property is valued at approximately ${current_bcv:,.0f}. "
        f"A renovation investment of ${budget:,.0f} targeting '{target_condition}' condition{sqft_note} "
        f"would reposition the property against a higher-quality comp set. "
        f"Renovated {new_beds}BR homes in {town} ({new_sqft:,} sqft) are trading in the {comp_range_text} range. "
        f"The estimated post-renovation value is ${renovated_bcv:,.0f}, creating approximately ${gross_value_creation:,.0f} in gross value "
        f"on a ${budget:,.0f} investment ({roi_pct:.1f}% ROI). "
        f"For every dollar spent on renovation, the model estimates ${value_per_dollar:.2f} in value creation."
    )
