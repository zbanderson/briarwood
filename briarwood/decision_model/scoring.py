"""
Briarwood Investment Scoring Engine.

Converts raw AnalysisReport metrics into a 1–5 investment score
with 5 category scores, 20 sub-factor scores, and a recommendation tier.

Metric extraction → sub-factor scoring → category aggregation → final score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from briarwood.decision_model.scoring_config import (
    CATEGORY_WEIGHTS,
    MAX_SCORE,
    MIN_SCORE,
    NEUTRAL_SCORE,
    RECOMMENDATION_TIERS,
    SUB_FACTOR_QUESTIONS,
    SUB_FACTOR_WEIGHTS,
)
from briarwood.schemas import AnalysisReport, PropertyInput


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SubFactorScore:
    name: str
    question: str
    score: float  # 1.0–5.0
    weight: float  # within category
    contribution: float  # score × weight
    evidence: str
    data_source: str
    raw_value: float | str | None = None


@dataclass(slots=True)
class CategoryScore:
    category_name: str
    score: float  # 1.0–5.0, weighted average of sub-factors
    weight: float  # category weight in final score
    contribution: float  # score × weight
    sub_factors: list[SubFactorScore] = field(default_factory=list)


@dataclass(slots=True)
class FinalScore:
    score: float  # 1.0–5.0
    tier: str
    action: str
    narrative: str
    category_scores: dict[str, CategoryScore] = field(default_factory=dict)


# ── Metric extraction ──────────────────────────────────────────────────────────


def _get_metrics(report: AnalysisReport, module_name: str) -> dict[str, Any]:
    result = report.module_results.get(module_name)
    if result is None:
        return {}
    return result.metrics


def _get_confidence(report: AnalysisReport, module_name: str) -> float:
    result = report.module_results.get(module_name)
    return result.confidence if result else 0.0


def _get_payload(report: AnalysisReport, module_name: str) -> Any:
    result = report.module_results.get(module_name)
    return result.payload if result else None


def _prop(report: AnalysisReport) -> PropertyInput | None:
    return report.property_input


def extract_scoring_metrics(report: AnalysisReport) -> dict[str, Any]:
    """Flatten all module metrics into a single dict for scoring functions."""
    m: dict[str, Any] = {}
    pi = _prop(report)

    # ── current_value ──
    cv = _get_metrics(report, "current_value")
    m["bcv"] = cv.get("briarwood_current_value")
    m["mispricing_pct"] = cv.get("mispricing_pct")
    m["pricing_view"] = cv.get("pricing_view")
    m["comparable_sales_value"] = cv.get("comparable_sales_value")
    m["income_supported_value"] = cv.get("income_supported_value")
    m["cv_confidence"] = _get_confidence(report, "current_value")

    # ── comparable_sales ──
    cs = _get_metrics(report, "comparable_sales")
    m["comp_count"] = cs.get("comp_count", 0)
    m["comparable_value"] = cs.get("comparable_value")
    m["comp_confidence"] = cs.get("comp_confidence", 0.0)

    # ── bull_base_bear ──
    bbb = _get_metrics(report, "bull_base_bear")
    m["ask_price"] = bbb.get("ask_price")
    m["base_case_value"] = bbb.get("base_case_value")
    m["bull_case_value"] = bbb.get("bull_case_value")
    m["bear_case_value"] = bbb.get("bear_case_value")
    m["stress_case_value"] = bbb.get("stress_case_value")
    m["base_growth_rate"] = bbb.get("base_growth_rate")
    m["bear_growth_rate"] = bbb.get("bear_growth_rate")
    m["bcv_anchor"] = bbb.get("bcv_anchor")
    m["base_market_drift_pct"] = bbb.get("base_market_drift_pct")
    m["inputs_trailing_1yr"] = bbb.get("inputs_trailing_1yr")
    m["inputs_trailing_3yr_cagr"] = bbb.get("inputs_trailing_3yr_cagr")
    m["inputs_trailing_5yr_cagr"] = bbb.get("inputs_trailing_5yr_cagr")
    m["inputs_town_score"] = bbb.get("inputs_town_score")
    m["inputs_risk_score"] = bbb.get("inputs_risk_score")
    m["inputs_scarcity_score"] = bbb.get("inputs_scarcity_score")

    # ── risk_constraints ──
    rc = _get_metrics(report, "risk_constraints")
    m["risk_flags"] = rc.get("risk_flags", "none")
    m["risk_count"] = rc.get("risk_count", 0)
    m["total_penalty"] = rc.get("total_penalty", 0.0)
    m["risk_score"] = report.module_results.get("risk_constraints", type("", (), {"score": 0.0})).score  # type: ignore[arg-type]
    m["flood_risk"] = rc.get("flood_risk")
    m["vacancy_rate"] = rc.get("vacancy_rate")
    m["data_dimensions_present"] = rc.get("data_dimensions_present", 0)

    # ── income_support ──
    inc = _get_metrics(report, "income_support")
    m["income_support_ratio"] = inc.get("income_support_ratio")
    m["price_to_rent"] = inc.get("price_to_rent")
    m["monthly_cash_flow"] = inc.get("monthly_cash_flow")
    m["operating_cash_flow"] = inc.get("operating_monthly_cash_flow")
    m["downside_burden"] = inc.get("downside_burden")
    m["rent_source_type"] = inc.get("rent_source_type")
    m["risk_view"] = inc.get("risk_view")
    m["financing_complete"] = inc.get("financing_complete", False)
    m["carrying_cost_complete"] = inc.get("carrying_cost_complete", False)

    # ── rental_ease ──
    re = _get_metrics(report, "rental_ease")
    m["rental_ease_score"] = re.get("rental_ease_score")
    m["rental_ease_label"] = re.get("rental_ease_label")
    m["liquidity_score"] = re.get("liquidity_score")
    m["demand_depth_score"] = re.get("demand_depth_score")
    m["estimated_days_to_rent"] = re.get("estimated_days_to_rent")

    # ── town_county_outlook ──
    tco = _get_metrics(report, "town_county_outlook")
    m["town_county_score"] = tco.get("town_county_score")
    m["location_thesis_label"] = tco.get("location_thesis_label")
    m["appreciation_support_view"] = tco.get("appreciation_support_view")
    m["liquidity_view"] = tco.get("liquidity_view")

    # ── scarcity_support ──
    ss = _get_metrics(report, "scarcity_support")
    m["scarcity_support_score"] = ss.get("scarcity_support_score")
    m["scarcity_label"] = ss.get("scarcity_label")

    # ── location_intelligence ──
    li = _get_metrics(report, "location_intelligence")
    m["location_score"] = li.get("location_score")
    m["location_scarcity_score"] = li.get("scarcity_score")
    m["location_premium_pct"] = li.get("location_premium_pct")

    # ── local_intelligence ──
    loc = _get_metrics(report, "local_intelligence")
    m["development_activity_score"] = loc.get("development_activity_score")
    m["supply_pipeline_score"] = loc.get("supply_pipeline_score")
    m["regulatory_trend_score"] = loc.get("regulatory_trend_score")

    # ── market_value_history ──
    mvh = _get_metrics(report, "market_value_history")
    m["zhvi_1yr_change"] = mvh.get("one_year_change_pct")
    m["zhvi_3yr_change"] = mvh.get("three_year_change_pct")

    # ── renovation_scenario ──
    reno = _get_metrics(report, "renovation_scenario")
    m["reno_enabled"] = reno.get("enabled", False)
    m["reno_roi_pct"] = reno.get("roi_pct")
    m["reno_net_value_creation"] = reno.get("net_value_creation")

    # ── teardown_scenario ──
    td = _get_metrics(report, "teardown_scenario")
    m["teardown_enabled"] = td.get("enabled", False)
    m["teardown_annualized_roi"] = td.get("annualized_roi_pct")

    # ── property_input fields ──
    if pi:
        m["purchase_price"] = pi.purchase_price
        m["sqft"] = pi.sqft
        m["beds"] = pi.beds
        m["baths"] = pi.baths
        m["lot_size"] = pi.lot_size
        m["year_built"] = pi.year_built
        m["days_on_market"] = pi.days_on_market
        m["condition_profile"] = pi.condition_profile
        m["capex_lane"] = pi.capex_lane
        m["has_back_house"] = pi.has_back_house
        m["adu_type"] = pi.adu_type
        m["has_basement"] = pi.has_basement
        m["has_pool"] = pi.has_pool
        m["garage_spaces"] = pi.garage_spaces
        m["corner_lot"] = pi.corner_lot
        m["property_type"] = pi.property_type
        m["taxes"] = pi.taxes
    else:
        m["purchase_price"] = m.get("ask_price")

    return m


# ── Utility ────────────────────────────────────────────────────────────────────


def _clamp(score: float) -> float:
    return max(MIN_SCORE, min(MAX_SCORE, score))


def _lerp_score(value: float, lo: float, hi: float, score_at_lo: float, score_at_hi: float) -> float:
    """Linearly interpolate a score between two anchor points."""
    if hi == lo:
        return score_at_lo
    t = (value - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return score_at_lo + t * (score_at_hi - score_at_lo)


def _sf(name: str, score: float, evidence: str, data_source: str, raw: float | str | None, weight: float) -> SubFactorScore:
    """Build a SubFactorScore with auto-clamping and contribution calculation."""
    clamped = _clamp(score)
    return SubFactorScore(
        name=name,
        question=SUB_FACTOR_QUESTIONS.get(name, ""),
        score=clamped,
        weight=weight,
        contribution=round(clamped * weight, 4),
        evidence=evidence,
        data_source=data_source,
        raw_value=raw,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY A: PRICE CONTEXT (25%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_price_vs_comps(m: dict) -> tuple[float, str, float | None]:
    """Ask price vs BCV (comp-derived). Negative mispricing = below comps = good."""
    pct = m.get("mispricing_pct")
    if pct is None:
        return NEUTRAL_SCORE, "No comp-based valuation available", None
    # mispricing_pct in the codebase is (base_case - ask) / ask, so positive = underpriced
    # We want: underpriced (positive pct) = high score
    delta = pct * 100  # convert to percentage points
    if delta >= 10:
        return 5.0, f"Priced {delta:.1f}% below model value — significant discount", delta
    if delta >= 5:
        return 4.0, f"Priced {delta:.1f}% below model — modest discount", delta
    if delta >= -5:
        return 3.0, f"Within ±5% of model value ({delta:+.1f}%)", delta
    if delta >= -15:
        return 2.0, f"Priced {abs(delta):.1f}% above model value — overpriced", delta
    return 1.0, f"Priced {abs(delta):.1f}% above model — significant overprice", delta


def _score_ppsf_positioning(m: dict) -> tuple[float, str, float | None]:
    """Price per sqft vs comp-derived value per sqft."""
    ask = m.get("purchase_price")
    bcv = m.get("bcv")
    sqft = m.get("sqft")
    if not ask or not sqft or sqft == 0:
        return NEUTRAL_SCORE, "Sqft unavailable — cannot calculate $/SF", None
    ask_ppsf = ask / sqft
    if bcv and sqft:
        bcv_ppsf = bcv / sqft
        delta_pct = ((bcv_ppsf - ask_ppsf) / ask_ppsf) * 100
        if delta_pct >= 10:
            return 5.0, f"Ask $/SF ${ask_ppsf:.0f} vs model ${bcv_ppsf:.0f} — {delta_pct:.0f}% below market", delta_pct
        if delta_pct >= 3:
            return 4.0, f"Ask $/SF ${ask_ppsf:.0f} vs model ${bcv_ppsf:.0f} — slightly below market", delta_pct
        if delta_pct >= -5:
            return 3.0, f"Ask $/SF ${ask_ppsf:.0f} roughly in line with model ${bcv_ppsf:.0f}", delta_pct
        if delta_pct >= -15:
            return 2.0, f"Ask $/SF ${ask_ppsf:.0f} above model ${bcv_ppsf:.0f} — premium pricing", delta_pct
        return 1.0, f"Ask $/SF ${ask_ppsf:.0f} significantly above model ${bcv_ppsf:.0f}", delta_pct
    return NEUTRAL_SCORE, f"Ask $/SF ${ask_ppsf:.0f} — no model benchmark available", ask_ppsf


def _score_historical_pricing(m: dict) -> tuple[float, str, float | None]:
    """ZHVI trend support for current pricing level."""
    yr1 = m.get("zhvi_1yr_change")
    yr3 = m.get("inputs_trailing_3yr_cagr")
    if yr1 is None and yr3 is None:
        return NEUTRAL_SCORE, "No ZHVI history available", None
    # Use 3yr CAGR as primary, 1yr as secondary
    trend = yr3 if yr3 is not None else yr1
    trend_pct = (trend or 0) * 100
    label = "3yr CAGR" if yr3 is not None else "1yr change"
    if trend_pct >= 6:
        return 5.0, f"{label} {trend_pct:+.1f}% — strong appreciation momentum", trend_pct
    if trend_pct >= 3:
        return 4.0, f"{label} {trend_pct:+.1f}% — healthy appreciation", trend_pct
    if trend_pct >= 0:
        return 3.0, f"{label} {trend_pct:+.1f}% — flat to modest growth", trend_pct
    if trend_pct >= -5:
        return 2.0, f"{label} {trend_pct:+.1f}% — declining market", trend_pct
    return 1.0, f"{label} {trend_pct:+.1f}% — significant depreciation", trend_pct


def _score_scarcity_premium(m: dict) -> tuple[float, str, float | None]:
    """Does location scarcity justify pricing?"""
    scarcity = m.get("scarcity_support_score") or m.get("location_scarcity_score")
    if scarcity is None:
        return NEUTRAL_SCORE, "No scarcity data available", None
    if scarcity >= 75:
        return 5.0, f"Scarcity score {scarcity:.0f} — highly supply-constrained location", scarcity
    if scarcity >= 60:
        return 4.0, f"Scarcity score {scarcity:.0f} — meaningfully scarce", scarcity
    if scarcity >= 45:
        return 3.0, f"Scarcity score {scarcity:.0f} — moderate supply constraint", scarcity
    if scarcity >= 30:
        return 2.0, f"Scarcity score {scarcity:.0f} — limited supply advantage", scarcity
    return 1.0, f"Scarcity score {scarcity:.0f} — abundant supply, no scarcity premium", scarcity


def _calculate_price_context(m: dict) -> CategoryScore:
    w = SUB_FACTOR_WEIGHTS["price_context"]
    subs = []
    for name, fn, src in [
        ("price_vs_comps", _score_price_vs_comps, "current_value.mispricing_pct"),
        ("ppsf_positioning", _score_ppsf_positioning, "current_value.bcv / sqft"),
        ("historical_pricing", _score_historical_pricing, "market_value_history / bull_base_bear"),
        ("scarcity_premium", _score_scarcity_premium, "scarcity_support.scarcity_support_score"),
    ]:
        score, evidence, raw = fn(m)
        subs.append(_sf(name, score, evidence, src, raw, w[name]))
    cat_score = _clamp(sum(s.contribution for s in subs))
    cw = CATEGORY_WEIGHTS["price_context"]
    return CategoryScore("Price Context", round(cat_score, 2), cw, round(cat_score * cw, 4), subs)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY B: ECONOMIC SUPPORT (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_rent_support(m: dict) -> tuple[float, str, float | None]:
    """Income support ratio: rent / total monthly cost."""
    ratio = m.get("income_support_ratio")
    if ratio is None:
        return NEUTRAL_SCORE, "Income support ratio unavailable", None
    if ratio >= 1.3:
        return 5.0, f"ISR {ratio:.2f}x — strong positive cash flow", ratio
    if ratio >= 1.1:
        return 4.0, f"ISR {ratio:.2f}x — positive cash flow after all costs", ratio
    if ratio >= 0.85:
        return 3.0, f"ISR {ratio:.2f}x — near break-even carry", ratio
    if ratio >= 0.6:
        return 2.0, f"ISR {ratio:.2f}x — meaningful negative carry", ratio
    return 1.0, f"ISR {ratio:.2f}x — heavy negative carry", ratio


def _score_carry_efficiency(m: dict) -> tuple[float, str, float | None]:
    """Price-to-rent ratio as carry efficiency signal."""
    ptr = m.get("price_to_rent")
    if ptr is None:
        return NEUTRAL_SCORE, "Price-to-rent unavailable", None
    if ptr <= 12:
        return 5.0, f"PTR {ptr:.1f}x — exceptional rent yield", ptr
    if ptr <= 16:
        return 4.0, f"PTR {ptr:.1f}x — strong rent support", ptr
    if ptr <= 20:
        return 3.0, f"PTR {ptr:.1f}x — typical for coastal NJ", ptr
    if ptr <= 25:
        return 2.0, f"PTR {ptr:.1f}x — rent doesn't justify price", ptr
    return 1.0, f"PTR {ptr:.1f}x — pure appreciation play, no rent support", ptr


def _score_downside_protection(m: dict) -> tuple[float, str, float | None]:
    """Buffer between BCV and ask — how much downside before underwater."""
    bcv = m.get("bcv")
    ask = m.get("purchase_price") or m.get("ask_price")
    if bcv is None or ask is None or ask == 0:
        return NEUTRAL_SCORE, "Cannot calculate downside buffer", None
    buffer_pct = ((bcv - ask) / ask) * 100
    if buffer_pct >= 10:
        return 5.0, f"BCV {buffer_pct:+.1f}% above ask — strong equity cushion", buffer_pct
    if buffer_pct >= 3:
        return 4.0, f"BCV {buffer_pct:+.1f}% above ask — modest cushion", buffer_pct
    if buffer_pct >= -3:
        return 3.0, f"BCV within ±3% of ask ({buffer_pct:+.1f}%)", buffer_pct
    if buffer_pct >= -10:
        return 2.0, f"BCV {buffer_pct:+.1f}% below ask — limited protection", buffer_pct
    return 1.0, f"BCV {buffer_pct:+.1f}% below ask — buying at a premium", buffer_pct


def _score_replacement_cost(m: dict) -> tuple[float, str, float | None]:
    """Is the property priced below replacement cost (rough $/sqft heuristic)?"""
    ask = m.get("purchase_price") or m.get("ask_price")
    sqft = m.get("sqft")
    lot_size = m.get("lot_size")
    if not ask or not sqft or sqft == 0:
        return NEUTRAL_SCORE, "Cannot estimate replacement cost", None
    ask_ppsf = ask / sqft
    # NJ coastal replacement cost benchmark: $350-$450/sqft new construction
    replacement_ppsf = 400.0
    ratio = ask_ppsf / replacement_ppsf
    if ratio <= 0.6:
        return 5.0, f"Ask ${ask_ppsf:.0f}/SF — well below replacement (~${replacement_ppsf:.0f}/SF)", ratio
    if ratio <= 0.8:
        return 4.0, f"Ask ${ask_ppsf:.0f}/SF — below replacement cost", ratio
    if ratio <= 1.0:
        return 3.0, f"Ask ${ask_ppsf:.0f}/SF — near replacement cost", ratio
    if ratio <= 1.3:
        return 2.0, f"Ask ${ask_ppsf:.0f}/SF — above replacement cost", ratio
    return 1.0, f"Ask ${ask_ppsf:.0f}/SF — significantly above replacement", ratio


def _calculate_economic_support(m: dict) -> CategoryScore:
    w = SUB_FACTOR_WEIGHTS["economic_support"]
    subs = []
    for name, fn, src in [
        ("rent_support", _score_rent_support, "income_support.income_support_ratio"),
        ("carry_efficiency", _score_carry_efficiency, "income_support.price_to_rent"),
        ("downside_protection", _score_downside_protection, "current_value.bcv vs ask"),
        ("replacement_cost", _score_replacement_cost, "property_input.sqft, purchase_price"),
    ]:
        score, evidence, raw = fn(m)
        subs.append(_sf(name, score, evidence, src, raw, w[name]))
    cat_score = _clamp(sum(s.contribution for s in subs))
    cw = CATEGORY_WEIGHTS["economic_support"]
    return CategoryScore("Economic Support", round(cat_score, 2), cw, round(cat_score * cw, 4), subs)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY C: OPTIONALITY (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_adu_expansion(m: dict) -> tuple[float, str, str | None]:
    """Physical capacity for ADU or expansion."""
    has_bh = m.get("has_back_house")
    adu_type = m.get("adu_type")
    lot_size = m.get("lot_size")
    has_basement = m.get("has_basement")
    garage = m.get("garage_spaces") or 0

    signals = 0
    notes = []
    if has_bh:
        signals += 2
        notes.append(f"existing back house/ADU ({adu_type or 'untyped'})")
    if has_basement:
        signals += 1
        notes.append("basement exists")
    if garage >= 2:
        signals += 1
        notes.append(f"{garage} garage spaces — conversion potential")
    if lot_size and lot_size >= 0.2:
        signals += 1
        notes.append(f"{lot_size:.2f} acre lot — room for addition")

    detail = "; ".join(notes) if notes else "no expansion signals detected"
    if signals >= 3:
        return 5.0, f"Strong expansion optionality: {detail}", detail
    if signals == 2:
        return 4.0, f"Good expansion potential: {detail}", detail
    if signals == 1:
        return 3.0, f"Some expansion potential: {detail}", detail
    return 2.0, "Limited physical expansion options", detail


def _score_renovation_upside(m: dict) -> tuple[float, str, float | None]:
    """Does a renovation create value above cost?"""
    if m.get("reno_enabled"):
        roi = m.get("reno_roi_pct")
        if roi is not None:
            if roi >= 50:
                return 5.0, f"Renovation ROI {roi:.0f}% — exceptional value creation", roi
            if roi >= 20:
                return 4.0, f"Renovation ROI {roi:.0f}% — solid return on capex", roi
            if roi >= 0:
                return 3.0, f"Renovation ROI {roi:.0f}% — marginal value creation", roi
            return 2.0, f"Renovation ROI {roi:.0f}% — destroys value", roi

    # No renovation scenario — score based on condition
    condition = (m.get("condition_profile") or "").lower()
    capex = (m.get("capex_lane") or "").lower()
    if condition in ("dated", "needs_work", "needs work") or capex == "heavy":
        return 4.0, "No renovation modeled but property needs work — upside likely exists", condition or capex
    if condition in ("maintained",) or capex == "moderate":
        return 3.0, "Moderate renovation potential based on condition", condition or capex
    if condition in ("updated", "renovated") or capex == "light":
        return 2.0, "Already updated — limited renovation upside", condition or capex
    return NEUTRAL_SCORE, "Condition unknown — cannot assess renovation potential", None


def _score_strategy_flexibility(m: dict) -> tuple[float, str, float | None]:
    """Can the owner pivot between strategies (hold/rent/flip/develop)?"""
    options = 0
    notes = []

    # Rentable?
    isr = m.get("income_support_ratio")
    if isr is not None and isr >= 0.7:
        options += 1
        notes.append("rentable")

    # Renovation path?
    condition = (m.get("condition_profile") or "").lower()
    if condition in ("dated", "needs_work", "needs work", "maintained"):
        options += 1
        notes.append("renovation path")

    # Teardown viable?
    if m.get("teardown_enabled") and (m.get("teardown_annualized_roi") or 0) > 3:
        options += 1
        notes.append("teardown viable")

    # ADU/expansion?
    if m.get("has_back_house") or m.get("has_basement") or (m.get("lot_size") or 0) >= 0.2:
        options += 1
        notes.append("expansion possible")

    # Quick flip (low DOM, underpriced)?
    misp = m.get("mispricing_pct") or 0
    if misp > 0.05:
        options += 1
        notes.append("potential flip")

    detail = ", ".join(notes) if notes else "limited options"
    score = min(5.0, 1.0 + options)
    return score, f"{options} viable strategies: {detail}", options


def _score_zoning_optionality(m: dict) -> tuple[float, str, str | None]:
    """Zoning, lot config, and regulatory environment for future development."""
    reg_score = m.get("regulatory_trend_score")
    lot = m.get("lot_size")
    corner = m.get("corner_lot")
    prop_type = (m.get("property_type") or "").lower()

    signals = 0
    notes = []

    if reg_score is not None and reg_score >= 60:
        signals += 1
        notes.append(f"permissive regulatory trend ({reg_score:.0f})")
    elif reg_score is not None and reg_score < 40:
        notes.append(f"restrictive regulatory environment ({reg_score:.0f})")

    if lot and lot >= 0.25:
        signals += 1
        notes.append(f"{lot:.2f} acre lot — subdivision potential")
    if corner:
        signals += 1
        notes.append("corner lot — better development geometry")
    if "multi" in prop_type or "duplex" in prop_type:
        signals += 1
        notes.append(f"already {prop_type} — zoning likely permissive")

    detail = "; ".join(notes) if notes else "no zoning signals available"
    if signals >= 3:
        return 5.0, f"Strong zoning optionality: {detail}", detail
    if signals == 2:
        return 4.0, f"Good zoning potential: {detail}", detail
    if signals == 1:
        return 3.0, f"Some zoning flexibility: {detail}", detail
    if reg_score is not None and reg_score < 40:
        return 2.0, f"Restrictive environment: {detail}", detail
    return NEUTRAL_SCORE, f"Insufficient zoning data: {detail}", detail


def _calculate_optionality(m: dict) -> CategoryScore:
    w = SUB_FACTOR_WEIGHTS["optionality"]
    subs = []
    for name, fn, src in [
        ("adu_expansion", _score_adu_expansion, "property_input (ADU, basement, lot, garage)"),
        ("renovation_upside", _score_renovation_upside, "renovation_scenario / condition_profile"),
        ("strategy_flexibility", _score_strategy_flexibility, "multi-module synthesis"),
        ("zoning_optionality", _score_zoning_optionality, "local_intelligence.regulatory_trend_score"),
    ]:
        score, evidence, raw = fn(m)
        subs.append(_sf(name, score, evidence, src, raw, w[name]))
    cat_score = _clamp(sum(s.contribution for s in subs))
    cw = CATEGORY_WEIGHTS["optionality"]
    return CategoryScore("Optionality", round(cat_score, 2), cw, round(cat_score * cw, 4), subs)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY D: MARKET POSITION (15%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_dom_signal(m: dict) -> tuple[float, str, float | None]:
    """Days on market — absorption speed signal."""
    dom = m.get("days_on_market")
    if dom is None:
        return NEUTRAL_SCORE, "Days on market unavailable", None
    if dom <= 7:
        return 5.0, f"{dom} DOM — hot demand, absorbing immediately", dom
    if dom <= 21:
        return 4.0, f"{dom} DOM — healthy demand", dom
    if dom <= 45:
        return 3.0, f"{dom} DOM — normal absorption", dom
    if dom <= 90:
        return 2.0, f"{dom} DOM — slow absorption, possible issues", dom
    return 1.0, f"{dom} DOM — stale listing, demand concerns", dom


def _score_inventory_tightness(m: dict) -> tuple[float, str, float | None]:
    """Supply pipeline and scarcity signals."""
    supply = m.get("supply_pipeline_score")
    scarcity = m.get("scarcity_support_score") or m.get("location_scarcity_score")
    if scarcity is None and supply is None:
        return NEUTRAL_SCORE, "No inventory data available", None

    # supply_pipeline_score: higher = more supply coming = less tight
    # scarcity_support_score: higher = more scarce = tighter
    if supply is not None:
        tightness = 100.0 - supply  # invert: low supply pipeline = tight
    else:
        tightness = scarcity or 50.0

    if tightness >= 75:
        return 5.0, f"Very tight inventory (supply tightness {tightness:.0f})", tightness
    if tightness >= 60:
        return 4.0, f"Tight inventory ({tightness:.0f})", tightness
    if tightness >= 40:
        return 3.0, f"Moderate inventory ({tightness:.0f})", tightness
    if tightness >= 25:
        return 2.0, f"Loose inventory ({tightness:.0f})", tightness
    return 1.0, f"Oversupplied market ({tightness:.0f})", tightness


def _score_buyer_seller_balance(m: dict) -> tuple[float, str, float | None]:
    """Market balance based on town score, DOM, and appreciation."""
    town = m.get("town_county_score")
    dom = m.get("days_on_market")
    yr1 = m.get("zhvi_1yr_change")

    signals = []
    score_sum = 0.0
    count = 0

    if town is not None:
        # town_county_score 0-100: higher = stronger market for sellers
        s = _lerp_score(town, 30, 80, 1.0, 5.0)
        signals.append(f"town score {town:.0f}")
        score_sum += s
        count += 1

    if dom is not None:
        s = _lerp_score(dom, 90, 7, 1.0, 5.0)
        signals.append(f"{dom} DOM")
        score_sum += s
        count += 1

    if yr1 is not None:
        pct = yr1 * 100
        s = _lerp_score(pct, -5, 10, 1.0, 5.0)
        signals.append(f"1yr ZHVI {pct:+.1f}%")
        score_sum += s
        count += 1

    if count == 0:
        return NEUTRAL_SCORE, "Insufficient data for market balance assessment", None
    avg = score_sum / count
    detail = ", ".join(signals)
    tone = "seller's market" if avg >= 3.5 else "balanced" if avg >= 2.5 else "buyer's market"
    return avg, f"{tone.title()} ({detail})", avg


def _score_location_momentum(m: dict) -> tuple[float, str, float | None]:
    """Town/county trend direction."""
    town = m.get("town_county_score")
    dev = m.get("development_activity_score")
    yr1 = m.get("zhvi_1yr_change")

    if town is None:
        return NEUTRAL_SCORE, "No town score available", None

    # Weight town score as primary
    base = _lerp_score(town, 30, 80, 1.5, 4.5)

    # Boost/penalize with development activity
    if dev is not None:
        if dev >= 70:
            base = min(5.0, base + 0.3)
        elif dev <= 30:
            base = max(1.0, base - 0.3)

    # Boost/penalize with ZHVI trend
    if yr1 is not None:
        if yr1 >= 0.05:
            base = min(5.0, base + 0.2)
        elif yr1 <= -0.03:
            base = max(1.0, base - 0.3)

    label = m.get("location_thesis_label") or "unknown"
    return base, f"Town score {town:.0f}, thesis '{label}', momentum {base:.1f}", town


def _calculate_market_position(m: dict) -> CategoryScore:
    w = SUB_FACTOR_WEIGHTS["market_position"]
    subs = []
    for name, fn, src in [
        ("dom_signal", _score_dom_signal, "property_input.days_on_market"),
        ("inventory_tightness", _score_inventory_tightness, "scarcity_support / local_intelligence"),
        ("buyer_seller_balance", _score_buyer_seller_balance, "town_county + DOM + ZHVI"),
        ("location_momentum", _score_location_momentum, "town_county_outlook + local_intelligence"),
    ]:
        score, evidence, raw = fn(m)
        subs.append(_sf(name, score, evidence, src, raw, w[name]))
    cat_score = _clamp(sum(s.contribution for s in subs))
    cw = CATEGORY_WEIGHTS["market_position"]
    return CategoryScore("Market Position", round(cat_score, 2), cw, round(cat_score * cw, 4), subs)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY E: RISK LAYER (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_liquidity_risk(m: dict) -> tuple[float, str, float | None]:
    """How quickly could this property be resold?"""
    ease = m.get("rental_ease_score")
    liq = m.get("liquidity_score")
    dom = m.get("days_on_market")

    # Use rental_ease liquidity sub-score if available, else DOM
    if liq is not None:
        if liq >= 75:
            return 5.0, f"High liquidity (score {liq:.0f}) — quick exit possible", liq
        if liq >= 55:
            return 4.0, f"Good liquidity ({liq:.0f})", liq
        if liq >= 40:
            return 3.0, f"Moderate liquidity ({liq:.0f})", liq
        if liq >= 25:
            return 2.0, f"Low liquidity ({liq:.0f}) — exit may take time", liq
        return 1.0, f"Very low liquidity ({liq:.0f}) — illiquid market", liq

    if dom is not None:
        score = _lerp_score(dom, 90, 7, 1.5, 4.5)
        return score, f"Liquidity estimated from {dom} DOM", dom

    return NEUTRAL_SCORE, "No liquidity data available", None


def _score_capex_risk(m: dict) -> tuple[float, str, str | None]:
    """Deferred maintenance and surprise capex exposure."""
    condition = (m.get("condition_profile") or "").lower()
    capex = (m.get("capex_lane") or "").lower()
    year_built = m.get("year_built")

    risk_signals = 0
    notes = []

    if condition in ("needs_work", "needs work"):
        risk_signals += 2
        notes.append("needs work")
    elif condition == "dated":
        risk_signals += 1
        notes.append("dated condition")
    elif condition in ("renovated", "updated"):
        notes.append("recently updated")

    if capex == "heavy":
        risk_signals += 2
        notes.append("heavy capex lane")
    elif capex == "moderate":
        risk_signals += 1
        notes.append("moderate capex")

    if year_built and year_built < 1970:
        risk_signals += 1
        notes.append(f"built {year_built}")

    detail = "; ".join(notes) if notes else "condition unknown"
    # Higher score = LOWER risk (inverted: 5 = safe, 1 = risky)
    if risk_signals == 0 and condition in ("renovated", "updated"):
        return 5.0, f"Low capex risk: {detail}", detail
    if risk_signals == 0:
        return NEUTRAL_SCORE, f"Capex risk unknown: {detail}", detail
    if risk_signals == 1:
        return 3.5, f"Minor capex risk: {detail}", detail
    if risk_signals == 2:
        return 2.5, f"Moderate capex risk: {detail}", detail
    if risk_signals == 3:
        return 1.5, f"Significant capex risk: {detail}", detail
    return 1.0, f"High capex risk: {detail}", detail


def _score_income_stability(m: dict) -> tuple[float, str, float | None]:
    """How reliable and sustainable is the income stream?"""
    source = (m.get("rent_source_type") or "").lower()
    ease_label = (m.get("rental_ease_label") or "").lower()
    burden = m.get("downside_burden")
    risk_view = (m.get("risk_view") or "").lower()

    score = NEUTRAL_SCORE
    notes = []

    # Rent source quality
    if "sourced" in source:
        score += 0.5
        notes.append("sourced rent data")
    elif "estimated" in source:
        notes.append("estimated rent")
    elif "missing" in source:
        score -= 0.5
        notes.append("no rent data")

    # Rental ease
    if ease_label in ("very_easy", "easy"):
        score += 0.5
        notes.append(f"rental ease: {ease_label}")
    elif ease_label in ("difficult", "very_difficult"):
        score -= 0.5
        notes.append(f"rental ease: {ease_label}")

    # Downside burden
    if burden is not None:
        if burden <= 0.6:
            score += 0.5
            notes.append(f"low downside burden ({burden:.0%})")
        elif burden >= 0.9:
            score -= 0.5
            notes.append(f"high downside burden ({burden:.0%})")

    # Risk view
    if "strong" in risk_view:
        score += 0.3
    elif "negative" in risk_view:
        score -= 0.5

    detail = "; ".join(notes) if notes else "limited income data"
    return _clamp(score), f"Income stability: {detail}", score


def _score_macro_regulatory(m: dict) -> tuple[float, str, str | None]:
    """Flood, regulatory, and macro headwinds."""
    flood = (m.get("flood_risk") or "").lower()
    reg = m.get("regulatory_trend_score")
    risk_flags = m.get("risk_flags") or "none"
    total_penalty = m.get("total_penalty") or 0.0

    score = 4.0  # Start optimistic, deduct for issues
    notes = []

    # Flood
    if flood == "high":
        score -= 1.5
        notes.append("high flood risk")
    elif flood == "medium":
        score -= 0.8
        notes.append("medium flood risk")
    elif flood in ("low", "none", "minimal"):
        notes.append("low flood risk")

    # Regulatory
    if reg is not None:
        if reg < 35:
            score -= 0.5
            notes.append(f"restrictive regulatory ({reg:.0f})")
        elif reg >= 65:
            notes.append(f"permissive regulatory ({reg:.0f})")

    # Accumulated risk penalties
    if total_penalty > 15:
        score -= 0.5
        notes.append(f"high accumulated penalties ({total_penalty:.0f}pts)")
    elif total_penalty > 8:
        score -= 0.3
        notes.append(f"moderate penalties ({total_penalty:.0f}pts)")

    detail = "; ".join(notes) if notes else "no macro/regulatory flags"
    return _clamp(score), f"Macro/regulatory: {detail}", detail


def _calculate_risk_layer(m: dict) -> CategoryScore:
    w = SUB_FACTOR_WEIGHTS["risk_layer"]
    subs = []
    for name, fn, src in [
        ("liquidity_risk", _score_liquidity_risk, "rental_ease.liquidity_score"),
        ("capex_risk", _score_capex_risk, "property_input (condition, capex, year)"),
        ("income_stability", _score_income_stability, "income_support + rental_ease"),
        ("macro_regulatory", _score_macro_regulatory, "risk_constraints + local_intelligence"),
    ]:
        score, evidence, raw = fn(m)
        subs.append(_sf(name, score, evidence, src, raw, w[name]))
    cat_score = _clamp(sum(s.contribution for s in subs))
    cw = CATEGORY_WEIGHTS["risk_layer"]
    return CategoryScore("Risk Layer", round(cat_score, 2), cw, round(cat_score * cw, 4), subs)


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SCORE
# ═══════════════════════════════════════════════════════════════════════════════


def get_recommendation_tier(score: float) -> tuple[str, str]:
    for threshold, tier, action in RECOMMENDATION_TIERS:
        if score >= threshold:
            return tier, action
    return "Avoid", "Does not meet investment criteria on current information."


def _generate_narrative(score: float, categories: dict[str, CategoryScore]) -> str:
    """Generate a 2-3 sentence narrative summarizing the score."""
    tier, _ = get_recommendation_tier(score)
    ranked = sorted(categories.values(), key=lambda c: c.score, reverse=True)
    strongest = ranked[0]
    weakest = ranked[-1]

    parts = [f"Overall score {score:.2f}/5.0 — {tier}."]

    if strongest.score >= 4.0:
        parts.append(f"Strongest dimension is {strongest.category_name} ({strongest.score:.1f}/5).")
    if weakest.score <= 2.5:
        parts.append(f"Weakest dimension is {weakest.category_name} ({weakest.score:.1f}/5) — this is the primary risk to the thesis.")
    elif weakest.score <= 3.0:
        parts.append(f"{weakest.category_name} ({weakest.score:.1f}/5) is the area most worth investigating further.")

    return " ".join(parts)


def calculate_final_score(report: AnalysisReport) -> FinalScore:
    """Run the complete scoring pipeline on an AnalysisReport."""
    m = extract_scoring_metrics(report)

    categories = {
        "price_context": _calculate_price_context(m),
        "economic_support": _calculate_economic_support(m),
        "optionality": _calculate_optionality(m),
        "market_position": _calculate_market_position(m),
        "risk_layer": _calculate_risk_layer(m),
    }

    final = _clamp(sum(cat.contribution for cat in categories.values()))
    final = round(final, 2)
    tier, action = get_recommendation_tier(final)
    narrative = _generate_narrative(final, categories)

    return FinalScore(
        score=final,
        tier=tier,
        action=action,
        narrative=narrative,
        category_scores=categories,
    )
