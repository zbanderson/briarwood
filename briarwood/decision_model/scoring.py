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
from briarwood.modules.town_aggregation_diagnostics import get_town_context
from briarwood.schemas import AnalysisReport, PropertyInput
from briarwood.settings import DEFAULT_DECISION_MODEL_SETTINGS, DecisionModelSettings


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
    component_scores: dict[str, float] = field(default_factory=dict)
    component_notes: dict[str, str] = field(default_factory=dict)
    unscored_factors: list[str] = field(default_factory=list)
    weight_redistributed: bool = False


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


def _estimate_comp_renovation_premium(report: AnalysisReport) -> dict[str, Any]:
    """Estimate renovation premium from comp condition data.

    Compares median $/sqft of renovated/updated comps vs dated/needs_work comps.
    First tries the matched comp set; if insufficient condition data, falls back
    to the full comp database filtered to the subject's town.
    Returns a dict with premium_pct, estimated_renovated_value, sample counts,
    and a narrative snippet.  Empty dict if insufficient data.
    """
    import statistics
    from pathlib import Path

    pi = report.property_input
    subject_town = (pi.town or "").lower() if pi else ""

    upper: list[float] = []   # renovated / updated comps — $/sqft
    lower: list[float] = []   # dated / needs_work comps — $/sqft
    upper_count = 0
    lower_count = 0
    source = "matched"

    # First: try matched comps
    comp_payload = _get_payload(report, "comparable_sales")
    if comp_payload is not None and hasattr(comp_payload, "comps_used"):
        for c in (comp_payload.comps_used or []):
            cond = (getattr(c, "condition_profile", None) or "").lower()
            sqft = getattr(c, "sqft", None)
            adj_price = getattr(c, "adjusted_price", None)
            if adj_price is None or not sqft or sqft <= 0:
                continue
            ppsf = adj_price / sqft
            if cond in ("renovated", "updated"):
                upper.append(ppsf)
                upper_count += 1
            elif cond in ("dated", "needs_work"):
                lower.append(ppsf)
                lower_count += 1

    # Fallback: scan the full comp database for the same town
    if (not upper or not lower) and subject_town:
        source = "database"
        try:
            import json
            db_path = Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
            if db_path.exists():
                with open(db_path) as f:
                    db = json.load(f)
                sales = db.get("sales", []) if isinstance(db, dict) else db
                upper = []
                lower = []
                upper_count = 0
                lower_count = 0
                for sale in sales:
                    if not isinstance(sale, dict):
                        continue
                    town = (sale.get("town") or "").lower()
                    if town != subject_town:
                        continue
                    cond = (sale.get("condition_profile") or "").lower()
                    sqft = sale.get("sqft")
                    price = sale.get("sale_price")
                    if price is None or not sqft or sqft <= 0:
                        continue
                    ppsf = price / sqft
                    if cond in ("renovated", "updated"):
                        upper.append(ppsf)
                        upper_count += 1
                    elif cond in ("dated", "needs_work", "maintained"):
                        lower.append(ppsf)
                        lower_count += 1
        except Exception:
            pass

    result: dict[str, Any] = {
        "renovated_comp_count": upper_count,
        "dated_comp_count": lower_count,
        "renovation_premium_source": source,
    }

    if not upper or not lower:
        return result

    median_upper = statistics.median(upper)
    median_lower = statistics.median(lower)

    if median_lower <= 0:
        return result

    premium_pct = (median_upper - median_lower) / median_lower

    # Estimate what the subject would be worth renovated
    bcv_metrics = _get_metrics(report, "current_value")
    bcv = bcv_metrics.get("briarwood_current_value")

    estimated_renovated_value = None
    estimated_value_creation = None
    if bcv and premium_pct > 0:
        estimated_renovated_value = round(bcv * (1 + premium_pct))
        estimated_value_creation = estimated_renovated_value - bcv

    result.update({
        "renovation_premium_pct": round(premium_pct, 3),
        "median_renovated_ppsf": round(median_upper, 2),
        "median_dated_ppsf": round(median_lower, 2),
        "estimated_renovated_value": estimated_renovated_value,
        "estimated_value_creation": estimated_value_creation,
    })
    return result


def extract_scoring_metrics(report: AnalysisReport) -> dict[str, Any]:
    """Flatten all module metrics into a single dict for scoring functions."""
    m: dict[str, Any] = {}
    pi = _prop(report)

    # ── current_value ──
    cv = _get_metrics(report, "current_value")
    m["bcv"] = cv.get("briarwood_current_value")
    m["mispricing_pct"] = cv.get("mispricing_pct")
    m["all_in_basis"] = cv.get("all_in_basis")
    m["capex_basis_used"] = cv.get("capex_basis_used")
    m["capex_basis_source"] = cv.get("capex_basis_source")
    m["net_opportunity_delta_value"] = cv.get("net_opportunity_delta_value")
    m["net_opportunity_delta_pct"] = cv.get("net_opportunity_delta_pct")
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
    m["rental_liquidity_score"] = re.get("liquidity_score")
    m["demand_depth_score"] = re.get("demand_depth_score")
    m["estimated_days_to_rent"] = re.get("estimated_days_to_rent")

    # ── liquidity_signal ──
    ls = _get_metrics(report, "liquidity_signal")
    m["liquidity_score"] = ls.get("liquidity_score")
    m["liquidity_label"] = ls.get("liquidity_label")
    m["market_liquidity_score"] = ls.get("market_liquidity_score")
    m["comp_depth_score"] = ls.get("comp_depth_score")

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

    # ── market_momentum_signal ──
    mm = _get_metrics(report, "market_momentum_signal")
    m["market_momentum_score"] = mm.get("market_momentum_score")
    m["market_momentum_label"] = mm.get("market_momentum_label")

    # ── market_value_history ──
    mvh = _get_metrics(report, "market_value_history")
    m["zhvi_1yr_change"] = mvh.get("one_year_change_pct")
    m["zhvi_3yr_change"] = mvh.get("three_year_change_pct")

    # ── renovation_scenario ──
    reno = _get_metrics(report, "renovation_scenario")
    m["reno_enabled"] = reno.get("enabled", False)
    m["reno_roi_pct"] = reno.get("roi_pct")
    m["reno_net_value_creation"] = reno.get("net_value_creation")

    # ── comp-derived renovation premium ──
    reno_premium = _estimate_comp_renovation_premium(report)
    m["comp_renovation_premium_pct"] = reno_premium.get("renovation_premium_pct")
    m["comp_renovated_comp_count"] = reno_premium.get("renovated_comp_count", 0)
    m["comp_dated_comp_count"] = reno_premium.get("dated_comp_count", 0)
    m["comp_median_renovated_ppsf"] = reno_premium.get("median_renovated_ppsf")
    m["comp_median_dated_ppsf"] = reno_premium.get("median_dated_ppsf")
    m["comp_estimated_renovated_value"] = reno_premium.get("estimated_renovated_value")
    m["comp_estimated_value_creation"] = reno_premium.get("estimated_value_creation")

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
        m["condition_confirmed"] = pi.condition_confirmed
        m["capex_confirmed"] = pi.capex_confirmed
        m["repair_capex_budget"] = pi.repair_capex_budget
        m["has_back_house"] = pi.has_back_house
        m["adu_type"] = pi.adu_type
        m["has_basement"] = pi.has_basement
        m["has_pool"] = pi.has_pool
        m["garage_spaces"] = pi.garage_spaces
        m["corner_lot"] = pi.corner_lot
        m["property_type"] = pi.property_type
        m["taxes"] = pi.taxes
        m["rent_confidence_override"] = pi.rent_confidence_override
        m["strategy_intent"] = pi.strategy_intent
        m["hold_period_years"] = pi.hold_period_years
        m["risk_tolerance"] = pi.risk_tolerance
        town_context = get_town_context(pi.town)
        if town_context is not None:
            ask_price = pi.purchase_price or m.get("ask_price")
            subject_ppsf = (ask_price / pi.sqft) if ask_price and pi.sqft else None
            town_price_anchor = town_context.median_price
            m["town_price_index"] = town_context.town_price_index
            m["town_ppsf_index"] = town_context.town_ppsf_index
            m["town_lot_index"] = town_context.town_lot_index
            m["town_liquidity_index"] = town_context.town_liquidity_index
            m["town_baseline_median_price"] = town_price_anchor
            m["town_baseline_median_ppsf"] = town_context.median_ppsf
            m["town_baseline_median_sqft"] = town_context.median_sqft
            m["town_baseline_median_lot_size"] = town_context.median_lot_size
            m["town_context_confidence"] = town_context.context_confidence
            m["town_context_flags"] = list(town_context.qa_flags)
            m["town_low_sample_flag"] = town_context.low_sample_flag
            m["town_high_missingness_flag"] = town_context.high_missingness_flag
            m["town_high_dispersion_flag"] = town_context.high_dispersion_flag
            m["town_outlier_heavy_flag"] = town_context.outlier_heavy_flag
            m["town_low_confidence_flag"] = town_context.low_confidence_flag
            m["subject_ppsf_vs_town"] = _safe_ratio(subject_ppsf, town_context.median_ppsf)
            m["subject_price_vs_town"] = _safe_ratio(ask_price, town_price_anchor)
            m["subject_lot_vs_town"] = _safe_ratio(pi.lot_size, town_context.median_lot_size)
            # Positive means the subject screens cheaper than the town's typical PPSF.
            m["town_adjusted_value_gap"] = (
                ((town_context.median_ppsf - subject_ppsf) / subject_ppsf)
                if subject_ppsf not in (None, 0) and town_context.median_ppsf not in (None, 0)
                else None
            )
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


def _safe_ratio(value: float | None, baseline: float | None) -> float | None:
    if value in (None, 0) or baseline in (None, 0):
        return None
    return float(value) / float(baseline)


def _ppsf_benchmark_signal(
    ask_ppsf: float,
    benchmark_ppsf: float | None,
    label: str,
) -> tuple[float, str, float | None] | None:
    if benchmark_ppsf in (None, 0):
        return None
    delta_pct = ((benchmark_ppsf - ask_ppsf) / ask_ppsf) * 100
    if delta_pct >= 10:
        return 5.0, f"Ask $/SF ${ask_ppsf:.0f} vs {label} ${benchmark_ppsf:.0f} — {delta_pct:.0f}% below benchmark", delta_pct
    if delta_pct >= 3:
        return 4.0, f"Ask $/SF ${ask_ppsf:.0f} vs {label} ${benchmark_ppsf:.0f} — slightly below benchmark", delta_pct
    if delta_pct >= -5:
        return 3.0, f"Ask $/SF ${ask_ppsf:.0f} roughly in line with {label} ${benchmark_ppsf:.0f}", delta_pct
    if delta_pct >= -15:
        return 2.0, f"Ask $/SF ${ask_ppsf:.0f} above {label} ${benchmark_ppsf:.0f} — premium pricing", delta_pct
    return 1.0, f"Ask $/SF ${ask_ppsf:.0f} significantly above {label} ${benchmark_ppsf:.0f}", delta_pct


def _town_liquidity_score(town_liquidity_index: float) -> float:
    return _clamp(_lerp_score(float(town_liquidity_index), 80, 120, 2.0, 4.5))


def _town_liquidity_adjusted_score(
    base_signal: float,
    town_liquidity_index: float | None,
    *,
    use_normalized_input: bool = True,
) -> float:
    if town_liquidity_index is None:
        return _clamp(base_signal if use_normalized_input else base_signal / 20.0)
    if use_normalized_input:
        normalized_base = base_signal / 20.0
    else:
        normalized_base = base_signal
    return _clamp(normalized_base * 0.85 + _town_liquidity_score(float(town_liquidity_index)) * 0.15)


def _sf(name: str, score: float | None, evidence: str, data_source: str, raw: float | str | None, weight: float) -> SubFactorScore | None:
    """Build a SubFactorScore. Returns None if score is None (unscorable)."""
    if score is None:
        return None
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


def _aggregate_category(
    category_name: str,
    category_key: str,
    scored: list[SubFactorScore | None],
    unscorable_names: list[str],
) -> CategoryScore:
    """Aggregate sub-factors into a category score with weight redistribution.

    If any sub-factor returned None (unscorable), its weight is redistributed
    proportionally to the scored sub-factors.
    """
    active = [s for s in scored if s is not None]
    if not active:
        cw = CATEGORY_WEIGHTS[category_key]
        return CategoryScore(
            category_name=category_name, score=NEUTRAL_SCORE, weight=cw,
            contribution=round(NEUTRAL_SCORE * cw, 4),
            unscored_factors=unscorable_names, weight_redistributed=True,
        )

    total_active_weight = sum(s.weight for s in active)
    if total_active_weight <= 0:
        total_active_weight = 1.0

    # Redistribute: scale weights so active weights sum to 1.0
    redistribution = 1.0 / total_active_weight
    for s in active:
        s.weight = round(s.weight * redistribution, 4)
        s.contribution = round(s.score * s.weight, 4)

    cat_score = _clamp(sum(s.contribution for s in active))
    cw = CATEGORY_WEIGHTS[category_key]
    return CategoryScore(
        category_name=category_name, score=round(cat_score, 2), weight=cw,
        contribution=round(cat_score * cw, 4), sub_factors=active,
        unscored_factors=unscorable_names, weight_redistributed=len(unscorable_names) > 0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY A: PRICE CONTEXT (25%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_price_vs_comps(m: dict) -> tuple[float, str, float | None]:
    """BCV versus all-in basis when available; fallback to ask versus BCV."""
    net_delta_pct = m.get("net_opportunity_delta_pct")
    net_delta_value = m.get("net_opportunity_delta_value")
    capex_source = m.get("capex_basis_source")
    if net_delta_pct is not None:
        delta = net_delta_pct * 100
        source_note = {
            "user_budget": "using explicit capex budget",
            "inferred_lane": "after inferred capex lane",
            "inferred_condition": "with condition-implied zero capex",
            "unknown": "before capex could be fully established",
        }.get(str(capex_source), "using all-in basis")
        if delta >= 10:
            return 5.0, f"Net opportunity delta {delta:.1f}% (+${abs(net_delta_value or 0):,.0f}) {source_note}", delta
        if delta >= 5:
            return 4.0, f"Net opportunity delta {delta:.1f}% — modest upside {source_note}", delta
        if delta >= -5:
            return 3.0, f"Net opportunity delta {delta:+.1f}% — roughly in line {source_note}", delta
        if delta >= -15:
            return 2.0, f"Net opportunity delta {delta:+.1f}% — thin after capex", delta
        return 1.0, f"Net opportunity delta {delta:+.1f}% — upside disappears after basis", delta

    pct = m.get("mispricing_pct")
    if pct is None:
        return NEUTRAL_SCORE, "No comp-based valuation available", None
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
    town_median_ppsf = m.get("town_baseline_median_ppsf")
    town_confidence = float(m.get("town_context_confidence") or 0.0)
    if not ask or not sqft or sqft == 0:
        return NEUTRAL_SCORE, "Sqft unavailable — cannot calculate $/SF", None
    ask_ppsf = ask / sqft
    model_benchmark = (bcv / sqft) if bcv and sqft else None
    model_signal = _ppsf_benchmark_signal(ask_ppsf, model_benchmark, "model")
    town_signal = _ppsf_benchmark_signal(ask_ppsf, town_median_ppsf, "town")

    if model_signal and town_signal and town_confidence >= 0.45:
        blended_score = _clamp(model_signal[0] * 0.75 + town_signal[0] * 0.25)
        delta_pct = ((model_benchmark - ask_ppsf) / ask_ppsf) * 100 if model_benchmark else None
        return (
            blended_score,
            f"Ask $/SF ${ask_ppsf:.0f} vs model ${model_benchmark:.0f}; town median ${town_median_ppsf:.0f}. "
            f"Town context is additive only ({town_confidence:.0%} confidence).",
            delta_pct,
        )
    if model_signal:
        return model_signal
    if town_signal and town_confidence >= 0.45:
        return town_signal[0], f"Ask $/SF ${ask_ppsf:.0f} vs town median ${town_median_ppsf:.0f} — comp PPSF benchmark is thin", town_signal[2]
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


def _build_category(category_name: str, category_key: str, factors: list[tuple[str, object, str]], m: dict) -> CategoryScore:
    """Generic category builder with weight redistribution."""
    w = SUB_FACTOR_WEIGHTS[category_key]
    scored: list[SubFactorScore | None] = []
    unscorable: list[str] = []
    for name, fn, src in factors:
        score, evidence, raw = fn(m)
        sf = _sf(name, score, evidence, src, raw, w[name])
        if sf is None:
            unscorable.append(name)
        scored.append(sf)
    return _aggregate_category(category_name, category_key, scored, unscorable)


def _calculate_price_context(m: dict) -> CategoryScore:
    return _build_category("Price Context", "price_context", [
        ("price_vs_comps", _score_price_vs_comps, "current_value.mispricing_pct"),
        ("ppsf_positioning", _score_ppsf_positioning, "current_value.bcv / sqft"),
        ("historical_pricing", _score_historical_pricing, "market_value_history / bull_base_bear"),
        ("scarcity_premium", _score_scarcity_premium, "scarcity_support.scarcity_support_score"),
    ], m)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY B: ECONOMIC SUPPORT (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_rent_support(m: dict) -> tuple[float | None, str, float | None]:
    """Income support ratio: rent / total monthly cost. Continuous interpolation for NJ coastal range."""
    ratio = m.get("income_support_ratio")
    if ratio is None:
        return None, "Income support ratio unavailable — no financing or rent data", None
    # Continuous scoring — avoids all-same-bucket at 0.45-0.60 ISR range
    if ratio >= 1.3:
        return 5.0, f"ISR {ratio:.2f}x — strong positive cash flow", ratio
    if ratio >= 1.0:
        return _lerp_score(ratio, 1.0, 1.3, 4.0, 5.0), f"ISR {ratio:.2f}x — positive cash flow", ratio
    if ratio >= 0.85:
        return _lerp_score(ratio, 0.85, 1.0, 3.0, 4.0), f"ISR {ratio:.2f}x — near break-even", ratio
    if ratio >= 0.6:
        return _lerp_score(ratio, 0.6, 0.85, 2.0, 3.0), f"ISR {ratio:.2f}x — negative carry", ratio
    if ratio >= 0.4:
        return _lerp_score(ratio, 0.4, 0.6, 1.0, 2.0), f"ISR {ratio:.2f}x — heavy negative carry", ratio
    return 1.0, f"ISR {ratio:.2f}x — severe negative carry", ratio


def _score_carry_efficiency(m: dict) -> tuple[float | None, str, float | None]:
    """Price-to-rent ratio as carry efficiency. Uses continuous interpolation for NJ coastal range."""
    ptr = m.get("price_to_rent")
    if ptr is None:
        return None, "Price-to-rent unavailable — no rent or price data", None
    # Continuous scoring via interpolation — avoids bucket collapse at NJ coastal PTR levels
    if ptr <= 12:
        return 5.0, f"PTR {ptr:.1f}x — exceptional rent yield", ptr
    if ptr <= 16:
        return _lerp_score(ptr, 12, 16, 5.0, 4.0), f"PTR {ptr:.1f}x — strong rent support", ptr
    if ptr <= 20:
        return _lerp_score(ptr, 16, 20, 4.0, 3.0), f"PTR {ptr:.1f}x — typical for coastal NJ", ptr
    if ptr <= 25:
        return _lerp_score(ptr, 20, 25, 3.0, 1.5), f"PTR {ptr:.1f}x — rent doesn't justify price", ptr
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
    """Is the property priced below replacement cost?
    Bug 6: replacement cost now read from DecisionModelSettings instead of
    hardcoded $400/sqft. TODO: make geography/property-type aware."""
    ask = m.get("purchase_price") or m.get("ask_price")
    sqft = m.get("sqft")
    lot_size = m.get("lot_size")
    if not ask or not sqft or sqft == 0:
        return NEUTRAL_SCORE, "Cannot estimate replacement cost", None
    ask_ppsf = ask / sqft
    replacement_ppsf = DEFAULT_DECISION_MODEL_SETTINGS.replacement_cost_per_sqft
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
    return _build_category("Economic Support", "economic_support", [
        ("rent_support", _score_rent_support, "income_support.income_support_ratio"),
        ("carry_efficiency", _score_carry_efficiency, "income_support.price_to_rent"),
        ("downside_protection", _score_downside_protection, "current_value.bcv vs ask"),
        ("replacement_cost", _score_replacement_cost, "property_input.sqft, purchase_price"),
    ], m)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY C: OPTIONALITY (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_adu_expansion(m: dict) -> tuple[float | None, str, str | None]:
    """Physical capacity for ADU or expansion. Uses lot sqft with coastal-appropriate thresholds."""
    has_bh = m.get("has_back_house")
    adu_type = m.get("adu_type")
    lot_size = m.get("lot_size")  # acres
    sqft = m.get("sqft") or 0
    has_basement = m.get("has_basement")
    garage = m.get("garage_spaces") or 0

    # Convert lot to sqft for finer scoring
    lot_sqft = (lot_size * 43560) if lot_size else None

    signals = 0
    notes: list[str] = []
    if has_bh:
        signals += 2
        notes.append(f"existing ADU ({adu_type or 'untyped'})")
    if has_basement:
        signals += 1
        notes.append("basement (conversion potential)")
    if garage >= 1:
        signals += 1
        notes.append(f"{garage} garage space(s)")
    # Lot scoring with NJ coastal thresholds (smaller lots than suburban)
    if lot_sqft is not None:
        remaining = lot_sqft - sqft if sqft else lot_sqft
        if remaining >= 3000:
            signals += 2
            notes.append(f"{lot_sqft:,.0f}sf lot, ~{remaining:,.0f}sf remaining")
        elif remaining >= 1500:
            signals += 1
            notes.append(f"{lot_sqft:,.0f}sf lot, ~{remaining:,.0f}sf remaining")
        else:
            notes.append(f"{lot_sqft:,.0f}sf lot, tight")

    # If we have zero data about features AND no lot, unscorable
    if lot_sqft is None and has_bh is None and has_basement is None and garage == 0:
        return None, "ADU potential unknown — no feature or lot data", None

    detail = "; ".join(notes) if notes else "no expansion signals"
    if signals >= 4:
        return 5.0, f"Strong expansion potential: {detail}", detail
    if signals >= 3:
        return 4.0, f"Good expansion potential: {detail}", detail
    if signals >= 2:
        return 3.5, f"Some expansion potential: {detail}", detail
    if signals >= 1:
        return 2.5, f"Limited expansion: {detail}", detail
    return 1.5, f"Minimal expansion options: {detail}", detail


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

    # No renovation scenario — estimate from comp-derived renovation premium
    condition = (m.get("condition_profile") or "").lower()
    capex = (m.get("capex_lane") or "").lower()
    premium_pct = m.get("comp_renovation_premium_pct")
    est_value = m.get("comp_estimated_renovated_value")
    est_creation = m.get("comp_estimated_value_creation")
    reno_comp_count = m.get("comp_renovated_comp_count", 0)
    dated_comp_count = m.get("comp_dated_comp_count", 0)
    median_reno_ppsf = m.get("comp_median_renovated_ppsf")
    median_dated_ppsf = m.get("comp_median_dated_ppsf")

    if condition in ("dated", "needs_work", "needs work") or capex == "heavy":
        if premium_pct is not None and reno_comp_count >= 1 and dated_comp_count >= 1:
            pct_display = premium_pct * 100
            evidence = (
                f"Renovated comps trade at ${median_reno_ppsf:,.0f}/sqft vs ${median_dated_ppsf:,.0f}/sqft "
                f"for dated — a {pct_display:.0f}% premium "
                f"({reno_comp_count} renovated, {dated_comp_count} dated comp{'s' if dated_comp_count != 1 else ''})"
            )
            if est_creation is not None and est_creation > 0:
                evidence += f". Estimated value creation: ${est_creation:,.0f}"
            if pct_display >= 20:
                return 5.0, evidence, premium_pct
            if pct_display >= 10:
                return 4.0, evidence, premium_pct
            return 3.5, evidence, premium_pct
        return 4.0, "Property needs work but no renovated comps available to estimate premium", condition or capex
    if condition in ("maintained",) or capex == "moderate":
        if premium_pct is not None and premium_pct > 0 and reno_comp_count >= 1:
            pct_display = premium_pct * 100
            evidence = (
                f"Moderate renovation potential — renovated comps trade at a {pct_display:.0f}% premium "
                f"(${median_reno_ppsf:,.0f}/sqft vs ${median_dated_ppsf:,.0f}/sqft)"
            )
            return 3.0, evidence, premium_pct
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

    detail = ", ".join(notes) if notes else "limited options"
    score = min(5.0, 1.0 + options)
    return score, f"{options} viable strategies: {detail}", options


def _score_zoning_optionality(m: dict) -> tuple[float | None, str, str | None]:
    """Zoning, lot config, and regulatory environment. Returns None when no real zoning data exists."""
    # Only use regulatory_trend_score if local_intelligence actually had documents
    # (score of exactly 50.0 with 0 confidence = no real data, default from empty module)
    dev_activity = m.get("development_activity_score")
    reg_score = m.get("regulatory_trend_score")
    has_real_local_data = dev_activity is not None and dev_activity > 0

    lot = m.get("lot_size")
    corner = m.get("corner_lot")
    prop_type = (m.get("property_type") or "").lower()

    signals = 0
    notes: list[str] = []

    if has_real_local_data and reg_score is not None:
        if reg_score >= 60:
            signals += 1
            notes.append(f"permissive regulatory trend ({reg_score:.0f})")
        elif reg_score < 40:
            notes.append(f"restrictive environment ({reg_score:.0f})")

    if lot and lot >= 0.25:
        signals += 1
        notes.append(f"{lot:.2f} acre lot — subdivision potential")
    if corner:
        signals += 1
        notes.append("corner lot")
    if "multi" in prop_type or "duplex" in prop_type:
        signals += 1
        notes.append(f"zoned {prop_type}")

    # If we have no real data at all, return None → weight redistribution
    if signals == 0 and not has_real_local_data and not corner:
        return None, "No zoning data available — weight redistributed", None

    detail = "; ".join(notes) if notes else "standard residential"
    if signals >= 3:
        return 5.0, f"Strong zoning optionality: {detail}", detail
    if signals == 2:
        return 4.0, f"Good zoning potential: {detail}", detail
    if signals == 1:
        return 3.0, f"Some flexibility: {detail}", detail
    return 2.0, f"Standard residential zoning: {detail}", detail


def _weighted_component_average(subs: list[SubFactorScore], names: set[str]) -> float | None:
    matched = [sf for sf in subs if sf.name in names]
    if not matched:
        return None
    total_weight = sum(sf.weight for sf in matched)
    if total_weight <= 0:
        return None
    weighted_score = sum(sf.score * sf.weight for sf in matched) / total_weight
    return round(weighted_score, 2)


def _component_note(subs: list[SubFactorScore], names: set[str]) -> str:
    matched = [sf for sf in subs if sf.name in names]
    if not matched:
        return "No sub-factors available."
    strongest = max(matched, key=lambda sf: sf.score)
    weakest = min(matched, key=lambda sf: sf.score)
    if strongest.name == weakest.name:
        return strongest.evidence
    return f"Best support: {strongest.evidence} Main drag: {weakest.evidence}"


def _calculate_optionality(m: dict) -> CategoryScore:
    return _build_category("Optionality", "optionality", [
        ("adu_expansion", _score_adu_expansion, "property_input (ADU, basement, lot, garage)"),
        ("renovation_upside", _score_renovation_upside, "renovation_scenario / condition_profile"),
        ("strategy_flexibility", _score_strategy_flexibility, "multi-module synthesis"),
        ("zoning_optionality", _score_zoning_optionality, "local_intelligence.regulatory_trend_score"),
    ], m)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY D: MARKET POSITION (15%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_dom_signal(m: dict) -> tuple[float, str, float | None]:
    """Days on market — absorption speed signal."""
    dom = m.get("days_on_market")
    town_liquidity_index = m.get("town_liquidity_index")
    if dom is None:
        if town_liquidity_index is not None:
            score = _lerp_score(float(town_liquidity_index), 80, 120, 2.0, 4.5)
            return score, f"DOM unavailable — using town liquidity index {float(town_liquidity_index):.0f}", town_liquidity_index
        return NEUTRAL_SCORE, "Days on market unavailable", None
    if dom <= 7:
        base_score = 5.0
        evidence = f"{dom} DOM — hot demand, absorbing immediately"
    elif dom <= 21:
        base_score = 4.0
        evidence = f"{dom} DOM — healthy demand"
    elif dom <= 45:
        base_score = 3.0
        evidence = f"{dom} DOM — normal absorption"
    elif dom <= 90:
        base_score = 2.0
        evidence = f"{dom} DOM — slow absorption, possible issues"
    else:
        base_score = 1.0
        evidence = f"{dom} DOM — stale listing, demand concerns"
    if town_liquidity_index is not None:
        town_bias = _town_liquidity_score(float(town_liquidity_index))
        base_score = _clamp(base_score * 0.8 + town_bias * 0.2)
        evidence = f"{evidence}; town liquidity backdrop {float(town_liquidity_index):.0f}/100"
    return base_score, evidence, dom


def _score_inventory_tightness(m: dict) -> tuple[float | None, str, float | None]:
    """Supply tightness from scarcity score. Ignores supply_pipeline_score (broken when local_intelligence has no data)."""
    scarcity = m.get("scarcity_support_score") or m.get("location_scarcity_score")
    dom = m.get("days_on_market")

    # Primary: scarcity score (reliable, from town/county data)
    if scarcity is not None:
        score = _lerp_score(scarcity, 25, 80, 1.5, 5.0)
        return score, f"Inventory tightness from scarcity ({scarcity:.0f}/100)", scarcity

    # Secondary: infer from DOM
    if dom is not None:
        score = _lerp_score(dom, 120, 7, 1.5, 5.0)
        return score, f"Inventory tightness inferred from {dom} DOM", dom

    return None, "Inventory tightness unknown — no scarcity or DOM data", None


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
    market_momentum = m.get("market_momentum_score")
    market_label = m.get("market_momentum_label")
    if market_momentum is not None:
        score = _lerp_score(float(market_momentum), 20, 85, 1.0, 5.0)
        label = market_label or "momentum signal"
        return score, f"{label} ({float(market_momentum):.0f}/100)", market_momentum

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
    return _build_category("Market Position", "market_position", [
        ("dom_signal", _score_dom_signal, "property_input.days_on_market"),
        ("inventory_tightness", _score_inventory_tightness, "scarcity_support / local_intelligence"),
        ("buyer_seller_balance", _score_buyer_seller_balance, "town_county + DOM + ZHVI"),
        ("location_momentum", _score_location_momentum, "town_county_outlook + local_intelligence"),
    ], m)


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY E: RISK LAYER (20%)
# ═══════════════════════════════════════════════════════════════════════════════


def _score_liquidity_risk(m: dict) -> tuple[float, str, float | None]:
    """How quickly could this property be resold?"""
    liq = m.get("liquidity_score")
    dom = m.get("days_on_market")
    rental_liq = m.get("rental_liquidity_score")
    town_liquidity_index = m.get("town_liquidity_index")

    if liq is not None:
        score = _town_liquidity_adjusted_score(float(liq), town_liquidity_index)
        if liq >= 75:
            return score, f"High liquidity (score {liq:.0f}) — quick exit possible", liq
        if liq >= 55:
            return score, f"Good liquidity ({liq:.0f})", liq
        if liq >= 40:
            return score, f"Moderate liquidity ({liq:.0f})", liq
        if liq >= 25:
            return score, f"Low liquidity ({liq:.0f}) — exit may take time", liq
        return score, f"Very low liquidity ({liq:.0f}) — illiquid market", liq

    if rental_liq is not None:
        score = _town_liquidity_adjusted_score(float(rental_liq), town_liquidity_index)
        if rental_liq >= 75:
            return score, f"Liquidity inferred from rental absorption ({rental_liq:.0f})", rental_liq
        if rental_liq >= 55:
            return score, f"Moderate liquidity inferred from rental absorption ({rental_liq:.0f})", rental_liq
        return score, f"Thin liquidity inferred from rental absorption ({rental_liq:.0f})", rental_liq

    if dom is not None:
        score = _lerp_score(dom, 90, 7, 1.5, 4.5)
        score = _town_liquidity_adjusted_score(score, town_liquidity_index, use_normalized_input=False)
        return score, f"Liquidity estimated from {dom} DOM", dom

    if town_liquidity_index is not None:
        score = _town_liquidity_score(float(town_liquidity_index))
        return score, f"Property liquidity unavailable — using town liquidity context ({float(town_liquidity_index):.0f}/100)", town_liquidity_index

    return NEUTRAL_SCORE, "No liquidity data available", None


def _score_capex_risk(m: dict) -> tuple[float, str, str | None]:
    """Deferred maintenance and surprise capex exposure."""
    condition = (m.get("condition_profile") or "").lower()
    capex = (m.get("capex_lane") or "").lower()
    year_built = m.get("year_built")
    repair_capex_budget = m.get("repair_capex_budget")
    sqft = m.get("sqft")
    condition_confirmed = bool(m.get("condition_confirmed"))
    capex_confirmed = bool(m.get("capex_confirmed"))

    if repair_capex_budget is not None and repair_capex_budget >= 0:
        budget_psf = (repair_capex_budget / sqft) if sqft else None
        confirmation_tag = "user-confirmed" if capex_confirmed or condition_confirmed else "explicit"
        if budget_psf is not None:
            if budget_psf <= 15:
                return 4.5, f"Low capex risk: {confirmation_tag} budget about ${budget_psf:.0f}/SF", f"${repair_capex_budget:,.0f}"
            if budget_psf <= 40:
                return 3.5, f"Manageable capex load: {confirmation_tag} budget about ${budget_psf:.0f}/SF", f"${repair_capex_budget:,.0f}"
            if budget_psf <= 80:
                return 2.0, f"Meaningful capex burden: {confirmation_tag} budget about ${budget_psf:.0f}/SF", f"${repair_capex_budget:,.0f}"
            return 1.0, f"Heavy capex burden: {confirmation_tag} budget about ${budget_psf:.0f}/SF", f"${repair_capex_budget:,.0f}"
        if repair_capex_budget <= 25000:
            return 4.0, f"Low capex risk: {confirmation_tag} budget of ${repair_capex_budget:,.0f}", f"${repair_capex_budget:,.0f}"
        if repair_capex_budget <= 75000:
            return 3.0, f"Moderate capex risk: {confirmation_tag} budget of ${repair_capex_budget:,.0f}", f"${repair_capex_budget:,.0f}"
        return 1.5, f"High capex risk: {confirmation_tag} budget of ${repair_capex_budget:,.0f}", f"${repair_capex_budget:,.0f}"

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
    if condition_confirmed:
        notes.append("condition confirmed by user")
    if capex_confirmed:
        notes.append("capex confirmed by user")

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
    """How reliable and sustainable is the income stream? Uses numeric scores, not label matching."""
    rental_ease_score = m.get("rental_ease_score")  # 0-100 numeric
    demand_depth = m.get("demand_depth_score")  # 0-100 numeric
    burden = m.get("downside_burden")
    risk_view = (m.get("risk_view") or "").lower()
    isr = m.get("income_support_ratio")

    # Start from rental ease as a 1-5 scale (most direct stability signal)
    if rental_ease_score is not None:
        base = _lerp_score(rental_ease_score, 20, 80, 1.5, 4.5)
    elif isr is not None:
        # Fallback: ISR as stability proxy
        base = _lerp_score(isr, 0.3, 1.3, 1.0, 4.5)
    else:
        base = NEUTRAL_SCORE

    notes: list[str] = []
    adj = 0.0

    # Downside burden adjustment
    if burden is not None:
        if burden <= 200:
            adj += 0.3
            notes.append(f"low burden (${burden:,.0f}/mo)")
        elif burden >= 2000:
            adj -= 0.4
            notes.append(f"high burden (${burden:,.0f}/mo)")
        elif burden >= 1000:
            adj -= 0.2
            notes.append(f"moderate burden (${burden:,.0f}/mo)")

    # Risk view from income module
    if "strong" in risk_view:
        adj += 0.2
    elif "negative" in risk_view or "weak" in risk_view:
        adj -= 0.2

    score = _clamp(base + adj)
    detail = "; ".join(notes) if notes else ""
    ease_text = f"ease {rental_ease_score:.0f}/100" if rental_ease_score is not None else ""
    return score, f"Income stability ({ease_text}{'; ' if ease_text and detail else ''}{detail})", score


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
    return _build_category("Risk Layer", "risk_layer", [
        ("liquidity_risk", _score_liquidity_risk, "rental_ease.liquidity_score"),
        ("capex_risk", _score_capex_risk, "property_input (condition, capex, year)"),
        ("income_stability", _score_income_stability, "income_support + rental_ease"),
        ("macro_regulatory", _score_macro_regulatory, "risk_constraints + local_intelligence"),
    ], m)


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SCORE
# ═══════════════════════════════════════════════════════════════════════════════


def get_recommendation_tier(score: float) -> tuple[str, str]:
    for threshold, tier, action in RECOMMENDATION_TIERS:
        if score >= threshold:
            return tier, action
    return "Avoid", "Does not meet investment criteria on current information."


def _generate_narrative(
    score: float,
    categories: dict[str, CategoryScore],
    *,
    confidence_level: str = "High",
    top_missing_input: str = "",
    top_two_missing: str = "",
) -> str:
    """Generate a 2-3 sentence narrative summarizing the score, with
    confidence calibration when data quality is Medium or Low."""
    tier, _ = get_recommendation_tier(score)
    ranked = sorted(categories.values(), key=lambda c: c.score, reverse=True)
    strongest = ranked[0]
    weakest = ranked[-1]

    parts: list[str] = []

    # Confidence calibration prefix
    if confidence_level == "Low":
        caveat = "Caution: This analysis has significant data gaps. Key assumptions are estimated."
        if top_two_missing:
            caveat += f" Consider this a preliminary assessment — add {top_two_missing} for a more reliable recommendation."
        parts.append(caveat)
    elif confidence_level == "Medium":
        caveat = "Note: This analysis is based on partially estimated data."
        if top_missing_input:
            caveat += f" The recommendation confidence would improve with {top_missing_input.lower()}."
        parts.append(caveat)

    parts.append(f"Overall score {score:.2f}/5.0 — {tier}.")

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

    # Compute confidence level for narrative calibration
    confidence_level, top_missing, top_two = _extract_confidence_for_narrative(report)
    narrative = _generate_narrative(
        final, categories,
        confidence_level=confidence_level,
        top_missing_input=top_missing,
        top_two_missing=top_two,
    )

    return FinalScore(
        score=final,
        tier=tier,
        action=action,
        narrative=narrative,
        category_scores=categories,
    )


def _extract_confidence_for_narrative(report: AnalysisReport) -> tuple[str, str, str]:
    """Derive confidence level and top missing inputs for narrative calibration."""
    from briarwood.evidence import compute_confidence_breakdown, compute_metric_input_statuses

    breakdown = compute_confidence_breakdown(report)
    overall = breakdown.overall_confidence
    statuses = compute_metric_input_statuses(report)

    # Determine level using same logic as view_models._compute_confidence_level
    comp_mod = report.module_results.get("comparable_sales")
    comp_count = int(comp_mod.metrics.get("comp_count", 0)) if comp_mod else 0
    cost_val = report.module_results.get("cost_valuation")
    rent_source = str(cost_val.metrics.get("rent_source_type", "missing")) if cost_val else "missing"
    town_mod = report.module_results.get("town_county_outlook")
    town_conf = town_mod.confidence if town_mod else 0.0

    weak_count = 0
    strong_count = 0
    if comp_count < 3:
        weak_count += 1
    elif comp_count >= 5:
        strong_count += 1
    if rent_source in ("missing",):
        weak_count += 1
    elif rent_source in ("manual_input", "provided"):
        strong_count += 1
    if town_conf < 0.50:
        weak_count += 1
    elif town_conf >= 0.75:
        strong_count += 1

    if weak_count >= 2 or overall < 0.55:
        level = "Low"
    elif strong_count >= 3 and overall >= 0.75:
        level = "High"
    else:
        level = "Medium"

    # Collect top missing inputs from metric statuses
    _impact_labels = {
        "estimated_monthly_rent": "rent estimate", "unit_rents": "unit rents",
        "taxes": "property taxes", "insurance": "insurance cost",
        "repair_capex_budget": "renovation budget", "condition_profile_override": "condition confirmation",
        "local_documents": "local market data",
    }
    seen: set[str] = set()
    top_fields: list[str] = []
    for s in statuses:
        if s.status == "fact_based":
            continue
        for f in s.prompt_fields:
            if f not in seen and f in _impact_labels:
                seen.add(f)
                top_fields.append(_impact_labels[f])
            if len(top_fields) >= 2:
                break
        if len(top_fields) >= 2:
            break

    top_missing = top_fields[0] if top_fields else ""
    top_two = " and ".join(top_fields[:2]) if top_fields else ""
    return level, top_missing, top_two
