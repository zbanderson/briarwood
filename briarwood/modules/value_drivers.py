from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from briarwood.evidence import build_section_evidence
from briarwood.schemas import ModuleResult, PropertyInput


class ValueDriverItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    estimated_value_impact: float
    confidence: float = Field(ge=0, le=1)
    description: str


class ValueBridgeStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: float
    confidence: float = Field(ge=0, le=1)


class ValueDriversOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_value: float
    adjusted_value: float
    value_gap: float
    drivers: list[ValueDriverItem]
    bridge: list[ValueBridgeStep]
    summary: str


class ValueDriversModule:
    name = "value_drivers"

    def run(self, property_input: PropertyInput, *, prior_results: dict[str, ModuleResult]) -> ModuleResult:
        current_value_result = prior_results.get("current_value")
        if current_value_result is None or current_value_result.payload is None:
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary="Value drivers are unavailable because current value did not run.",
                metrics={"driver_count": 0},
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["comp_support", "rent_estimate", "listing_history"],
                    extra_missing_inputs=["current_value"],
                ),
            )

        current_value = current_value_result.payload
        income_result = prior_results.get("income_support")
        location_result = prior_results.get("location_intelligence")
        renovation_result = prior_results.get("renovation_scenario")
        town_result = prior_results.get("town_county_outlook")

        base_value = (
            getattr(getattr(current_value, "direct_value_range", None), "midpoint", None)
            or getattr(getattr(current_value, "components", None), "comparable_sales_value", None)
            or getattr(current_value, "briarwood_current_value", None)
        )
        adjusted_value = getattr(current_value, "briarwood_current_value", None)
        if base_value in (None, 0) or adjusted_value is None:
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary="Value drivers are unavailable because the valuation anchor is incomplete.",
                metrics={"driver_count": 0},
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["comp_support", "rent_estimate", "listing_history"],
                ),
            )

        value_gap = float(adjusted_value) - float(base_value)
        raw_candidates = _raw_driver_candidates(
            property_input=property_input,
            current_value=current_value,
            income_payload=None if income_result is None else income_result.payload,
            location_metrics=None if location_result is None else location_result.metrics,
            renovation_metrics=None if renovation_result is None else renovation_result.metrics,
            town_metrics=None if town_result is None else town_result.metrics,
        )
        drivers = _allocate_driver_impacts(raw_candidates, value_gap)
        bridge = [ValueBridgeStep(label="Direct Market Anchor", value=round(float(base_value), 2), confidence=round(float(getattr(current_value, "comp_confidence_score", None) or current_value_result.confidence), 2))]
        running = float(base_value)
        for driver in drivers:
            running += driver.estimated_value_impact
            bridge.append(
                ValueBridgeStep(
                    label=driver.label,
                    value=round(running, 2),
                    confidence=driver.confidence,
                )
            )
        bridge.append(
            ValueBridgeStep(
                label="Briarwood Adjusted Value",
                value=round(float(adjusted_value), 2),
                confidence=round(float(current_value_result.confidence), 2),
            )
        )
        avg_confidence = round(sum(driver.confidence for driver in drivers) / max(len(drivers), 1), 2)
        top_driver = max(drivers, key=lambda item: abs(item.estimated_value_impact), default=None)
        summary = (
            f"Value bridge starts from a direct market anchor of ${base_value:,.0f} and steps to ${adjusted_value:,.0f} "
            f"through property-specific drivers. Dominant driver: {top_driver.label.lower()}."
            if top_driver is not None
            else f"Value bridge lands near ${adjusted_value:,.0f} with limited property-specific driver support."
        )
        payload = ValueDriversOutput(
            base_value=round(float(base_value), 2),
            adjusted_value=round(float(adjusted_value), 2),
            value_gap=round(value_gap, 2),
            drivers=drivers,
            bridge=bridge,
            summary=summary,
        )
        return ModuleResult(
            module_name=self.name,
            metrics={
                "base_value": payload.base_value,
                "adjusted_value": payload.adjusted_value,
                "value_gap": payload.value_gap,
                "driver_count": len(payload.drivers),
                "dominant_driver": top_driver.label if top_driver is not None else "",
                "driver_confidence": avg_confidence,
            },
            score=min(avg_confidence * 100, 100.0),
            confidence=avg_confidence,
            summary=summary,
            payload=payload,
            section_evidence=build_section_evidence(
                property_input,
                categories=["comp_support", "rent_estimate", "listing_history"],
                notes=["Value drivers explain the bridge from the direct comp anchor to Briarwood's adjusted value; they do not replace the core scoring engine."],
            ),
        )


def _raw_driver_candidates(
    *,
    property_input: PropertyInput,
    current_value,
    income_payload,
    location_metrics: dict | None,
    renovation_metrics: dict | None,
    town_metrics: dict | None,
) -> list[dict]:
    base_value = float(
        getattr(getattr(current_value, "direct_value_range", None), "midpoint", None)
        or getattr(getattr(current_value, "components", None), "comparable_sales_value", None)
        or getattr(current_value, "briarwood_current_value", None)
        or 0.0
    )
    candidates: list[dict] = []

    income_supported_value = getattr(getattr(current_value, "components", None), "income_supported_value", None)
    income_raw = 0.0
    income_desc = "Rental support is not strong enough yet to move value materially."
    if income_supported_value is not None:
        income_raw = float(income_supported_value) - base_value
        income_desc = "Income support reflects rents, unit mix, and accessory-unit income where available."
    elif property_input.has_back_house or property_input.adu_type or len(property_input.unit_rents or []) >= 2:
        income_raw = base_value * 0.02
        income_desc = "Income support receives a modest premium because the property has multi-unit or accessory-unit income optionality."
    candidates.append(
        {
            "key": "income",
            "label": "Income",
            "raw_impact": income_raw,
            "confidence": round(float(getattr(income_payload, "confidence", 0.45) or 0.45), 2),
            "description": income_desc,
        }
    )

    location_premium_pct = 0.0
    if location_metrics is not None and location_metrics.get("location_premium_pct") is not None:
        location_premium_pct = float(location_metrics["location_premium_pct"])
    elif town_metrics is not None and str(town_metrics.get("location_thesis_label") or "").lower() in {"beach premium", "downtown premium"}:
        location_premium_pct = 0.025
    location_raw = base_value * location_premium_pct
    location_conf = 0.55 if property_input.latitude is not None and property_input.longitude is not None else 0.35
    candidates.append(
        {
            "key": "location",
            "label": "Location",
            "raw_impact": location_raw,
            "confidence": round(location_conf, 2),
            "description": "Location value reflects beach/downtown/train access, town premium, and micro-location support when Briarwood can benchmark it.",
        }
    )

    optionality_raw = 0.0
    optionality_bits: list[str] = []
    if property_input.has_back_house or property_input.adu_type:
        optionality_raw += base_value * 0.015
        optionality_bits.append("accessory-unit flexibility")
    town_median_lot = None
    if town_metrics is not None:
        town_median_lot = town_metrics.get("baseline_median_lot_size")
    if town_median_lot not in (None, 0) and property_input.lot_size not in (None, 0) and property_input.lot_size > float(town_median_lot):
        optionality_raw += base_value * 0.015
        optionality_bits.append("larger-than-typical lot size")
    candidates.append(
        {
            "key": "optionality",
            "label": "Optionality",
            "raw_impact": optionality_raw,
            "confidence": 0.5 if optionality_bits else 0.3,
            "description": "Optionality reflects expandability, zoning-like flexibility, and lot-driven upside." if optionality_bits else "Optionality remains modest because lot and use flexibility are not yet strong enough to drive value materially.",
        }
    )

    condition_raw = 0.0
    condition_profile = (property_input.condition_profile or "").lower()
    if condition_profile in {"renovated", "updated"}:
        condition_raw += base_value * 0.01
    elif condition_profile in {"dated", "needs_work"}:
        condition_raw -= base_value * 0.025
    if renovation_metrics is not None and renovation_metrics.get("net_value_creation") is not None and float(renovation_metrics["net_value_creation"] or 0.0) > 0:
        condition_raw -= min(base_value * 0.01, float(renovation_metrics["net_value_creation"]) * 0.08)
    candidates.append(
        {
            "key": "condition",
            "label": "Condition",
            "raw_impact": condition_raw,
            "confidence": 0.65 if property_input.condition_profile else 0.35,
            "description": "Condition captures renovation upside, present wear, and how much of the comp premium is still trapped behind execution.",
        }
    )
    return candidates


def _allocate_driver_impacts(raw_candidates: list[dict], value_gap: float) -> list[ValueDriverItem]:
    if abs(value_gap) < 1:
        return [
            ValueDriverItem(
                key=item["key"],
                label=item["label"],
                estimated_value_impact=0.0,
                confidence=item["confidence"],
                description=item["description"],
            )
            for item in raw_candidates
        ]

    direction = 1 if value_gap >= 0 else -1
    directional = [item for item in raw_candidates if item["raw_impact"] * direction > 0]
    if not directional:
        directional = raw_candidates
    total_strength = sum(abs(float(item["raw_impact"])) for item in directional) or float(len(directional))

    drivers: list[ValueDriverItem] = []
    allocated = 0.0
    for index, item in enumerate(directional):
        if index == len(directional) - 1:
            impact = value_gap - allocated
        else:
            share = abs(float(item["raw_impact"])) / total_strength if total_strength else 1.0 / max(len(directional), 1)
            impact = round(value_gap * share, 2)
            allocated += impact
        drivers.append(
            ValueDriverItem(
                key=item["key"],
                label=item["label"],
                estimated_value_impact=round(impact, 2),
                confidence=float(item["confidence"]),
                description=item["description"],
            )
        )
    drivers.sort(key=lambda item: abs(item.estimated_value_impact), reverse=True)
    return drivers


def get_value_drivers_payload(result: ModuleResult) -> ValueDriversOutput:
    if not isinstance(result.payload, ValueDriversOutput):
        raise TypeError("value_drivers module payload is not a ValueDriversOutput")
    return result.payload
