from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from briarwood.modules.hybrid_value import get_hybrid_value_payload
from briarwood.modules.town_aggregation_diagnostics import get_town_context
from briarwood.modules.town_county_outlook import get_town_county_outlook_payload
from briarwood.schemas import AnalysisReport


@dataclass(slots=True)
class ValueFinderOutput:
    value_gap_pct: float | None
    comp_gap_pct: float | None
    market_friction_score: float
    cut_pressure_score: float
    opportunity_signal: str
    pricing_posture: str
    dom_signal: str
    short_summary: str
    confidence_note: str
    evidence_strength: str
    metrics: dict[str, Any]


@dataclass(slots=True)
class PropertyValueFinderOutput:
    bullets: list[str]
    metrics: dict[str, Any]


def analyze_value_finder(
    *,
    asking_price: float | None,
    briarwood_value: float | None = None,
    comp_median: float | None = None,
    comp_low: float | None = None,
    comp_high: float | None = None,
    days_on_market: int | None = None,
    price_cut_count: int | None = None,
    total_price_cut_pct: float | None = None,
    town_dom_trend: float | None = None,
    town_inventory_trend: float | None = None,
    subject_price_per_sqft: float | None = None,
    cohort_price_per_sqft: float | None = None,
    confidence: float | None = None,
    similar_listing_dom: float | None = None,
    relist_count: int | None = None,
) -> ValueFinderOutput:
    value_gap_pct = _gap_pct(reference_value=briarwood_value, asking_price=asking_price)
    comp_gap_pct = _gap_pct(reference_value=comp_median, asking_price=asking_price)
    ppsf_gap_pct = _ppsf_gap_pct(subject_price_per_sqft=subject_price_per_sqft, cohort_price_per_sqft=cohort_price_per_sqft)

    pricing_inputs = [gap for gap in [value_gap_pct, comp_gap_pct, ppsf_gap_pct] if gap is not None]
    pricing_score = _pricing_score(pricing_inputs)
    market_friction_score = _market_friction_score(
        days_on_market=days_on_market,
        town_dom_trend=town_dom_trend,
        town_inventory_trend=town_inventory_trend,
        similar_listing_dom=similar_listing_dom,
    )
    cut_pressure_score = _cut_pressure_score(
        price_cut_count=price_cut_count,
        total_price_cut_pct=total_price_cut_pct,
        relist_count=relist_count,
        days_on_market=days_on_market,
        market_friction_score=market_friction_score,
    )
    pricing_posture = _pricing_posture(pricing_score)
    dom_signal = _dom_signal(days_on_market=days_on_market, market_friction_score=market_friction_score)
    evidence_strength, confidence_note = _confidence_note(
        pricing_inputs=pricing_inputs,
        confidence=confidence,
        comp_low=comp_low,
        comp_high=comp_high,
        days_on_market=days_on_market,
    )
    opportunity_signal = _opportunity_signal(
        pricing_score=pricing_score,
        market_friction_score=market_friction_score,
        cut_pressure_score=cut_pressure_score,
        evidence_strength=evidence_strength,
    )
    summary = _summary(
        pricing_posture=pricing_posture,
        dom_signal=dom_signal,
        opportunity_signal=opportunity_signal,
        value_gap_pct=value_gap_pct,
        comp_gap_pct=comp_gap_pct,
        days_on_market=days_on_market,
        cut_pressure_score=cut_pressure_score,
    )

    return ValueFinderOutput(
        value_gap_pct=_round_or_none(value_gap_pct, 4),
        comp_gap_pct=_round_or_none(comp_gap_pct, 4),
        market_friction_score=round(market_friction_score, 1),
        cut_pressure_score=round(cut_pressure_score, 1),
        opportunity_signal=opportunity_signal,
        pricing_posture=pricing_posture,
        dom_signal=dom_signal,
        short_summary=summary,
        confidence_note=confidence_note,
        evidence_strength=evidence_strength,
        metrics={
            "pricing_score": round(pricing_score, 1),
            "ppsf_gap_pct": _round_or_none(ppsf_gap_pct, 4),
            "comp_low": comp_low,
            "comp_high": comp_high,
            "days_on_market": days_on_market,
            "price_cut_count": price_cut_count,
            "total_price_cut_pct": total_price_cut_pct,
            "town_dom_trend": town_dom_trend,
            "town_inventory_trend": town_inventory_trend,
            "similar_listing_dom": similar_listing_dom,
            "relist_count": relist_count,
        },
    )


def analyze_property_value_finder(report: AnalysisReport) -> PropertyValueFinderOutput:
    property_input = report.property_input
    current_value = report.module_results.get("current_value")
    current_metrics = current_value.metrics if current_value is not None else {}
    income_support = report.module_results.get("income_support")
    income_metrics = income_support.metrics if income_support is not None else {}
    hybrid_module = report.module_results.get("hybrid_value")
    hybrid = get_hybrid_value_payload(hybrid_module) if hybrid_module is not None else None
    town_module = report.module_results.get("town_county_outlook")
    town = get_town_county_outlook_payload(town_module) if town_module is not None else None
    scarcity = report.module_results.get("scarcity_support")
    scarcity_metrics = scarcity.metrics if scarcity is not None else {}
    market_momentum = report.module_results.get("market_momentum_signal")
    market_momentum_metrics = market_momentum.metrics if market_momentum is not None else {}

    candidates: list[tuple[float, str, str]] = []

    price_gap = _as_float(current_metrics.get("net_opportunity_delta_pct"))
    if price_gap is None:
        price_gap = _as_float(current_metrics.get("mispricing_pct"))
    if price_gap is not None and price_gap >= 0.06:
        candidates.append(
            (
                64.0 + (min(price_gap, 0.20) * 120.0),
                "pricing",
                f"Price sits ~{round(price_gap * 100):.0f}% below fair value",
            )
        )

    income_bullet = _income_bullet(property_input, income_metrics, hybrid)
    if income_bullet is not None:
        candidates.append((92.0, "income", income_bullet))

    expansion_bullet = _expansion_bullet(property_input)
    if expansion_bullet is None:
        expansion_bullet = _lot_flexibility_bullet(property_input)
    if expansion_bullet is not None:
        candidates.append((70.0, "expansion", expansion_bullet))

    strategy_bullet = _strategy_flexibility_bullet(property_input, hybrid, income_metrics)
    if strategy_bullet is not None:
        candidates.append((72.0, "strategy", strategy_bullet))

    town_bullet = _town_tailwind_bullet(
        town=town,
        scarcity_metrics=scarcity_metrics,
        market_momentum_metrics=market_momentum_metrics,
        market_momentum_confidence=float(market_momentum.confidence) if market_momentum is not None else 0.0,
    )
    if town_bullet is not None:
        candidates.append((58.0, "market", town_bullet))

    bullets = _dedupe_and_rank(candidates)[:4]
    return PropertyValueFinderOutput(
        bullets=bullets,
        metrics={
            "bullet_count": len(bullets),
            "price_gap_pct": price_gap,
            "has_hybrid_value": bool(hybrid.is_hybrid) if hybrid is not None else False,
        },
    )


def _gap_pct(*, reference_value: float | None, asking_price: float | None) -> float | None:
    if reference_value in (None, 0) or asking_price in (None, 0):
        return None
    return (float(reference_value) - float(asking_price)) / float(asking_price)


def _ppsf_gap_pct(*, subject_price_per_sqft: float | None, cohort_price_per_sqft: float | None) -> float | None:
    if subject_price_per_sqft in (None, 0) or cohort_price_per_sqft in (None, 0):
        return None
    return (float(cohort_price_per_sqft) - float(subject_price_per_sqft)) / float(subject_price_per_sqft)


def _pricing_score(gaps: list[float]) -> float:
    if not gaps:
        return 5.0
    clipped = [max(-0.18, min(gap, 0.18)) for gap in gaps]
    avg_gap = sum(clipped) / len(clipped)
    return max(0.0, min(10.0, 5.0 + (avg_gap / 0.18) * 5.0))


def _market_friction_score(
    *,
    days_on_market: int | None,
    town_dom_trend: float | None,
    town_inventory_trend: float | None,
    similar_listing_dom: float | None,
) -> float:
    score = 0.0
    if days_on_market is not None:
        if days_on_market <= 21:
            score += 1.5
        elif days_on_market <= 45:
            score += 3.5
        elif days_on_market <= 75:
            score += 6.0
        else:
            score += 8.2
    else:
        score += 4.0
    if town_dom_trend is not None:
        if town_dom_trend >= 0.10:
            score += 1.0
        elif town_dom_trend <= -0.10:
            score -= 0.8
    if town_inventory_trend is not None:
        if town_inventory_trend >= 0.10:
            score += 0.8
        elif town_inventory_trend <= -0.10:
            score -= 0.6
    if days_on_market is not None and similar_listing_dom not in (None, 0):
        if float(days_on_market) >= float(similar_listing_dom) * 1.4:
            score += 1.0
        elif float(days_on_market) <= float(similar_listing_dom) * 0.8:
            score -= 0.7
    return max(0.0, min(10.0, score))


def _cut_pressure_score(
    *,
    price_cut_count: int | None,
    total_price_cut_pct: float | None,
    relist_count: int | None,
    days_on_market: int | None,
    market_friction_score: float,
) -> float:
    score = max(0.0, market_friction_score - 2.0)
    if price_cut_count:
        score += min(float(price_cut_count) * 1.6, 3.2)
    if total_price_cut_pct is not None:
        score += min(max(total_price_cut_pct, 0.0) / 0.08, 3.0)
    if relist_count:
        score += min(float(relist_count) * 1.5, 2.0)
    if days_on_market is not None and days_on_market >= 90:
        score += 0.8
    return max(0.0, min(10.0, score))


def _pricing_posture(pricing_score: float) -> str:
    if pricing_score >= 6.7:
        return "Attractive vs Baseline"
    if pricing_score <= 3.6:
        return "Rich vs Baseline"
    return "Near Baseline"


def _dom_signal(*, days_on_market: int | None, market_friction_score: float) -> str:
    if days_on_market is None:
        return "DOM signal is limited"
    if days_on_market <= 21:
        return "Moving on a normal timeline"
    if days_on_market <= 45:
        return "Normal marketing period"
    if days_on_market <= 75:
        return "Showing clear market friction"
    if market_friction_score >= 7.0:
        return "Stale listing; seller leverage likely weakening"
    return "Prolonged market time"


def _confidence_note(
    *,
    pricing_inputs: list[float],
    confidence: float | None,
    comp_low: float | None,
    comp_high: float | None,
    days_on_market: int | None,
) -> tuple[str, str]:
    evidence_count = len(pricing_inputs)
    if comp_low is not None and comp_high is not None:
        evidence_count += 1
    if days_on_market is not None:
        evidence_count += 1
    strength = "high" if evidence_count >= 4 and (confidence or 0.0) >= 0.7 else "medium" if evidence_count >= 2 else "low"
    if strength == "high":
        return strength, "Signal is supported by both pricing anchors and live market behavior."
    if strength == "medium":
        return strength, "Signal is directionally useful, but at least one anchor is still thin."
    return strength, "Treat this as a watchlist signal, not a decisive value call, because pricing support is still limited."


def _opportunity_signal(
    *,
    pricing_score: float,
    market_friction_score: float,
    cut_pressure_score: float,
    evidence_strength: str,
) -> str:
    if pricing_score <= 3.4 and (market_friction_score >= 7.0 or cut_pressure_score >= 6.5):
        return "Needs Price Reset"
    if pricing_score <= 3.8:
        return "Rich / Market Resisting"
    if pricing_score >= 6.8 and market_friction_score <= 4.8 and cut_pressure_score <= 4.0:
        return "Possible Value"
    if pricing_score >= 5.8 and (market_friction_score >= 5.0 or cut_pressure_score >= 4.5):
        return "Emerging Opportunity"
    if evidence_strength == "low" and (market_friction_score >= 6.0 or cut_pressure_score >= 5.0):
        return "Watch for Cut"
    if market_friction_score >= 6.5 or cut_pressure_score >= 5.5:
        return "Watch for Cut"
    return "Fairly Priced"


def _summary(
    *,
    pricing_posture: str,
    dom_signal: str,
    opportunity_signal: str,
    value_gap_pct: float | None,
    comp_gap_pct: float | None,
    days_on_market: int | None,
    cut_pressure_score: float,
) -> str:
    pricing_line = pricing_posture.lower()
    if value_gap_pct is not None:
        pricing_line = f"{pricing_posture.lower()} with ask at about {abs(value_gap_pct) * 100:.0f}% {'below' if value_gap_pct >= 0 else 'above'} Briarwood Value"
    elif comp_gap_pct is not None:
        pricing_line = f"{pricing_posture.lower()} with ask at about {abs(comp_gap_pct) * 100:.0f}% {'below' if comp_gap_pct >= 0 else 'above'} the comp midpoint"
    dom_line = dom_signal.lower()
    if days_on_market is not None:
        dom_line = f"{days_on_market} DOM; {dom_signal.lower()}"
    if opportunity_signal == "Possible Value":
        return f"{pricing_line}, and {dom_line}. This screens as attractive now rather than just a seller under pressure."
    if opportunity_signal == "Emerging Opportunity":
        return f"{pricing_line}, and {dom_line}. Pricing looks closer to support, but the setup is still developing."
    if opportunity_signal == "Watch for Cut":
        return f"{pricing_line}, and {dom_line}. Seller leverage appears to be weakening, but it is not a clean value signal yet."
    if opportunity_signal == "Needs Price Reset":
        return f"{pricing_line}, and {dom_line}. Market friction and cut pressure both suggest the current ask is still too high."
    if opportunity_signal == "Rich / Market Resisting":
        return f"{pricing_line}, and {dom_line}. The market looks more resistant than opportunistic at this level."
    return f"{pricing_line}, and {dom_line}. Right now this reads closer to fair than to a clear value dislocation."


def _round_or_none(value: float | None, places: int) -> float | None:
    return None if value is None else round(value, places)


def _income_bullet(property_input: object, income_metrics: dict[str, Any], hybrid: object) -> str | None:
    if hybrid is not None and getattr(hybrid, "is_hybrid", False):
        monthly_rent = _best_accessory_monthly_rent(property_input, income_metrics)
        if monthly_rent is not None and monthly_rent >= 500:
            return f"{_accessory_label(property_input, getattr(hybrid, 'detected_accessory_income_type', None))} income (~{_compact_currency_monthly(monthly_rent)}/mo)"
    unit_count = _rentable_unit_count(property_input, income_metrics)
    total_rent = _best_total_monthly_rent(income_metrics)
    if unit_count >= 2 and total_rent is not None and total_rent >= 1500:
        return f"Multi-unit income support (~{_compact_currency_monthly(total_rent)}/mo)"
    return None


def _expansion_bullet(property_input: object) -> str | None:
    if property_input is None:
        return None
    bits: list[str] = []
    if bool(getattr(property_input, "has_detached_garage", False)) or str(getattr(property_input, "garage_type", "") or "").strip().lower() == "detached":
        bits.append("detached garage")
    elif isinstance(getattr(property_input, "garage_spaces", None), (int, float)) and float(property_input.garage_spaces) >= 2:
        bits.append("garage footprint")
    if bool(getattr(property_input, "has_basement", False)) and not bool(getattr(property_input, "basement_finished", False)):
        bits.append("unfinished basement")
    if not bits:
        return None
    return f"Expansion upside ({' / '.join(bits[:2])})"


def _lot_flexibility_bullet(property_input: object) -> str | None:
    if property_input is None or not getattr(property_input, "town", None):
        return None
    town_context = get_town_context(getattr(property_input, "town", None))
    lot_size = _as_float(getattr(property_input, "lot_size", None))
    median_lot = _as_float(getattr(town_context, "median_lot_size", None)) if town_context is not None else None
    town_confidence = _as_float(getattr(town_context, "context_confidence", None)) if town_context is not None else None
    if lot_size in (None, 0) or median_lot in (None, 0) or town_confidence is None or town_confidence < 0.6:
        return None
    if lot_size / median_lot < 1.2:
        return None
    return "Larger-than-typical lot adds expansion flexibility"


def _strategy_flexibility_bullet(property_input: object, hybrid: object, income_metrics: dict[str, Any]) -> str | None:
    occupancy_strategy = str(getattr(property_input, "occupancy_strategy", "") or income_metrics.get("occupancy_strategy") or "").lower()
    if occupancy_strategy == "owner_occupy_partial":
        return "Live-in with rental offset"
    if hybrid is not None and getattr(hybrid, "is_hybrid", False):
        return "Primary home plus rental offset flexibility"
    if _rentable_unit_count(property_input, income_metrics) >= 2:
        return "Flexible hold or house-hack setup"
    return None


def _town_tailwind_bullet(
    *,
    town: object,
    scarcity_metrics: dict[str, Any],
    market_momentum_metrics: dict[str, Any],
    market_momentum_confidence: float,
) -> str | None:
    if town is None:
        return None
    town_score = _as_float(getattr(getattr(town, "score", None), "town_county_score", None))
    town_confidence = _as_float(getattr(town, "confidence", None)) or 0.0
    scarcity_score = _as_float(scarcity_metrics.get("scarcity_support_score"))
    scarcity_label = str(scarcity_metrics.get("scarcity_label") or "").lower()
    momentum_score = _as_float(market_momentum_metrics.get("market_momentum_score"))

    if scarcity_score is not None and scarcity_score >= 62 and scarcity_label != "low-confidence" and town_confidence >= 0.45:
        return "Scarcity-supported town demand"
    if town_score is not None and town_score >= 65 and town_confidence >= 0.60:
        return "Strong long-term town demand"
    if momentum_score is not None and momentum_score >= 62 and market_momentum_confidence >= 0.50:
        return "Constructive local momentum"
    return None


def _best_accessory_monthly_rent(property_input: object, income_metrics: dict[str, Any]) -> float | None:
    if property_input is not None:
        back_house_rent = _as_float(getattr(property_input, "back_house_monthly_rent", None))
        if back_house_rent is not None and back_house_rent > 0:
            return back_house_rent
        unit_rents = [float(rent) for rent in getattr(property_input, "unit_rents", []) if isinstance(rent, (int, float)) and rent > 0]
        if len(unit_rents) == 1:
            return unit_rents[0]
    return _as_float(income_metrics.get("avg_rent_per_unit"))


def _best_total_monthly_rent(income_metrics: dict[str, Any]) -> float | None:
    return (
        _as_float(income_metrics.get("monthly_rent_estimate"))
        or _as_float(income_metrics.get("effective_monthly_rent"))
        or _as_float(income_metrics.get("gross_monthly_rent_before_vacancy"))
    )


def _rentable_unit_count(property_input: object, income_metrics: dict[str, Any]) -> int:
    manual_unit_rents = [rent for rent in getattr(property_input, "unit_rents", []) if isinstance(rent, (int, float)) and rent > 0]
    if manual_unit_rents:
        return len(manual_unit_rents)
    num_units = income_metrics.get("num_units")
    return int(num_units) if isinstance(num_units, (int, float)) else 0


def _accessory_label(property_input: object, detected_type: str | None) -> str:
    adu_type = str(getattr(property_input, "adu_type", "") or detected_type or "").replace("_", " ").strip().lower()
    if "cottage" in adu_type:
        return "Detached cottage"
    if "garage" in adu_type:
        return "Garage unit"
    if "basement" in adu_type:
        return "Basement unit"
    if adu_type:
        return adu_type.title()
    if bool(getattr(property_input, "has_back_house", False)):
        return "Back-house"
    return "Accessory-unit"


def _dedupe_and_rank(candidates: list[tuple[float, str, str]]) -> list[str]:
    selected: dict[str, tuple[float, str]] = {}
    for score, key, label in candidates:
        if not label:
            continue
        existing = selected.get(key)
        if existing is None or score > existing[0]:
            selected[key] = (score, label)
    ranked = sorted(selected.values(), key=lambda item: item[0], reverse=True)
    return [label for _, label in ranked]


def _compact_currency_monthly(value: float) -> str:
    if value >= 10_000:
        return f"${value / 1_000:.0f}k"
    if value >= 1_000:
        return f"${value / 1_000:.1f}k".replace(".0k", "k")
    return f"${value:,.0f}"


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
