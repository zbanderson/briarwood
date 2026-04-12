from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.agents.comparable_sales.schemas import AdjustedComparable, ComparableSalesOutput
from briarwood.evidence import build_section_evidence
from briarwood.modules.comparable_sales import ComparableSalesModule, get_comparable_sales_payload
from briarwood.modules.income_support import IncomeSupportModule, get_income_support_payload
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.valuation_constraints import evaluate_market_feedback, is_nonstandard_product, market_friction_discount


@dataclass(slots=True)
class HybridCompEntry:
    address: str
    sale_price: float
    adjusted_price: float
    sale_date: str
    fit_label: str
    property_type: str | None = None


@dataclass(slots=True)
class HybridValueOutput:
    is_hybrid: bool
    reason: str
    detected_primary_structure_type: str | None
    detected_accessory_income_type: str | None
    primary_house_value: float | None
    primary_house_comp_confidence: float
    primary_house_comp_set: list[HybridCompEntry] = field(default_factory=list)
    rear_income_value: float | None = None
    rear_income_method_used: str | None = None
    rear_income_confidence: float = 0.0
    rent_assumption_summary: str = ""
    optionality_premium_value: float | None = None
    optionality_reason: str = ""
    optionality_confidence: float = 0.0
    low_case_hybrid_value: float | None = None
    base_case_hybrid_value: float | None = None
    high_case_hybrid_value: float | None = None
    confidence: float = 0.0
    market_friction_discount: float | None = None
    market_feedback_adjustment: float | None = None
    notes: list[str] = field(default_factory=list)
    narrative: str = ""


class HybridValueModule:
    """Value front-house plus accessory-income properties with a decomposed framework."""

    name = "hybrid_value"

    def __init__(
        self,
        *,
        comparable_sales_module: ComparableSalesModule | None = None,
        income_support_module: IncomeSupportModule | None = None,
    ) -> None:
        self.comparable_sales_module = comparable_sales_module or ComparableSalesModule()
        self.income_support_module = income_support_module or IncomeSupportModule()

    def run(
        self,
        property_input: PropertyInput,
        *,
        prior_results: dict[str, ModuleResult] | None = None,
    ) -> ModuleResult:
        comparable_result = (
            prior_results.get("comparable_sales")
            if prior_results is not None and "comparable_sales" in prior_results
            else self.comparable_sales_module.run(property_input)
        )
        income_result = (
            prior_results.get("income_support")
            if prior_results is not None and "income_support" in prior_results
            else self.income_support_module.run(property_input)
        )
        comparable_payload = get_comparable_sales_payload(comparable_result)
        income_payload = get_income_support_payload(income_result)

        detection = _detect_hybrid_property(property_input, comparable_payload, income_payload)
        if not detection["is_hybrid"]:
            payload = HybridValueOutput(
                is_hybrid=False,
                reason=str(detection["reason"]),
                detected_primary_structure_type=detection["primary_structure_type"],
                detected_accessory_income_type=detection["accessory_income_type"],
                primary_house_value=None,
                primary_house_comp_confidence=0.0,
                confidence=0.0,
                notes=["Standard valuation remains the primary framework because the subject does not screen as a hybrid layout."],
                narrative="The subject does not currently require Briarwood's hybrid front-house plus accessory-income framework.",
            )
            return ModuleResult(
                module_name=self.name,
                score=0.0,
                confidence=0.0,
                summary=payload.narrative,
                metrics={
                    "is_hybrid": False,
                    "base_case_hybrid_value": None,
                    "confidence": 0.0,
                },
                payload=payload,
                section_evidence=build_section_evidence(
                    property_input,
                    categories=["comp_support", "rent_estimate", "sqft", "listing_history"],
                    notes=["Hybrid value only activates when accessory-unit economics or unusual layout meaningfully affect value."],
                ),
            )

        # When the comp module already performed hybrid decomposition (comping
        # primary dwelling only + income-capitalizing additional units), use
        # its primary dwelling value and income value directly instead of
        # re-running comps or re-capitalizing income (avoids double-counting).
        comp_is_hybrid = getattr(comparable_payload, "is_hybrid_valuation", False) and comparable_payload.primary_dwelling_value
        if comp_is_hybrid:
            primary_house_value = float(comparable_payload.primary_dwelling_value)
            primary_house_comp_confidence = round(float(comparable_payload.comp_confidence_score or comparable_payload.confidence or 0.0), 2)
            primary_house_comp_set = [
                HybridCompEntry(
                    address=comp.address,
                    sale_price=float(comp.sale_price),
                    adjusted_price=float(comp.adjusted_price),
                    sale_date=comp.sale_date,
                    fit_label=comp.fit_label,
                    property_type=comp.property_type,
                )
                for comp in comparable_payload.comps_used[:4]
            ]
        else:
            standalone_input = _standalone_primary_input(property_input)
            primary_result = self.comparable_sales_module.run(standalone_input)
            primary_payload = get_comparable_sales_payload(primary_result)
            primary_house_value, primary_house_comp_confidence, primary_house_comp_set = _primary_house_value(
                primary_payload
            )

        # When the comp module already capitalized the additional unit income,
        # reuse that value directly — the comp module applied a proper
        # NOI / cap-rate calculation so re-capping would discard legitimate
        # income support.
        if comp_is_hybrid and comparable_payload.additional_unit_income_value:
            rear_income_value = float(comparable_payload.additional_unit_income_value)
            rear_income_method_used = "comp_module_income_cap"
            rear_income_confidence = 0.72
            unit_count = comparable_payload.additional_unit_count or len(property_input.unit_rents or [])
            annual_income = comparable_payload.additional_unit_annual_income or 0
            rent_assumption_summary = (
                f"Rear income reused from comp module hybrid decomposition: "
                f"{unit_count} unit(s), ${annual_income:,.0f}/yr gross."
            )
            rear_notes: list[str] = []
        else:
            rear_income_value, rear_income_method_used, rear_income_confidence, rent_assumption_summary, rear_notes = _rear_income_value(
                property_input,
                income_payload=income_payload,
                primary_house_value=primary_house_value,
            )
        optionality_premium_value, optionality_reason, optionality_confidence = _optionality_premium(
            property_input,
            primary_house_value=primary_house_value,
            rear_income_value=rear_income_value,
        )
        pre_constraint_value = (primary_house_value or 0.0) + (rear_income_value or 0.0) + (optionality_premium_value or 0.0)
        market_friction_value, market_friction_notes = market_friction_discount(
            property_input=property_input,
            anchor_value=pre_constraint_value if pre_constraint_value > 0 else None,
        )
        constrained_value = pre_constraint_value + market_friction_value
        support_quality = (
            comparable_payload.base_comp_selection.support_summary.support_quality
            if comparable_payload.base_comp_selection is not None
            else "thin"
        )
        market_feedback = evaluate_market_feedback(
            property_input=property_input,
            indicated_value=constrained_value if constrained_value > 0 else None,
            support_quality=support_quality,
            confidence=primary_house_comp_confidence,
            subject_is_nonstandard=is_nonstandard_product(property_input),
        )
        low_case, base_case, high_case = _value_range(
            primary_house_value=primary_house_value,
            rear_income_value=rear_income_value,
            optionality_premium_value=optionality_premium_value,
            rear_income_confidence=rear_income_confidence,
            optionality_confidence=optionality_confidence,
            market_friction_discount=market_friction_value,
            market_feedback_adjustment=market_feedback.value_adjustment,
        )
        confidence = _overall_confidence(
            primary_house_comp_confidence=primary_house_comp_confidence,
            rear_income_confidence=rear_income_confidence,
            optionality_confidence=optionality_confidence,
            has_primary_value=primary_house_value is not None,
            has_rear_value=rear_income_value is not None,
            market_feedback_impact=market_feedback.confidence_impact,
        )
        notes = list(rear_notes)
        notes.extend(market_friction_notes)
        notes.extend(market_feedback.notes)
        if primary_house_value is not None and rear_income_value is not None:
            notes.append("Rear-unit value is treated as an incremental attachment to the front-house anchor rather than as a fully separate apartment asset.")
        if optionality_premium_value:
            notes.append("Optionality premium is capped at a modest share of pre-premium value to avoid double-counting site utility.")
        payload = HybridValueOutput(
            is_hybrid=True,
            reason=str(detection["reason"]),
            detected_primary_structure_type=detection["primary_structure_type"],
            detected_accessory_income_type=detection["accessory_income_type"],
            primary_house_value=primary_house_value,
            primary_house_comp_confidence=primary_house_comp_confidence,
            primary_house_comp_set=primary_house_comp_set,
            rear_income_value=rear_income_value,
            rear_income_method_used=rear_income_method_used,
            rear_income_confidence=rear_income_confidence,
            rent_assumption_summary=rent_assumption_summary,
            optionality_premium_value=optionality_premium_value,
            optionality_reason=optionality_reason,
            optionality_confidence=optionality_confidence,
            low_case_hybrid_value=low_case,
            base_case_hybrid_value=base_case,
            high_case_hybrid_value=high_case,
            confidence=confidence,
            market_friction_discount=market_friction_value,
            market_feedback_adjustment=market_feedback.value_adjustment,
            notes=notes,
            narrative=_narrative(
                reason=str(detection["reason"]),
                primary_house_value=primary_house_value,
                rear_income_value=rear_income_value,
                rear_income_method_used=rear_income_method_used,
                optionality_premium_value=optionality_premium_value,
                optionality_reason=optionality_reason,
                market_friction_discount=market_friction_value,
                market_feedback_adjustment=market_feedback.value_adjustment,
            ),
        )
        return ModuleResult(
            module_name=self.name,
            score=round(confidence * 100, 1),
            confidence=confidence,
            summary=payload.narrative,
            metrics={
                "is_hybrid": True,
                "primary_house_value": primary_house_value,
                "rear_income_value": rear_income_value,
                "optionality_premium_value": optionality_premium_value,
                "low_case_hybrid_value": low_case,
                "base_case_hybrid_value": base_case,
                "high_case_hybrid_value": high_case,
                "confidence": confidence,
                "rear_income_method_used": rear_income_method_used,
                "market_friction_discount": market_friction_value,
                "market_feedback_adjustment": market_feedback.value_adjustment,
            },
            payload=payload,
            section_evidence=build_section_evidence(
                property_input,
                categories=["comp_support", "rent_estimate", "sqft", "listing_history"],
                extra_estimated_inputs=(["rent_estimate"] if "estimated" in rent_assumption_summary.lower() else []),
                notes=["Hybrid valuation decomposes the asset into a front-house comp anchor, accessory-income value, and tightly bounded optionality."],
            ),
        )


def get_hybrid_value_payload(result: ModuleResult) -> HybridValueOutput:
    if not isinstance(result.payload, HybridValueOutput):
        raise TypeError("hybrid_value module payload is not a HybridValueOutput")
    return result.payload


def _detect_hybrid_property(
    property_input: PropertyInput,
    comparable_payload: ComparableSalesOutput,
    income_payload: object,
) -> dict[str, Any]:
    description = (property_input.listing_description or "").lower()
    property_type = (property_input.property_type or "").lower()
    has_accessory = bool(property_input.has_back_house) or bool(property_input.adu_type)
    detached_keywords = ("rear house", "back house", "guest house", "detached cottage", "cottage", "adu")
    keyword_hit = any(keyword in description for keyword in detached_keywords)
    unit_count = max(len([rent for rent in property_input.unit_rents if rent > 0]), 1 if property_input.back_house_monthly_rent else 0)
    accessory_rent = _accessory_monthly_rent(property_input, income_payload=income_payload)
    total_monthly_rent = getattr(income_payload, "monthly_rent_estimate", None) or getattr(income_payload, "effective_monthly_rent", None)
    accessory_material = bool(
        accessory_rent
        and (
            (property_input.purchase_price and (accessory_rent * 12 * 9.0) >= (property_input.purchase_price * 0.08))
            or (total_monthly_rent and accessory_rent / max(float(total_monthly_rent), 1.0) >= 0.25)
        )
    )
    sparse_direct = int(comparable_payload.comp_count or 0) <= 3 or float(comparable_payload.confidence or 0.0) <= 0.58
    multi_like = property_type in {"duplex", "triplex", "fourplex", "multi_family"}
    qualifies = any(
        [
            has_accessory and multi_like,
            has_accessory and sparse_direct,
            keyword_hit and sparse_direct,
            accessory_material,
            multi_like and "single family" in description and keyword_hit,
            unit_count >= 2 and (has_accessory or keyword_hit),
        ]
    )
    reason_parts: list[str] = []
    if has_accessory:
        reason_parts.append("subject includes a back-house or ADU-style accessory improvement")
    if sparse_direct:
        reason_parts.append("pure whole-property comps look thin")
    if accessory_material:
        reason_parts.append("accessory income appears material to value support")
    if keyword_hit:
        reason_parts.append("listing language suggests a detached or atypical rear-unit layout")
    reason = "; ".join(reason_parts) if reason_parts else "subject fits a standard comp pattern"
    return {
        "is_hybrid": qualifies,
        "reason": reason[:1].upper() + reason[1:] if reason else "",
        "primary_structure_type": "single_family_home" if property_type not in {"condo", "townhouse"} else property_type,
        "accessory_income_type": property_input.adu_type or ("rear_cottage" if keyword_hit or property_input.has_back_house else None),
    }


def _standalone_primary_input(property_input: PropertyInput) -> PropertyInput:
    data = property_input.to_dict()

    # Decompose beds/baths to the primary dwelling only.
    # Each additional unit typically represents ~1.5 beds / 1 bath.
    additional_unit_count = len([r for r in property_input.unit_rents if r > 0])
    if additional_unit_count == 0 and (property_input.has_back_house or property_input.adu_type):
        additional_unit_count = 1
    if additional_unit_count > 0 and property_input.beds:
        data["beds"] = max(int(property_input.beds - additional_unit_count * 1.5), 1)
    if additional_unit_count > 0 and property_input.baths:
        data["baths"] = max(property_input.baths - additional_unit_count * 1.0, 1.0)

    # sqft: if adu_sqft is provided and is larger than total sqft, the total
    # sqft likely already represents the primary dwelling alone (common in
    # listings that report main-house sqft separately).
    if property_input.adu_sqft and property_input.sqft:
        if property_input.adu_sqft < property_input.sqft:
            data["sqft"] = max(int(property_input.sqft - property_input.adu_sqft), 400)
        # else: sqft already represents primary dwelling — keep as-is

    data["property_type"] = "Single Family Residence"
    data["has_back_house"] = False
    data["adu_type"] = None
    data["adu_sqft"] = None
    data["back_house_monthly_rent"] = None
    data["unit_rents"] = []
    data["occupancy_strategy"] = None
    return PropertyInput(**data)


def _primary_house_value(
    comparable_payload: ComparableSalesOutput,
) -> tuple[float | None, float, list[HybridCompEntry]]:
    midpoint = None
    if comparable_payload.direct_value_range is not None and comparable_payload.direct_value_range.midpoint is not None:
        midpoint = float(comparable_payload.direct_value_range.midpoint)
    elif comparable_payload.blended_value_range is not None and comparable_payload.blended_value_range.midpoint is not None:
        midpoint = float(comparable_payload.blended_value_range.midpoint)
    elif comparable_payload.comparable_value is not None:
        midpoint = float(comparable_payload.comparable_value)
    confidence = round(float(comparable_payload.comp_confidence_score or comparable_payload.confidence or 0.0), 2)
    comp_set = [
        HybridCompEntry(
            address=comp.address,
            sale_price=float(comp.sale_price),
            adjusted_price=float(comp.adjusted_price),
            sale_date=comp.sale_date,
            fit_label=comp.fit_label,
            property_type=comp.property_type,
        )
        for comp in _best_primary_comps(comparable_payload.comps_used)[:4]
    ]
    return midpoint, confidence, comp_set


def _best_primary_comps(comps: list[AdjustedComparable]) -> list[AdjustedComparable]:
    filtered = [
        comp for comp in comps
        if (getattr(comp, "segmentation_bucket", None) != "income_comps")
    ]
    if not filtered:
        filtered = list(comps)
    return sorted(
        filtered,
        key=lambda comp: (
            -float(getattr(comp, "weighted_score", 0.0) or 0.0),
            float(getattr(comp, "distance_to_subject_miles", 99.0) or 99.0),
            float(abs(float(getattr(comp, "adjusted_price", 0.0) or 0.0))),
        ),
    )


def _rear_income_value(
    property_input: PropertyInput,
    *,
    income_payload: object,
    primary_house_value: float | None,
) -> tuple[float | None, str | None, float, str, list[str]]:
    accessory_rent = _accessory_monthly_rent(property_input, income_payload=income_payload)
    if accessory_rent is None or accessory_rent <= 0:
        return None, None, 0.0, "Accessory income remains too thin to support a separate value increment.", [
            "Rear-unit contribution was not added because accessory rent could not be supported."
        ]

    rent_source = _rent_source_type(property_input, income_payload)
    if rent_source in {"manual", "back_house"}:
        confidence = 0.76
    elif rent_source == "unit_schedule":
        confidence = 0.70
    elif rent_source == "estimated":
        confidence = 0.48
    else:
        confidence = 0.58

    vacancy_friction = 0.10 if confidence < 0.6 else 0.08
    reserve = 0.04 if confidence >= 0.65 else 0.05
    stabilized_annual_rent = accessory_rent * 12.0 * (1.0 - vacancy_friction)
    noi = stabilized_annual_rent * (1.0 - reserve)
    cap_rate = 0.0725 if confidence >= 0.7 else 0.08
    noi_value = noi / cap_rate
    gross_multiplier = 8.75 if confidence >= 0.65 else 7.75
    gross_multiplier_value = accessory_rent * 12.0 * gross_multiplier
    method = "noi_cap_rate" if confidence >= 0.62 else "gross_rent_multiplier"
    raw_value = noi_value if method == "noi_cap_rate" else gross_multiplier_value
    capped_value = _cap_accessory_value(raw_value, primary_house_value=primary_house_value, purchase_price=property_input.purchase_price)
    assumption_summary = (
        f"Accessory rent assumes ${accessory_rent:,.0f}/mo from {rent_source.replace('_', ' ')}, "
        f"{vacancy_friction:.0%} vacancy/friction, and "
        f"{'a light reserve with direct capitalization' if method == 'noi_cap_rate' else f'a {gross_multiplier:.2f}x gross-rent multiplier'}."
    )
    notes = []
    if capped_value < raw_value:
        notes.append("Accessory income value was capped to keep the rear-unit increment conservative relative to the main-house anchor.")
    if confidence < 0.6:
        notes.append("Rear-unit confidence is reduced because rent support or legal clarity is limited.")
    return round(capped_value, 2), method, round(confidence, 2), assumption_summary, notes


def _accessory_monthly_rent(property_input: PropertyInput, *, income_payload: object) -> float | None:
    if property_input.back_house_monthly_rent and property_input.back_house_monthly_rent > 0:
        return float(property_input.back_house_monthly_rent)
    positive_unit_rents = sorted([float(rent) for rent in property_input.unit_rents if rent > 0])
    if len(positive_unit_rents) >= 2:
        return positive_unit_rents[0]
    if len(positive_unit_rents) == 1 and (property_input.has_back_house or property_input.adu_type):
        return positive_unit_rents[0]
    estimated_rent = getattr(income_payload, "monthly_rent_estimate", None) or getattr(property_input, "estimated_monthly_rent", None)
    if (property_input.has_back_house or property_input.adu_type) and estimated_rent:
        return float(estimated_rent) * 0.35
    return None


def _rent_source_type(property_input: PropertyInput, income_payload: object) -> str:
    if property_input.back_house_monthly_rent and property_input.back_house_monthly_rent > 0:
        return "back_house"
    if len([rent for rent in property_input.unit_rents if rent > 0]) >= 2:
        return "unit_schedule"
    source_type = str(getattr(income_payload, "rent_source_type", "") or "").lower()
    if source_type in {"manual_input", "provided"}:
        return "manual"
    if source_type == "estimated":
        return "estimated"
    return "market"


def _cap_accessory_value(
    raw_value: float,
    *,
    primary_house_value: float | None,
    purchase_price: float | None,
) -> float:
    caps = [raw_value]
    if primary_house_value:
        caps.append(primary_house_value * 0.35)
    if purchase_price:
        caps.append(purchase_price * 0.28)
    return max(0.0, min(caps))


def _optionality_premium(
    property_input: PropertyInput,
    *,
    primary_house_value: float | None,
    rear_income_value: float | None,
) -> tuple[float | None, str, float]:
    pre_premium_value = (primary_house_value or 0.0) + (rear_income_value or 0.0)
    if pre_premium_value <= 0:
        return None, "", 0.0
    if property_input.days_on_market and property_input.days_on_market >= 60:
        return 0.0, "No separate rarity premium was applied because stale-listing feedback already constrains optionality.", 0.0

    description = (property_input.listing_description or "").lower()
    signals: list[tuple[str, float]] = []
    if property_input.adu_type and not rear_income_value:
        signals.append((f"{property_input.adu_type.replace('_', ' ')} utility", 0.02))
    if property_input.has_back_house and not rear_income_value:
        signals.append(("detached rear structure utility", 0.015))
    if "beach" in description or "coastal" in description:
        signals.append(("near-beach detached-cottage appeal", 0.0075))
    if "multigenerational" in description or "in-law" in description:
        signals.append(("multigenerational flexibility", 0.01))
    if "garage apartment" in description or "conversion" in description:
        signals.append(("future conversion optionality", 0.01))
    if not signals:
        return 0.0, "No separate rarity premium was applied.", 0.0

    premium_pct = min(sum(weight for _, weight in signals), 0.02)
    premium_value = round(pre_premium_value * premium_pct, 2)
    reason = ", ".join(label for label, _ in signals[:3])
    confidence = round(min(0.72, 0.46 + (0.08 * len(signals))), 2)
    return premium_value, reason, confidence


def _value_range(
    *,
    primary_house_value: float | None,
    rear_income_value: float | None,
    optionality_premium_value: float | None,
    rear_income_confidence: float,
    optionality_confidence: float,
    market_friction_discount: float = 0.0,
    market_feedback_adjustment: float = 0.0,
) -> tuple[float | None, float | None, float | None]:
    if primary_house_value is None:
        return None, None, None
    base_case = (
        primary_house_value
        + (rear_income_value or 0.0)
        + (optionality_premium_value or 0.0)
        + market_friction_discount
        + market_feedback_adjustment
    )
    rear_downside = (rear_income_value or 0.0) * (0.20 if rear_income_confidence >= 0.65 else 0.32)
    rear_upside = (rear_income_value or 0.0) * (0.12 if rear_income_confidence >= 0.65 else 0.18)
    premium_downside = (optionality_premium_value or 0.0) * (0.65 if optionality_confidence < 0.55 else 0.45)
    premium_upside = (optionality_premium_value or 0.0) * (0.15 if optionality_confidence >= 0.6 else 0.05)
    low_case = max(0.0, base_case - rear_downside - premium_downside)
    high_case = base_case + rear_upside + premium_upside
    return round(low_case, 2), round(base_case, 2), round(high_case, 2)


def _overall_confidence(
    *,
    primary_house_comp_confidence: float,
    rear_income_confidence: float,
    optionality_confidence: float,
    has_primary_value: bool,
    has_rear_value: bool,
    market_feedback_impact: float = 0.0,
) -> float:
    if not has_primary_value:
        return 0.0
    base = (primary_house_comp_confidence * 0.62) + (rear_income_confidence * 0.28) + (optionality_confidence * 0.10)
    if not has_rear_value:
        base *= 0.75
    return round(max(0.25, min(base + market_feedback_impact, 0.88)), 2)


def _narrative(
    *,
    reason: str,
    primary_house_value: float | None,
    rear_income_value: float | None,
    rear_income_method_used: str | None,
    optionality_premium_value: float | None,
    optionality_reason: str,
    market_friction_discount: float,
    market_feedback_adjustment: float,
) -> str:
    front_line = (
        "The subject appears to derive value from both its core residential use and accessory income-producing improvements."
    )
    reason_line = f"Briarwood therefore applies a hybrid valuation framework because {reason.lower()}."
    income_line = (
        f"The front house anchors around ${primary_house_value:,.0f}, while the rear improvement contributes roughly ${rear_income_value:,.0f} via "
        f"{'NOI support' if rear_income_method_used == 'noi_cap_rate' else 'a gross-rent multiplier'}."
        if primary_house_value is not None and rear_income_value is not None and rear_income_method_used
        else "Accessory-unit value remains conservative and only receives separate credit where rent support is tangible."
    )
    premium_line = (
        f"A modest optionality premium of about ${optionality_premium_value:,.0f} is layered in for {optionality_reason}."
        if optionality_premium_value
        else "No separate rarity premium is added beyond the supported income increment."
    )
    friction_line = (
        f"Market friction subtracts about ${abs(market_friction_discount):,.0f} for split-structure buyer-pool risk."
        if market_friction_discount < 0
        else ""
    )
    feedback_line = (
        f"Stale-listing feedback subtracts about ${abs(market_feedback_adjustment):,.0f} from the hybrid read."
        if market_feedback_adjustment < 0
        else ""
    )
    return " ".join([line for line in [front_line, reason_line, income_line, premium_line, friction_line, feedback_line] if line])
