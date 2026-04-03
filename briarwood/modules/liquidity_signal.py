from __future__ import annotations

from briarwood.agents.rental_ease.scoring import liquidity_view_to_score
from briarwood.evidence import build_section_evidence
from briarwood.modules.comparable_sales import ComparableSalesModule, get_comparable_sales_payload
from briarwood.modules.rental_ease import RentalEaseModule, get_rental_ease_payload
from briarwood.modules.town_county_outlook import TownCountyOutlookModule, get_town_county_outlook_payload
from briarwood.schemas import LiquiditySignalOutput, ModuleResult, PropertyInput


class LiquiditySignalModule:
    """Canonical exit-liquidity signal for the current underwriting stack."""

    name = "liquidity_signal"

    def __init__(
        self,
        *,
        comparable_sales_module: ComparableSalesModule | None = None,
        rental_ease_module: RentalEaseModule | None = None,
        town_county_outlook_module: TownCountyOutlookModule | None = None,
    ) -> None:
        self.comparable_sales_module = comparable_sales_module or ComparableSalesModule()
        self.rental_ease_module = rental_ease_module or RentalEaseModule()
        self.town_county_outlook_module = town_county_outlook_module or TownCountyOutlookModule()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        comps_result = self.comparable_sales_module.run(property_input)
        rental_result = self.rental_ease_module.run(property_input)
        town_result = self.town_county_outlook_module.run(property_input)

        comps = get_comparable_sales_payload(comps_result)
        rental = get_rental_ease_payload(rental_result)
        town = get_town_county_outlook_payload(town_result).score

        dom_score = _dom_score(property_input.days_on_market)
        market_score = liquidity_view_to_score(town.liquidity_view)
        rental_score = float(rental.liquidity_score)
        comp_depth_score = _comp_depth_score(comps.comp_count, comps_result.confidence)

        weighted_components = []
        if dom_score is not None:
            weighted_components.append(("dom", dom_score, 0.35))
        if market_score is not None:
            weighted_components.append(("market", market_score, 0.30))
        if comp_depth_score is not None:
            weighted_components.append(("comps", comp_depth_score, 0.20))
        if rental_score is not None:
            weighted_components.append(("rental", rental_score, 0.15))

        total_weight = sum(weight for _, _, weight in weighted_components)
        liquidity_score = (
            sum(score * weight for _, score, weight in weighted_components) / total_weight
            if total_weight
            else 50.0
        )
        liquidity_score = round(max(0.0, min(liquidity_score, 100.0)), 1)
        liquidity_label = _liquidity_label(liquidity_score)
        confidence = _confidence(weighted_components, comps_result.confidence, rental_result.confidence, town_result.confidence)
        assumptions = _assumptions(weighted_components)
        supporting_evidence = _supporting_evidence(
            dom=property_input.days_on_market,
            dom_score=dom_score,
            market_view=town.liquidity_view,
            rental_score=rental_score,
            comp_count=comps.comp_count,
        )
        unsupported_claims = _unsupported_claims(property_input.days_on_market, comps.comp_count, weighted_components)
        summary = _summary(liquidity_label, property_input.days_on_market, town.liquidity_view, comps.comp_count)

        output = LiquiditySignalOutput(
            liquidity_score=liquidity_score,
            liquidity_label=liquidity_label,
            confidence=confidence,
            summary=summary,
            days_on_market=property_input.days_on_market,
            dom_score=round(dom_score, 1) if dom_score is not None else None,
            market_liquidity_view=town.liquidity_view,
            market_liquidity_score=round(market_score, 1) if market_score is not None else None,
            rental_liquidity_score=round(rental_score, 1) if rental_score is not None else None,
            comp_depth_score=round(comp_depth_score, 1) if comp_depth_score is not None else None,
            comp_count=int(comps.comp_count),
            assumptions=assumptions,
            supporting_evidence=supporting_evidence,
            unsupported_claims=unsupported_claims,
        )

        metrics = {
            "liquidity_score": output.liquidity_score,
            "liquidity_label": output.liquidity_label,
            "dom_score": output.dom_score,
            "market_liquidity_score": output.market_liquidity_score,
            "rental_liquidity_score": output.rental_liquidity_score,
            "comp_depth_score": output.comp_depth_score,
            "market_liquidity_view": output.market_liquidity_view,
            "days_on_market": output.days_on_market,
            "comp_count": output.comp_count,
        }
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=float(output.liquidity_score),
            confidence=float(output.confidence),
            summary=output.summary,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["liquidity_signal", "listing_history", "comp_support"],
                notes=["Canonical liquidity blends property marketing speed, market liquidity context, comp depth, and rental absorption signals."],
                extra_missing_inputs=(["listing_history"] if property_input.days_on_market is None else []),
            ),
        )


def get_liquidity_signal_payload(result: ModuleResult) -> LiquiditySignalOutput:
    if not isinstance(result.payload, LiquiditySignalOutput):
        raise TypeError("liquidity_signal module payload is not a LiquiditySignalOutput")
    return result.payload


def _dom_score(days_on_market: int | None) -> float | None:
    if days_on_market is None:
        return None
    if days_on_market <= 7:
        return 92.0
    if days_on_market <= 21:
        return 82.0
    if days_on_market <= 45:
        return 66.0
    if days_on_market <= 90:
        return 42.0
    return 24.0


def _comp_depth_score(comp_count: int, comp_confidence: float) -> float | None:
    if comp_count <= 0:
        return None
    if comp_count >= 6:
        base = 84.0
    elif comp_count >= 4:
        base = 72.0
    elif comp_count >= 2:
        base = 58.0
    else:
        base = 42.0
    return max(25.0, min((0.75 * base) + (0.25 * comp_confidence * 100), 92.0))


def _liquidity_label(score: float) -> str:
    if score >= 78:
        return "Strong Exit Liquidity"
    if score >= 62:
        return "Normal Exit Liquidity"
    if score >= 45:
        return "Mixed Exit Liquidity"
    return "Thin Exit Liquidity"


def _confidence(
    weighted_components: list[tuple[str, float, float]],
    comparable_sales_confidence: float,
    rental_confidence: float,
    town_confidence: float,
) -> float:
    if not weighted_components:
        return 0.35
    quality_caps = {
        "dom": 0.86,
        "market": town_confidence,
        "comps": comparable_sales_confidence,
        "rental": rental_confidence,
    }
    total_weight = sum(weight for key, _, weight in weighted_components)
    confidence = sum(quality_caps.get(key, 0.5) * weight for key, _, weight in weighted_components) / total_weight
    if len(weighted_components) <= 2:
        confidence = min(confidence, 0.7)
    return round(max(0.35, min(confidence, 0.9)), 2)


def _assumptions(weighted_components: list[tuple[str, float, float]]) -> list[str]:
    component_keys = {key for key, _, _ in weighted_components}
    notes: list[str] = []
    if "market" in component_keys:
        notes.append("Market liquidity uses the town/county liquidity view as the primary backdrop.")
    if "rental" in component_keys:
        notes.append("Rental absorption remains supporting evidence for exit liquidity rather than the primary signal.")
    if "dom" not in component_keys:
        notes.append("Property-level days-on-market is missing, so exit liquidity leans more heavily on market proxies.")
    return notes


def _supporting_evidence(
    *,
    dom: int | None,
    dom_score: float | None,
    market_view: str | None,
    rental_score: float | None,
    comp_count: int,
) -> list[str]:
    evidence: list[str] = []
    if dom is not None and dom_score is not None:
        evidence.append(f"{dom} DOM translated to a property-level liquidity score of {dom_score:.0f}.")
    if market_view:
        evidence.append(f"Town/county liquidity backdrop is {market_view}.")
    if comp_count > 0:
        evidence.append(f"{comp_count} comp(s) support the local resale depth check.")
    if rental_score is not None:
        evidence.append(f"Rental absorption contributes a secondary liquidity read of {rental_score:.0f}/100.")
    return evidence[:4]


def _unsupported_claims(
    dom: int | None,
    comp_count: int,
    weighted_components: list[tuple[str, float, float]],
) -> list[str]:
    claims: list[str] = []
    if dom is None:
        claims.append("Exit liquidity is less certain because property-level days-on-market data is missing.")
    if comp_count < 2:
        claims.append("Resale depth is thin because the local comparable-sale set is shallow.")
    if len(weighted_components) <= 2:
        claims.append("Liquidity relies on a limited evidence mix and should be treated as directional.")
    return claims[:3]


def _summary(label: str, dom: int | None, market_view: str | None, comp_count: int) -> str:
    dom_text = f"{dom} DOM" if dom is not None else "DOM unavailable"
    market_text = (market_view or "unknown").replace("_", " ")
    return (
        f"{label}. Exit liquidity blends {dom_text}, a {market_text} market backdrop, "
        f"and {comp_count} usable comp{'s' if comp_count != 1 else ''}."
    )
