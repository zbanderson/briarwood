from __future__ import annotations

from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.scoring import clamp_score
from briarwood.utils import current_year, safe_divide


class PropertySnapshotModule:
    name = "property_snapshot"

    def run(self, property_input: PropertyInput) -> ModuleResult:
        price_per_sqft = None
        if property_input.purchase_price and property_input.sqft:
            price_per_sqft = safe_divide(property_input.purchase_price, property_input.sqft)

        age = None
        if property_input.year_built:
            age = current_year() - property_input.year_built

        score = 70.0
        if age is not None:
            score -= min(age / 2, 20)
        if property_input.days_on_market is not None and property_input.days_on_market < 30:
            score += 5

        metrics = {
            "beds": property_input.beds,
            "baths": property_input.baths,
            "sqft": property_input.sqft,
            "lot_size": property_input.lot_size,
            "price_per_sqft": round(price_per_sqft, 2) if price_per_sqft is not None else None,
            "property_age": age,
        }
        summary = (
            f"{property_input.beds} bed / {property_input.baths} bath home in "
            f"{property_input.town} with {property_input.sqft} sqft."
        )
        return ModuleResult(
            module_name=self.name,
            metrics=metrics,
            score=clamp_score(score),
            confidence=0.9,
            summary=summary,
            section_evidence=build_section_evidence(
                property_input,
                categories=["address", "beds_baths", "sqft", "lot_size", "price_ask"],
                notes=["Property snapshot reflects currently assembled facts, which may come from public record, listing text, or manual input depending on evidence mode."],
            ),
        )
